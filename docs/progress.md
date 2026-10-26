# Sokokali progress

## Phase 1: Backend foundation (complete, awaiting approval)

Done:
- Refactored the prototype into a `backend/app` FastAPI package with an app factory and dependency container.
- Environment-based settings (`SOKOKALI_*`), JSON structured logging, request IDs and latency logging.
- Endpoints: `/health`, `/ready`, `/api/v1/status`, `/api/v1/chat`, `/api/v1/fixtures`, `/api/v1/predictions/{match_id}`, plus OpenAPI docs at `/docs`.
- Simulated sports provider: deterministic seeded season for two simulated leagues (8 teams each, 112 results) and 8 upcoming fixtures, all flagged `is_simulated`.
- Prediction engine: shrunk attack/defence strengths, Poisson expected goals, Elo with goal-difference multiplier, a 70/30 blend, team form and explanatory factors. Probabilities sum to 1.
- Rule-based chat: English/Kiswahili/Sheng detection, intent classification, team alias matching, moderation (abuse, personal data), refusing "sure bet"/fixed-match requests, per-viewer conversation memory for follow-ups, and per-client rate limiting.
- Forex signals (added after the first push): simulated hourly prices for 5 pairs (including USD/KES), an EMA20/50 + MACD + RSI signal engine with ATR-based stop/target, and `/api/v1/forex/*` endpoints. Chat handles forex in all three languages. Trade levels are behind a licensing flag (off by default), every reply has a risk warning, and "guaranteed profit" requests are refused.
- Terminal chat (`python -m app.cli`), carrying over the prototype's `demo` command.
- 81 automated tests (unit and API).

Known limitations:
- The rule-based language detection and intents are keyword heuristics.
- In chat replies, rounded percentages can add up to 99% or 101%. The structured `prediction` field sums to exactly 1.
- Memory and rate limits are in-process (Redis is planned).
- Neither the football model nor the forex signal has been backtested or calibrated (Phase 3). Forex `strength` counts how many indicators agree; it is not a win probability.

## Phase 2: Conversational intelligence (complete, awaiting approval)

Done:
- Anthropic Claude (`claude-opus-5-5`, effort `low`) via the official `anthropic` SDK (async client, 30 s timeout, 2 SDK retries), chosen by `SOKOKALI_LLM_PROVIDER` (`auto`/`anthropic`/`none`).
- Five strict tools: upcoming fixtures, match prediction, team form, head-to-head, forex signal. Manual tool loop (max 4 rounds), with parallel tool calls run concurrently.
- Grounding check: replies with percentages/decimals not found in tool results are rejected and answered by the rule-based engine.
- Server-side refusal fallback (`fallbacks: "default"`), refusal/max_tokens handling, a 30 s cooldown after API outages, and a concurrency limit of 8 Claude calls.
- Per-viewer conversation memory sent as text history (last 6 turns). Stable system prompt and tools (cache-friendly, append-only).
- Moderation and guarantee requests stay deterministic and never reach Claude. Disclaimers are appended by the server.
- `engine` field on chat responses; `ai_engine` status shows Claude, degraded or rules-only.
- 13 new tests using a scripted fake client (94 total). The invalid-key path was checked against the real API (401, then fallback to rules).

Not yet verified:
- A live reply from Claude with a real key (no key is configured on this machine). Run `python -m app.cli` after adding `ANTHROPIC_API_KEY` to `.env`.

Known limitations:
- Language detection is still the keyword heuristic. Claude replies in the detected language.
- The grounding check covers percentages and decimals, not whole numbers (scores, dates, Elo).
- Conversation memory is in-process. Redis comes later.

## Phase 4: Dashboard (complete, awaiting approval)

Built ahead of Phase 3, at the user's request, so the bot can be seen responding.

Done:
- `frontend/`: React 19 + TypeScript 5.9 + Vite 8 + Tailwind CSS 4.
- Live chat (viewer ID, reply-language override, suggestions, engine/language/intent/simulated badges, prediction bars, forex chips).
- System status (component health polled every 10 s, uptime, average API latency, last chat reply time), online/offline and AI-engine indicators in the header.
- Fixtures & predictions (click a fixture to load its prediction), forex signals table, error log, "coming next" card for avatar/broadcast/gamification.
- Typed API client with timeouts (10 s, 60 s for chat) and request events for latency and the error log; the Vite dev proxy means no CORS setup is needed.
- `scripts/start-dev.ps1` starts the backend and dashboard and opens the browser.
- 13 frontend tests (Vitest + Testing Library). Type-check and production build pass. Verified through the dev proxy against the running backend (status, chat, forex).

Not yet built (needs backend features first):
- Broadcast start/pause/stop controls and admin login (Phase 6), the WebSocket live feed (Phase 6), avatar preview and speech status (Phase 5), gamification milestones (Phase 6).

Not yet verified:
- No visual check in a real browser by me (no browser tool in this session), and `scripts/start-dev.ps1` was syntax-checked but not run.

## Phase 3: Sports analytics (complete, awaiting approval)

Done:
- football-data.org v4 provider (`SOKOKALI_SPORTS_PROVIDER=football_data`): current + previous season per competition, live/scheduled/finished parsing, team aliases, in-memory snapshot cache with TTL. Serves stale data when a refresh fails and reports `degraded` status.
- Shared HTTP helper: timeouts, exponential backoff with jitter, `Retry-After`, no retries on 4xx other than 408/425/429.
- Prediction engine split into `fit_model` / `estimate`. Fitted models are cached per data snapshot, and teams without history are rated as league average (instead of an error).
- Walk-forward backtest (no future data): baseline vs Poisson vs Elo vs blend, with log loss, Brier score, accuracy and 10-bin calibration. Available via `python -m app.evaluate`, `GET /api/v1/models/evaluation` (cached per data snapshot, run off the event loop) and the dashboard's Model accuracy panel.
- Chat keeps working if the sports provider is down (team lookup degrades to "no teams found").
- 18 new backend tests (112 total) with mocked HTTP, plus 1 new frontend test (14 total). Real-network check: football-data.org was reached, and an invalid key was rejected (HTTP 400) and handled.

Not yet verified:
- A real download with a valid football-data.org key (none configured here).

Known limitations / deferred:
- On simulated data the blend beats the baseline (log loss 1.016 vs 1.088 over 72 matches), but 72 matches is too few to draw conclusions. Re-run on real data.
- scikit-learn / XGBoost models are not added: with one or two seasons per league, the explainable Poisson/Elo baseline comes first. Add a gradient-boosted model only if a backtest on real data shows it beats the blend.
- Prediction history is not stored yet (needs the PostgreSQL work in Phase 7). Forex prices are still simulated only.

## Next: Phase 5, avatar & voice (not started; needs approval)
