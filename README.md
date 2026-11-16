# FanDuel API for Python: fanduelapi

The FanDuel API Python client. `pip install fanduelapi` and read FanDuel Sportsbook player props, game lines, alternates, futures, DFS salaries and the history of every line move as JSON. Free key, no card.

[Website](https://fanduelapi.com/?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python) | [Docs](https://fanduelapi.com/docs?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python) | [Free API key](https://fanduelapi.com/sign-up?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python) | [Pricing](https://fanduelapi.com/pricing?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python) | [All SDKs](https://fanduelapi.com/sdks?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python)

Also for fanduelapi.com: [JavaScript: `npm install fanduelapi`](https://github.com/fanduelapi/fanduelapi-js) | [MCP server: `npx -y fanduelapi-mcp`](https://github.com/fanduelapi/fanduelapi-mcp)

Python client for [FanDuel API](https://fanduelapi.com/?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python): FanDuel Sportsbook player props, game lines, alternates, futures, DFS salaries and the history of every line move, as JSON. Standard library only, Python 3.8+.

FanDuel API is an independent data service operated by Stunning Couches LLC. It is not affiliated with, endorsed by or sponsored by FanDuel.

## Install

```bash
pip install fanduelapi
```

## Try it with no key

Two helpers need no account: a small delayed sample of real props, and the credit cost of any call.

```python
import fanduelapi

for p in fanduelapi.sample_props("nba")[:5]:
    print(f"{p['player']:<22} {p['stat']:<9} {p['line']:>5}  over {p['over_american']:>5}  under {p['under_american']:>5}")

print(fanduelapi.credit_costs("/api/v1/props?league=nba&limit=200"))
```

Output on 15 November 2026 (the sample is delayed like the Free plan, so yours will differ):

```
Aaron Nesmith          assists     1.5  over   108  under  -144
Aaron Nesmith          pa         14.5  over  -114  under  -114
Aaron Nesmith          points     13.5  over   102  under  -136
Aaron Nesmith          pr         16.5  over  -118  under  -112
Aaron Nesmith          pra        18.5  over  -104  under  -128
{'path': '/api/v1/props?league=nba&limit=200', 'credits': 6}
```

## With a key

Get a free key (no card) at https://fanduelapi.com/sign-up?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python and export it:

```bash
export FANDUEL_API_KEY="fd_..."
```

```python
from fanduelapi import FanDuelAPI

fd = FanDuelAPI()  # reads FANDUEL_API_KEY

# Every NBA points prop, with where it opened and how often it moved
for p in fd.props(league="nba", stat="points", limit=50):
    m = p["move"]
    print(p["player"], p["line"], p["over_american"], p["under_american"],
          "opened", m["open"]["line"], "line moves", m["line_moves"])

# The whole board in one call (compact rows, 1 credit per 100 rows)
board = fd.props(league="nfl", view="compact", limit=1000)

# Every recorded move of one prop
history = fd.prop_history(board[0]["id"])

# Game lines for every game of a league
games = fd.odds(league="nhl")

# FanDuel prices above the exchange fair price (min_edge is in percent)
value = fd.ev(league="nba", min_edge=2)
```

### Follow line moves

`follow_changes` reads the change feed with a cursor and sleeps between empty pages for as long as the API's `X-Next-Update-Seconds` header says:

```python
for c in fd.follow_changes(league="NBA"):
    if c["kind"] == "line_move":
        print(c["player"], c["stat"], c["previous"]["line"], "->", c["current"]["line"])
```

### Errors and limits

Non-2xx responses raise `FanDuelAPIError` with `status`, `code` and the API's error body. Short rate limits (429 with `Retry-After`) are retried automatically. A monthly stop (`QUOTA_EXCEEDED`) is raised at once with `topup_url` and `upgrade_url` for the person to click; the client never buys anything.

```python
from fanduelapi import FanDuelAPIError
try:
    fd.results(league="nba")
except FanDuelAPIError as e:
    print(e.code, e.topup_url)
```

`fd.credits_used()` returns the `X-Credits-*` headers of the last response.

## Methods

| Method | Endpoint |
| --- | --- |
| `props(league, stat, player, event_id, view, updated_since, limit, offset)` | `GET /api/v1/props` |
| `prop_history(prop_id)` | `GET /api/v1/props/{id}/history` |
| `changes(since, league, limit)`, `follow_changes(...)` | `GET /api/v1/changes` |
| `odds(league, date, market_type)` | `GET /api/v1/odds` |
| `events`, `markets`, `futures`, `game_report(event_id)` | events, markets, futures, game report |
| `compare`, `ev`, `arbitrage` | alternates and other venues, +EV, arbitrage |
| `results`, `hit_rates(player, stat)`, `training_set` | graded results and model data (paid plans) |
| `dfs_slates`, `dfs_players(slate_id)`, `injuries`, `coverage` | DFS salaries, injuries, what is tracked |
| `fanduelapi.sample_props(sport)`, `fanduelapi.credit_costs(path)` | keyless |

Plans, credits and limits: https://fanduelapi.com/pricing?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python and https://fanduelapi.com/credits?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python. Full reference: https://fanduelapi.com/docs?utm_source=github&utm_medium=readme&utm_campaign=fanduelapi-python and https://fanduelapi.com/openapi.json.

## Tests

```bash
python -m unittest discover -s tests            # offline, against a local fake server
FANDUEL_LIVE=1 python -m unittest discover -s tests   # also hits the keyless live endpoints
```

## License

MIT
