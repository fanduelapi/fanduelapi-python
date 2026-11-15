"""Offline tests against a local fake server. Live checks: FANDUEL_LIVE=1 python -m unittest discover -s tests"""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import fanduelapi  # noqa: E402
from fanduelapi import FanDuelAPI, FanDuelAPIError  # noqa: E402

SEEN = []
STATE = {"rate_limited_once": False}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        SEEN.append((self.path, self.headers.get("Authorization")))
        if self.path.startswith("/api/v1/props?"):
            return self._send(200, {"data": [{"player": "Aaron Nesmith", "stat": "assists", "line": 1.5, "over_american": 110, "under_american": -146}], "meta": {}}, {"X-Credits-Used": "3"})
        if self.path.startswith("/api/v1/changes"):
            if "since=c1" in self.path:
                return self._send(200, {"data": [], "meta": {"next_cursor": "c1"}}, {"X-Next-Update-Seconds": "0"})
            return self._send(200, {"data": [{"kind": "line_move", "player": "A", "previous": {"line": 20.5}, "current": {"line": 21.5}}], "meta": {"next_cursor": "c1"}})
        if self.path.startswith("/api/v1/odds"):
            if not STATE["rate_limited_once"]:
                STATE["rate_limited_once"] = True
                return self._send(429, {"error": {"code": "RATE_LIMITED", "message": "slow down"}}, {"Retry-After": "0"})
            return self._send(200, {"data": [{"event_id": "1"}]})
        if self.path.startswith("/api/v1/results"):
            return self._send(429, {"error": {"code": "QUOTA_EXCEEDED", "message": "month used", "topup_url": "https://fanduelapi.com/topup?t=x", "upgrade_url": "https://fanduelapi.com/upgrade?t=x"}})
        if self.path.startswith("/api/v1/credit-costs"):
            quote = {"path": "/api/v1/props?league=nba&limit=200", "credits": 6} if "path=" in self.path else None
            return self._send(200, {"data": [{"path": "/api/v1/changes", "credits_per_100_rows": 1}], "meta": {"quote": quote}})
        return self._send(404, {"error": {"code": "NOT_FOUND", "message": "nope"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        if self.path == "/api/mcp" and body["params"]["name"] == "get_sample_props":
            text = json.dumps({"data": [{"player": "Aaron Nesmith", "line": 1.5}]})
            return self._send(200, {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": text}]}})
        return self._send(400, {"error": {"code": "BAD", "message": "bad"}})


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Fake)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def client(self):
        return FanDuelAPI(api_key="fd_test", base_url=self.base, max_retries=2)

    def test_props_sends_bearer_and_params_and_returns_data(self):
        rows = self.client().props(league="nba", stat="points", limit=5)
        self.assertEqual(rows[0]["player"], "Aaron Nesmith")
        path, auth = SEEN[-1]
        self.assertIn("league=nba", path)
        self.assertIn("stat=points", path)
        self.assertEqual(auth, "Bearer fd_test")

    def test_credit_headers_are_kept(self):
        c = self.client()
        c.props(league="nba")
        self.assertEqual(c.credits_used(), {"x-credits-used": "3"})

    def test_change_feed_follows_the_cursor(self):
        c = self.client()
        page = c.changes(league="NBA")
        self.assertEqual(page["meta"]["next_cursor"], "c1")
        first = next(c.follow_changes(league="NBA", poll_seconds=0))
        self.assertEqual(first["current"]["line"], 21.5)

    def test_rate_limit_is_retried(self):
        self.assertEqual(self.client().odds(league="nfl")[0]["event_id"], "1")

    def test_quota_stop_is_raised_with_its_links(self):
        with self.assertRaises(FanDuelAPIError) as ctx:
            self.client().results(league="nba")
        self.assertEqual(ctx.exception.code, "QUOTA_EXCEEDED")
        self.assertTrue(ctx.exception.topup_url.startswith("https://"))

    def test_keyless_helpers(self):
        self.assertEqual(fanduelapi.sample_props("nba", base_url=self.base)[0]["player"], "Aaron Nesmith")
        self.assertEqual(fanduelapi.credit_costs(base_url=self.base)[0]["credits_per_100_rows"], 1)
        self.assertEqual(fanduelapi.credit_costs("/api/v1/props?league=nba&limit=200", base_url=self.base)["credits"], 6)
        self.assertIsNone(SEEN[-1][1], "keyless call sends no Authorization")


@unittest.skipUnless(os.environ.get("FANDUEL_LIVE") == "1", "live check: set FANDUEL_LIVE=1")
class LiveTest(unittest.TestCase):
    def test_sample_props_live(self):
        rows = fanduelapi.sample_props("nba")
        self.assertTrue(rows and "line" in rows[0] and "over_american" in rows[0])

    def test_credit_costs_live(self):
        self.assertTrue(any(r["path"] == "/api/v1/changes" for r in fanduelapi.credit_costs()))


if __name__ == "__main__":
    unittest.main()
