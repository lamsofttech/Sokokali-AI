# Sokokali

Sokokali is an AI-powered sports presenter for a Kenyan audience. It chats in English, Kiswahili and Sheng, answers questions about fixtures, results and team form, and gives probability-based football predictions.

**Current status: Phase 1 (backend foundation).** Only the backend exists so far. All sports data is **simulated**: the team names are real clubs, but every result and fixture is synthetic, and every API response and chat reply says so. No LLM, livestream, avatar or betting integration exists yet.

Predictions are model estimates, not guarantees, and are not betting advice.

## Requirements

- Windows 10/11 with PowerShell
- Python 3.12 or newer (`python --version`)

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

## Terminal chat (no server)

```powershell
.\.venv\Scripts\python.exe -m app.cli
```

Type `demo` for a sample prediction and `exit` to quit.

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
    integrations/sports/        Provider interface (base.py) + simulated provider
    services/ai_engine.py       Language detection, intents, moderation, multilingual replies
    services/chat_service.py    Chat orchestration and grounding in sports data
    services/conversation_memory.py  Per-viewer bounded history with expiry
    services/sports_engine.py   Team lookup, fixtures, results (the chat's "tools")
    services/prediction_engine.py    Poisson + Elo prediction model
  tests/                        pytest suite
docs/                           progress.md, decisions.md
legacy/prototype-v0.1/          The original prototype, kept for reference
```

## Security notes

- Configuration comes from environment variables. There are no secrets in the code.
- Input is validated (message length, viewer ID format, match ID format).
- Messages with abuse or personal data (phone numbers, emails) are refused and not stored in memory.
- Do not expose this development server to the internet yet. Rate limits are per process, in memory, and there is no admin authentication or TLS yet.
