"""Python client for FanDuel API (https://fanduelapi.com).

FanDuel API is an independent REST API for FanDuel Sportsbook data: player props, game lines,
alternates, futures, DFS salaries and the history of every line move. It is operated by
Stunning Couches LLC and is not affiliated with, endorsed by or sponsored by FanDuel.

No dependencies beyond the standard library.

    from fanduelapi import FanDuelAPI
    fd = FanDuelAPI()                      # reads FANDUEL_API_KEY
    for p in fd.props(league="nba", stat="points", limit=20):
        print(p["player"], p["line"], p["over_american"], p["under_american"])
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

__all__ = ["FanDuelAPI", "FanDuelAPIError", "sample_props", "credit_costs", "__version__"]
__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://fanduelapi.com"
USER_AGENT = f"fanduelapi-python/{__version__}"


class FanDuelAPIError(Exception):
    """A non-2xx response. `status`, `code` and `body` carry the API's error object."""

    def __init__(self, status: int, code: str, message: str, body: Optional[dict] = None):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.body = body or {}

    @property
    def upgrade_url(self) -> Optional[str]:
        return (self.body.get("error") or {}).get("upgrade_url")

    @property
    def topup_url(self) -> Optional[str]:
        return (self.body.get("error") or {}).get("topup_url")


def _request(method: str, url: str, headers: Dict[str, str], body: Optional[dict], timeout: float):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode() or "{}"
            return res.status, dict(res.headers), json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"error": {"code": "HTTP_ERROR", "message": raw[:200]}}
        return e.code, dict(e.headers), parsed


class FanDuelAPI:
    """Client for the REST API at https://fanduelapi.com/api/v1.

    Every method returns the response's `data` list (or object), except `request`, which returns
    the whole body. On HTTP 429 the client waits for Retry-After and tries again, up to
    `max_retries` times; a monthly quota stop (QUOTA_EXCEEDED) is raised at once, because waiting
    does not help until the reset.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0, max_retries: int = 3):
        self.api_key = api_key if api_key is not None else os.environ.get("FANDUEL_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_headers: Dict[str, str] = {}

    # ---------------- transport ----------------
    def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Optional[dict] = None) -> dict:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base_url}{path}" + (f"?{urllib.parse.urlencode(query, doseq=True)}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        attempt = 0
        while True:
            status, resp_headers, parsed = _request(method, url, headers, body, self.timeout)
            self.last_headers = {k.lower(): v for k, v in resp_headers.items()}
            if 200 <= status < 300:
                return parsed
            err = parsed.get("error") if isinstance(parsed, dict) else None
            code = (err or {}).get("code", "HTTP_ERROR")
            if status == 429 and code != "QUOTA_EXCEEDED" and attempt < self.max_retries:
                attempt += 1
                time.sleep(float(self.last_headers.get("retry-after", "5")))
                continue
            raise FanDuelAPIError(status, code, (err or {}).get("message", f"HTTP {status}"), parsed if isinstance(parsed, dict) else None)

    def _get(self, path: str, **params: Any) -> Any:
        return self.request("GET", f"/api/v1{path}", params).get("data")

    # ---------------- data ----------------
    def props(self, league: Optional[str] = None, stat: Optional[str] = None, player: Optional[str] = None, event_id: Optional[str] = None,
              view: Optional[str] = None, updated_since: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None, **extra: Any) -> List[dict]:
        """Current FanDuel player props. view="compact" returns up to 1,000 rows in one call, without the move summary."""
        return self._get("/props", league=league, stat=stat, player=player, event_id=event_id, view=view, updated_since=updated_since, limit=limit, offset=offset, **extra)

    def prop_history(self, prop_id: str) -> Any:
        """Every recorded state of one prop: each line move, price move and status change."""
        return self._get(f"/props/{urllib.parse.quote(prop_id, safe='')}/history")

    def changes(self, since: Optional[str] = None, league: Optional[str] = None, limit: Optional[int] = None) -> dict:
        """One page of the change feed. Returns the whole body: `data` and `meta.next_cursor`."""
        return self.request("GET", "/api/v1/changes", {"since": since, "league": league, "limit": limit})

    def follow_changes(self, since: Optional[str] = None, league: Optional[str] = None, poll_seconds: Optional[float] = None) -> Iterator[dict]:
        """Yield every change forever, sleeping between empty pages for X-Next-Update-Seconds (or poll_seconds)."""
        cursor = since
        while True:
            page = self.changes(since=cursor, league=league)
            for change in page.get("data") or []:
                yield change
            cursor = (page.get("meta") or {}).get("next_cursor") or cursor
            if not page.get("data"):
                time.sleep(poll_seconds if poll_seconds is not None else float(self.last_headers.get("x-next-update-seconds", "30")))

    def odds(self, league: Optional[str] = None, date: Optional[str] = None, market_type: Optional[str] = None, **extra: Any) -> Any:
        """The odds board: every game of a league with its game lines."""
        return self._get("/odds", league=league, date=date, market_type=market_type, **extra)

    def events(self, league: Optional[str] = None, **extra: Any) -> List[dict]:
        return self._get("/events", league=league, **extra)

    def markets(self, **params: Any) -> List[dict]:
        return self._get("/markets", **params)

    def game_report(self, event_id: str) -> Any:
        return self._get(f"/games/{urllib.parse.quote(event_id, safe='')}/report")

    def futures(self, league: Optional[str] = None, **extra: Any) -> List[dict]:
        return self._get("/futures", league=league, **extra)

    def compare(self, **params: Any) -> List[dict]:
        """FanDuel main line against its own alternate ladder, and against Novig, DraftKings and PrizePicks (view="books")."""
        return self._get("/compare", **params)

    def ev(self, **params: Any) -> List[dict]:
        """FanDuel prices above the Novig fair price, with EV, edge and Kelly. min_edge is in percent."""
        return self._get("/ev", **params)

    def arbitrage(self, **params: Any) -> List[dict]:
        return self._get("/arbitrage", **params)

    def results(self, league: Optional[str] = None, stat: Optional[str] = None, player: Optional[str] = None, **extra: Any) -> List[dict]:
        """Graded props: closing line, actual stat and result (paid plans)."""
        return self._get("/results", league=league, stat=stat, player=player, **extra)

    def hit_rates(self, player: str, stat: str, league: Optional[str] = None, games: Optional[int] = None) -> Any:
        return self._get("/hit-rates", league=league, player=player, stat=stat, games=games)

    def training_set(self, **params: Any) -> List[dict]:
        return self._get("/training-set", **params)

    def dfs_slates(self, sport: Optional[str] = None, **extra: Any) -> List[dict]:
        return self._get("/dfs/slates", sport=sport, **extra)

    def dfs_players(self, slate_id: str, **params: Any) -> List[dict]:
        return self._get(f"/dfs/slates/{urllib.parse.quote(slate_id, safe='')}/players", **params)

    def injuries(self, league: Optional[str] = None, **extra: Any) -> List[dict]:
        return self._get("/injuries", league=league, **extra)

    def coverage(self) -> Any:
        return self._get("/coverage")

    def credits_used(self) -> Dict[str, str]:
        """X-Credits-* headers of the last response."""
        return {k: v for k, v in self.last_headers.items() if k.startswith("x-credits")}


def credit_costs(path: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> Any:
    """The credit cost table, or with `path` the quote for that one call ({"path", "credits"}). No key needed."""
    body = FanDuelAPI(api_key="", base_url=base_url).request("GET", "/api/v1/credit-costs", {"path": path})
    return (body.get("meta") or {}).get("quote") if path else body.get("data")


def sample_props(sport: str = "nba", base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> List[dict]:
    """Up to 10 real FanDuel props, delayed like the Free plan, from the keyless MCP tool get_sample_props. No key needed."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_sample_props", "arguments": {"sport": sport}}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": USER_AGENT}
    status, _, parsed = _request("POST", f"{base_url.rstrip('/')}/api/mcp", headers, body, timeout)
    if status != 200 or "result" not in parsed:
        raise FanDuelAPIError(status, "MCP_ERROR", json.dumps(parsed.get("error", parsed))[:200], parsed)
    text = parsed["result"]["content"][0]["text"]
    return json.loads(text).get("data", [])
