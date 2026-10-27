# Sokokali

Sokokali is an AI-powered sports and markets presenter for a Kenyan audience. It chats in English, Kiswahili and Sheng. It covers two markets:

- **Football:** fixtures, results, team form and probability-based match predictions.
- **Forex:** technical-analysis signals (buy/sell/neutral) for EUR/USD, GBP/USD, USD/JPY, AUD/USD and USD/KES.

**Current status: Phases 1-7 done** (backend, Claude chat, sports analytics, dashboard, avatar & voice, simulated livestream & gamification, Docker deployment with PostgreSQL/Redis, CI). There is a FastAPI backend and a React + TypeScript admin dashboard. Chat is powered by **Anthropic Claude** when an API key is configured, with an offline rule-based engine as the fallback. By default all data is **simulated**: the team names and currency pairs are real, but every result, fixture and price is synthetic, and every API response and chat reply says so. Real football data from football-data.org can be switched on (see below). Forex prices are always simulated for now. The livestream runs on a **simulated audience**: there is no real platform connection yet (TikTok has no officially authorized live-comments API; see below). There is no betting or trading integration.

Predictions and signals are model estimates, not guarantees. They are not betting or financial advice.

### Forex compliance boundary

Publishing buy/sell calls with entry, stop-loss and take-profit levels to a public audience may count as regulated investment advice. In Kenya, the Capital Markets Authority (CMA) licenses investment advisers and forex brokers. So:

- Trade levels are **off by default** (`SOKOKALI_FOREX_TRADE_LEVELS_ENABLED=false`). Signals then show direction, strength, price and indicators only. Turn this on only after a licensing/legal review.
- Every forex reply carries a high-risk warning and says it is educational, not financial advice.
- "Guaranteed profit" requests are refused with a red-flag warning.
- There are no broker referrals, no account links and no trade execution.
- `SOKOKALI_FOREX_ENABLED=false` switches forex off completely.

## Requirements

- Windows 10/11 with PowerShell
- Python 3.12 or newer (`python --version`)
- Node.js 20.19+ or 22.12+ for the dashboard (`node --version`)

## Quick start with Docker (recommended)

With Docker Desktop running, from the repository root:

```powershell
docker compose up -d --build
```

Open http://localhost:8080. This starts the dashboard, the backend, PostgreSQL (predictions, everything said on air, and engagement state survive restarts) and Redis. Stop with `docker compose down`. See [docs/deployment.md](docs/deployment.md) for logs, configuration, monitoring and the Google Cloud plan.

## Quick start without Docker

After the one-time setup below, start everything from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

This opens two windows (backend on port 8000, dashboard on port 5173) and then opens http://localhost:5173 in your browser. Type a message in **Live chat**, or click a suggestion. Close the two windows to stop.

## Setup (Windows PowerShell)

Run these from the repository root (the folder that contains this README):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Optional: copy the example configuration and edit it:

```powershell
Copy-Item ..\.env.example ..\.env
```

### Turn on Claude (optional)

Without a key, Sokokali uses its offline rule-based engine. To use Claude:

1. Create the `.env` file as above, then open it: `notepad ..\.env`
2. Fill in `ANTHROPIC_API_KEY=` with your key from https://console.anthropic.com/ and save. `.env` is git-ignored. Never commit it or paste the key into chat.
3. Check it works (from the `backend` folder):

```powershell
.\.venv\Scripts\python.exe -m app.cli
```

The banner should say `Conversation engine: Claude claude-opus-5-5`, and replies should be tagged `[llm]`. If they are tagged `[rules]`, Claude was unavailable. The server log (`llm_unavailable` / `llm_fallback_to_rules`) and `GET /api/v1/status` (`ai_engine`) say why.

Each Claude reply is a paid API call (model `claude-opus-5-5`, effort `low`). Chat is rate-limited per client (`SOKOKALI_CHAT_RATE_LIMIT_PER_MINUTE`).

## Real football data (optional)

1. Get a free API key at https://www.football-data.org/client/register.
2. In `.env`, set `SOKOKALI_SPORTS_PROVIDER=football_data` and `FOOTBALL_DATA_API_KEY=<your key>`. Optionally change `SOKOKALI_FOOTBALL_DATA_COMPETITIONS` (default `["PL"]`, the Premier League).
3. Restart the backend. `GET /api/v1/status` should show `sports_provider: football-data.org (live data)`, and replies stop carrying the simulated-data notice.

Sokokali downloads the current and previous season once, then reuses the data for 5 minutes (`SOKOKALI_SPORTS_CACHE_TTL_SECONDS`). Requests have a 10 s timeout and up to 3 attempts with backoff. If a refresh fails, the last good data keeps being served and the status shows `degraded`. A bad key fails immediately rather than retrying. The Kenyan Premier League is not on football-data.org's free tier, so with real data only the configured competitions are covered.

## Model accuracy (backtesting)

From the `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m app.evaluate --calibration
```

This predicts every finished match using only the matches before it, then compares four models on the same matches: a frequencies baseline, Poisson, Elo and the live blend. It reports log loss, Brier score, accuracy and calibration. The same report is at `GET /api/v1/models/evaluation` and in the dashboard's **Model accuracy** panel. On simulated data the numbers only show the pipeline works. Switch to real data to judge the model.

## Run the API

From the `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Then open these in your browser:

| URL | What it shows |
|-----|---------------|
| http://127.0.0.1:8000/docs | Interactive API docs (Swagger UI). Use "Try it out" to call any endpoint |
| http://127.0.0.1:8000/health | Liveness check |
| http://127.0.0.1:8000/api/v1/status | Component status (shows that sports data is SIMULATED) |
| http://127.0.0.1:8000/api/v1/fixtures | Upcoming simulated fixtures |
| http://127.0.0.1:8000/api/v1/predictions/sim-epl-f001 | Prediction for the first fixture (Arsenal vs Chelsea) |
| http://127.0.0.1:8000/api/v1/forex/signals | Forex signals for every pair |
| http://127.0.0.1:8000/api/v1/forex/signals/USDKES | Forex signal for one pair |

Press `Ctrl+C` in the terminal to stop the server.

### Try the chat endpoint

In Swagger UI open **POST /api/v1/chat**, click **Try it out**, and send:

```json
{ "message": "Sokokali, Arsenal na Chelsea nani atashinda?", "viewer_id": "fan-1" }
```

Or from a second PowerShell window:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"message": "Sokokali, Arsenal na Chelsea nani atashinda?", "viewer_id": "fan-1"}'
```

Other messages to try: `Niaje msee! Gor vs Leopards nani atawin?`, `fixtures`, `Liverpool form`, `Gor Mahia results`, `Nipe sure bet ya leo`, and a follow-up such as `So who will win?` with the same `viewer_id`.

Forex messages: `EUR/USD signal`, `Nipe uchambuzi wa forex leo`, `Niaje msee, pauni iko aje?`, `USD/KES`, `Give me guaranteed forex profit`.

## Dashboard (React + TypeScript)

The dashboard lives in `frontend/` (React 19, TypeScript, Vite, Tailwind CSS). One-time setup:

```powershell
cd frontend
npm install
```

Start the backend (see "Run the API"), then in a **second** PowerShell window:

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. The dashboard shows:

- **Live chat:** send messages as a viewer. Each reply shows whether Claude or the rule-based engine answered, the language, the intent, prediction bars and forex signals.
- **System status:** online/offline, AI engine (Claude, paused or rule-based), each backend component, uptime, average API latency and the last chat reply time.
- **Fixtures & predictions:** click a match for its probabilities, expected goals and key factors.
- **Forex signals:** direction, strength, price and RSI for each pair, with the risk disclaimer.
- **Error log:** failed API requests from this browser session.
- **Avatar & voice:** a 3D Sokokali presenter that reads every chat reply aloud (see below).

### Live broadcast (simulated audience)

At the top of the dashboard, **Broadcast control** starts, pauses and stops a live show with simulated viewers. The viewers join, ask about the real fixtures and currency pairs, chat in English, Kiswahili and Sheng, like, follow, send gifts, answer trivia and vote in polls.

- **What Sokokali answers:** every comment is checked first. Duplicates, repeats, spam (more than 4 comments a minute per viewer), abuse and personal data are filtered out, and the panel shows the counts. The rest are queued by priority: real questions about matches and currencies first, first-time viewers get a boost, greetings wait. **Gifts never buy priority.** Questions older than 90 seconds are skipped rather than answered late.
- **No talking over itself:** the next answer waits until the previous one has been spoken (estimated from its length).
- **Segments:** in quiet moments, and at least every 3 minutes even when busy, Sokokali runs a match preview, free trivia, a forex outlook, a fans' poll or a responsible-gambling reminder. The **Run now** buttons trigger one immediately.
- **Pause** stops Sokokali talking but keeps receiving comments. **Stop** disconnects and clears the queue.
- **Live feed:** every viewer event, what happened to each comment (queued with its priority, or why it was filtered) and Sokokali's on-air replies.
- **Engagement:** community milestones (likes, viewers, comments) unlock cosmetic rewards. The presenter changes jersey (home, away, gold) and the studio changes look (floodlights, derby night). There is also a trivia round, poll votes and a free-participation leaderboard. **Points come only from free participation; gifts only trigger a celebration.**

**Admin token:** in development the controls work without one. Anywhere else, set `SOKOKALI_ADMIN_TOKEN` in `.env`. Admin endpoints refuse all requests until it is set, then require `Authorization: Bearer <token>`. Enter the same token in the dashboard's **Admin token** box. The live feed (WebSocket `/ws/live`) uses the same token.

**TikTok:** `SOKOKALI_LIVE_SOURCE=tiktok` exists, but it refuses to start. TikTok has no public, officially authorized API for live comments, and this project does not use reverse-engineered workarounds. When authorized access exists, only `backend/app/integrations/live/tiktok.py` needs implementing; the rest of the pipeline is ready. Platform webhooks or tests can also push events through `POST /api/v1/live/events`.

### Avatar & voice

Every chat reply is spoken by the 3D presenter in the **Avatar & voice** panel, with captions and lip sync. It uses the browser's free built-in voice (Web Speech API), so there is nothing to install or pay for.

- **Animations:** idle (breathing, blinking), speaking, commentary (for predictions, fixtures and forex) and celebration (for greetings, or the **Celebrate** button).
- **Voice:** picked automatically from the reply language (Kiswahili voices for Kiswahili/Sheng, Kenyan or British English otherwise). You can choose a specific voice and speed. Settings are remembered in this browser.
- **Kiswahili voices:** which voices exist depends on the browser and Windows. Microsoft Edge usually offers Kiswahili (Kenya) voices. The panel warns you when none is installed.
- **One reply at a time:** replies queue up instead of talking over each other (up to 5 waiting; **Skip** and **Stop** control the queue).
- **Fallbacks:** if the browser has no voice, the voice is muted, or the browser blocks audio (some browsers block sound until you click on the page; click **Test voice** once), Sokokali keeps "speaking" silently with captions and animation. Without WebGL, a simple 2D badge replaces the 3D presenter.
- **Simulated data** shows as a banner on the presenter, and is not read aloud on every reply.

The lip sync is approximate: browsers don't expose the speech audio, so the mouth follows the words being spoken, letter by letter, rather than the actual sound.

The dev server forwards `/api`, `/health` and `/ready` to the backend at `http://127.0.0.1:8000`. To use a different backend, create `frontend/.env.local` with `VITE_BACKEND_URL=http://host:port`.

Other commands (from `frontend/`): `npm test` (unit tests), `npm run typecheck`, `npm run build` (production build into `frontend/dist`).

## Terminal chat (no server)

```powershell
.\.venv\Scripts\python.exe -m app.cli
```

Type `demo` for a sample prediction, `forex` for signals, and `exit` to quit.

## Run the tests

From the `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## API endpoints (Phase 1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (returns 503 if the sports provider is down) |
| GET | `/api/v1/status` | Version, uptime and component status |
| POST | `/api/v1/chat` | Viewer message in, Sokokali reply out (rate-limited per client) |
| GET | `/api/v1/fixtures` | Upcoming fixtures and data freshness (`?limit=`, `?competition=`) |
| GET | `/api/v1/predictions/{match_id}` | Home/draw/away probabilities, expected goals, key factors |
| GET | `/api/v1/models/evaluation` | Walk-forward backtest: log loss, Brier score, accuracy, calibration (`?warmup=`, `?refit_every=`) |
| GET | `/api/v1/broadcast/status` | Broadcast state and live stats |
| POST | `/api/v1/broadcast/start` · `/pause` · `/stop` | Control the live show (admin) |
| POST | `/api/v1/broadcast/segments/{segment}` | Run trivia, poll, match_preview, forex or responsible_gambling now (admin) |
| POST | `/api/v1/live/events` | Inject a live event, e.g. from a platform webhook (admin) |
| GET | `/api/v1/gamification/status` | Milestones, trivia, poll, leaderboard, cosmetics |
| WS | `/ws/live` | Live feed: events, replies, game updates, state (admin token as `?token=`) |
| GET | `/api/v1/history/predictions` | Stored predictions with model versions (admin; needs a database) |
| GET | `/api/v1/history/broadcast` | Everything Sokokali said on air (admin; needs a database) |
| GET | `/metrics` | Prometheus metrics (admin outside development) |
| GET | `/api/v1/forex/pairs` | Supported currency pairs |
| GET | `/api/v1/forex/signals` | Signals for every pair |
| GET | `/api/v1/forex/signals/{symbol}` | Signal for one pair, e.g. `EURUSD` or `EUR-USD` |

Chat responses include `engine` (`llm` or `rules`) so you can see which engine answered.

Admin endpoints are marked (admin) and need the admin token outside development.

## Project layout

```text
backend/
  app/
    main.py                     FastAPI app factory, middleware, error handlers
    cli.py                      Terminal chat
    core/config.py              Settings from SOKOKALI_* environment variables / .env
    core/container.py           Builds and wires all services (dependency injection)
    core/logging.py             JSON structured logging
    core/rate_limit.py          Sliding-window rate limiter
    api/deps.py                 FastAPI dependencies
    api/routes/                 system.py, chat.py, sports.py endpoints
    schemas/                    Pydantic request/response and domain models
    integrations/sports/        Sports provider interface (base.py), simulated provider, football_data.py (real data)
    core/http.py                HTTP helper: timeouts, retries, backoff, Retry-After
    services/backtest.py        Walk-forward backtesting and calibration
    evaluate.py                 Backtest report on the command line
    integrations/forex/         Forex price provider interface (base.py) + simulated provider
    services/ai_engine.py       Language detection, intents, moderation, multilingual replies (rule-based)
    services/llm_engine.py      Claude conversation engine: tool loop, grounding check, fallback, cooldown
    services/llm_tools.py       Tools Claude can call (fixtures, predictions, form, head-to-head, forex)
    services/chat_service.py    Chat orchestration and grounding in sports data
    services/conversation_memory.py  Per-viewer bounded history with expiry
    services/sports_engine.py   Team lookup, fixtures, results (the chat's "tools")
    services/prediction_engine.py    Poisson + Elo prediction model
    services/speech_service.py  Speech cue per reply: speakable text, voice languages, avatar animation
    services/live_pipeline.py   Comment intake: dedup, rate limit, moderation, priority queue
    services/gamification.py    Milestones, cosmetics, trivia, polls, leaderboard
    services/broadcast_controller.py  The live show: answers, pacing, segments, reconnects
    services/live_hub.py        WebSocket fan-out
    services/compliance.py      Responsible-gambling reminders (betting boundary)
    integrations/live/          Live source interface, simulated audience, TikTok placeholder
    core/security.py            Admin token checks
    core/metrics.py             Prometheus metrics (/metrics)
    database/                   SQLAlchemy models and storage (PostgreSQL; SQLite in tests)
  Dockerfile
frontend/Dockerfile, nginx.conf  Dashboard image (nginx serves it and proxies API/WebSocket)
docker-compose.yml              Full local stack: frontend, backend, PostgreSQL, Redis
.github/workflows/ci.yml        CI: tests, type checks, security audits, Docker build + smoke test
docs/deployment.md              Running with Docker, monitoring, Google Cloud plan
    services/forex_engine.py    EMA/MACD/RSI/ATR signals, currency pair lookup, trade-level gate
  tests/                        pytest suite
frontend/
  src/
    App.tsx                     App root
    pages/Dashboard.tsx         Dashboard layout and live status polling
    components/                 ChatPanel, FixturesPanel, ForexPanel, StatusPanel, ErrorLogPanel, ...
    avatar/                     3D presenter (PresenterScene.tsx), speech queue + engines (speech.ts),
                                lip sync (lipSync.ts), useSpeech hook
    services/api.ts             Typed API client (timeouts, latency and error events)
    services/types.ts           TypeScript mirrors of the backend schemas
    hooks/                      usePolling, useRequestLog
  vite.config.ts                Dev server, API proxy, test setup
scripts/start-dev.ps1           Starts backend + dashboard and opens the browser
docs/                           progress.md, decisions.md
legacy/prototype-v0.1/          The original prototype, kept for reference
```

## How the Claude integration stays grounded

- Claude answers through **tools** that read the sports and forex services. It is told never to invent numbers.
- Before a reply is used, every percentage and decimal in it is checked against the tool results. If any number is unsupported, the reply is discarded and the rule-based engine answers from verified data instead.
- Abusive messages, personal data and "sure bet / guaranteed profit" requests never reach Claude. They get the fixed, safe answer.
- Disclaimers ("probabilities, not guarantees", forex risk warning, simulated-data notice) are added by the server, not left to the model.
- If Claude times out, is rate-limited, refuses or is down, the rule-based engine answers and Claude is paused for 30 seconds. Refusals are first retried on another model server-side (`fallbacks: "default"`).
- Viewer messages are passed to Claude as chat comments, not instructions. Conversation history is per `viewer_id`; anonymous messages get no history.

## Security notes

- Configuration comes from environment variables. There are no secrets in the code.
- Input is validated (message length, viewer ID format, match ID format).
- Messages with abuse or personal data (phone numbers, emails) are refused and not stored in memory.
- Do not expose this development server to the internet yet. Rate limits are per process, in memory, and there is no admin authentication or TLS yet.
