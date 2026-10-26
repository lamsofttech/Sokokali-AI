# Sokokali

Sokokali is an AI-powered sports and markets presenter for a Kenyan audience. It chats in English, Kiswahili and Sheng. It covers two markets:

- **Football:** fixtures, results, team form and probability-based match predictions.
- **Forex:** technical-analysis signals (buy/sell/neutral) for EUR/USD, GBP/USD, USD/JPY, AUD/USD and USD/KES.

**Current status: Phase 4 (dashboard).** There is a FastAPI backend and a React + TypeScript admin dashboard. Chat is powered by **Anthropic Claude** when an API key is configured, with an offline rule-based engine as the fallback. All data is **simulated**: the team names and currency pairs are real, but every result, fixture and price is synthetic, and every API response and chat reply says so. No livestream, avatar, betting or trading integration exists yet.

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

## Quick start: see the bot respond

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
| GET | `/api/v1/forex/pairs` | Supported currency pairs |
| GET | `/api/v1/forex/signals` | Signals for every pair |
| GET | `/api/v1/forex/signals/{symbol}` | Signal for one pair, e.g. `EURUSD` or `EUR-USD` |

Chat responses include `engine` (`llm` or `rules`) so you can see which engine answered.

The broadcast, gamification and WebSocket endpoints come in later phases. Admin authentication arrives with the broadcast control endpoints, since Phase 1 has no administrative actions.

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
    integrations/sports/        Sports provider interface (base.py) + simulated provider
    integrations/forex/         Forex price provider interface (base.py) + simulated provider
    services/ai_engine.py       Language detection, intents, moderation, multilingual replies (rule-based)
    services/llm_engine.py      Claude conversation engine: tool loop, grounding check, fallback, cooldown
    services/llm_tools.py       Tools Claude can call (fixtures, predictions, form, head-to-head, forex)
    services/chat_service.py    Chat orchestration and grounding in sports data
    services/conversation_memory.py  Per-viewer bounded history with expiry
    services/sports_engine.py   Team lookup, fixtures, results (the chat's "tools")
    services/prediction_engine.py    Poisson + Elo prediction model
    services/forex_engine.py    EMA/MACD/RSI/ATR signals, currency pair lookup, trade-level gate
  tests/                        pytest suite
frontend/
  src/
    App.tsx                     App root
    pages/Dashboard.tsx         Dashboard layout and live status polling
    components/                 ChatPanel, FixturesPanel, ForexPanel, StatusPanel, ErrorLogPanel, ...
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
