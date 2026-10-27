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
- `scripts/start-dev.ps1` was syntax-checked but not run. (Update, Phase 5: the dashboard was later screenshotted in headless Microsoft Edge and renders correctly.)

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

## Phase 5: Avatar & voice (complete, awaiting approval)

Done:
- Backend speech cue on every chat reply (`speech`): text cleaned for TTS (on-screen notices removed, `EUR/USD` -> `EUR USD`, scores and "vs" read naturally), BCP 47 voice languages per reply language, avatar animation per intent, simulated-data banner flag.
- 3D presenter (React Three Fiber + three.js) built from primitives: Kenya-coloured jersey, studio desk and pitch, idle/speaking/commentary/celebration animations with smooth blending, blinking, head motion, microphone. Loaded lazily (three.js is a separate ~243 kB gzipped chunk), with a 2D fallback when WebGL is missing or the scene crashes.
- Free text-to-speech via the Web Speech API: automatic voice choice by language, manual voice and speed (saved in localStorage), mute.
- Speech queue: one reply at a time, max 5 waiting (oldest dropped), skip/stop, watchdog for browsers that never fire `end`, and fallback to a silent engine (captions + animation) when the voice fails or is blocked.
- Basic lip sync from word-boundary events (per-letter mouth shapes), with a talking rhythm when the voice gives no word events.
- Avatar & voice panel on the dashboard: live preview, captions, simulated banner, speaking/queued status, voice warnings, Test voice / Celebrate / Skip / Stop.
- 4 new backend tests (116 total), 18 new frontend tests (32 total). Type-check and build pass. Headless Edge (SwiftShader WebGL) screenshot confirms the dashboard and 3D presenter render.

Not yet verified:
- Audio output and lip sync timing in a real browser with speakers (headless screenshots can't check sound or motion). Kiswahili voice availability depends on your browser/Windows voices.

Known limitations:
- The presenter is a demonstration character made of simple shapes; a rigged, realistic character can replace `Presenter` later without changing the speech logic.
- Lip sync follows words and letters, not the audio waveform (the browser doesn't expose it). A paid TTS with viseme/timestamp output would allow true audio-driven lip sync.
- Speech happens in the dashboard browser only; sending the presenter to OBS/livestream output is part of Phase 6/7.

## Phase 6: Livestream & gamification (complete, awaiting approval)

Done:
- Normalized `LiveEvent` contract and `LiveEventSource` interface (with a fail-fast `check`). Simulated audience: joins, comments about real fixtures/pairs in en/sw/Sheng, likes, gifts, follows, shares, trivia answers, poll votes, plus duplicates, spam and moderated content. TikTok placeholder refuses to start (no authorized API).
- Comment pipeline: event-ID dedup, repeated-comment filter, per-viewer rate limit, moderation, game answers kept out of the question queue, priority queue (questions about teams/pairs and first-time viewers first; gifts give no priority), bounded queue that drops the lowest priority, stale-question expiry.
- Gamification: community milestones unlocking cosmetic outfits/backgrounds, 11 bilingual trivia questions, fans' polls (1/X/2 or team name, one vote each), free-participation leaderboard; gifts give a confetti/celebration effect only.
- Broadcast controller: start/pause/resume/stop, one answer at a time paced by estimated speaking time, segments in quiet moments and at least every 3 minutes, source reconnect with exponential backoff, alerts, error isolation per step, clean shutdown.
- Responsible-gambling reminders (en/sw/Sheng) as a segment; no wagering/deposit/betting-link code (compliance boundary).
- Admin token auth (Bearer header / WS query), open only in development/test, fail-closed otherwise. Endpoints: broadcast status/start/pause/stop/segments, live event injection, gamification status, `/ws/live`.
- Dashboard: Broadcast control (with admin token), Live feed, Engagement panel. The avatar speaks broadcast replies, celebrates gifts/milestones and wears unlocked cosmetics. WebSocket reconnects with backoff.
- 26 new backend tests (138 total), 8 new frontend tests (40 total). Verified end to end in headless Edge through the Vite proxy: 3-minute simulated show, 378 events, 11 answers, 6 segments, cosmetics unlocked, 0 errors.

Not yet verified:
- Audio playback during the broadcast on a real browser with speakers (headless blocks audio; the captions-only fallback was confirmed instead).

Known limitations:
- State (queue, points, milestones) is in-process and resets on restart; Redis/PostgreSQL come in Phase 7.
- The backend estimates speaking time from word count; the browser's actual voice may be faster or slower.
- No real platform connector: TikTok needs authorized access; YouTube/Twitch official APIs are possible future connectors.

## Phase 7: Deployment (local Docker; Google Cloud planned) (complete, awaiting approval)

Done:
- PostgreSQL persistence (SQLAlchemy 2.0 async): prediction history (deduplicated, with model version and data date), broadcast log of everything said on air, and an engagement snapshot restored on startup. Writes run in the background and never break the show. Startup retries while the database boots, then falls back to memory.
- Redis-backed sliding-window rate limit shared across restarts/replicas, falling back to in-memory if Redis is down.
- Prometheus `/metrics` (HTTP by route, chat replies by engine/intent, live events, queue, WebSocket clients, broadcast state/errors). `/ready` checks the database and Redis. Status shows database/redis components. Admin history endpoints.
- Dockerfiles (non-root backend with health check and graceful shutdown; nginx-unprivileged dashboard with an API/WebSocket proxy and security headers incl. CSP), and `docker-compose.yml` with PostgreSQL 17 and Redis 7, health-gated startup, restart policies, volumes, localhost-only ports.
- GitHub Actions CI: backend tests + pip-audit, frontend typecheck/tests/build + npm audit, Docker build and a smoke test of the running stack.
- `docs/deployment.md`: local operations, monitoring, storage, Google Cloud mapping (Cloud Run single instance, Cloud SQL, Memorystore, Secret Manager, Cloud Build).
- 8 new backend tests (146 total, stable over repeated runs); frontend still 40 (one live-feed ordering bug fixed and covered).
- Verified locally: all four containers healthy; through nginx: readiness (database and redis true), chat, a broadcast over the WebSocket, stored history, metrics and CSP headers. The 3D dashboard renders under the CSP, and engagement state was restored after `docker compose restart backend`. The stack ran healthy for 8+ hours. pip-audit and npm audit: no known vulnerabilities.

Not yet verified:
- The CI workflow itself runs on GitHub after the push (it was not executed locally as a workflow).
- Google Cloud deployment (planned, not done).

Known limitations:
- Schema changes need Alembic migrations before real data accumulates (tables are only created, never altered).
- One backend instance by design (the broadcast state is in-process).

## Going live on TikTok: moderator relay + stage view (complete)

Chosen over reverse-engineering TikTok's private API (account risk; against the project's no-bypass rule).

Done:
- Audience choice per show (`simulated`, `relay`, `tiktok`), switchable while stopped (`POST /api/v1/broadcast/start?audience=relay`).
- `POST /api/v1/live/relay` (admin): a moderator relays a real viewer's comment/gift/join/follow. It gets a stable hashed viewer ID per username and goes through the full pipeline.
- Dashboard Moderator relay panel: single entry with Enter-to-send, bulk paste of `username: comment` lines, and a per-comment result (queued with priority, or the filter reason).
- Stage view (`/?view=stage`, portrait `&layout=portrait`): full-window presenter with large captions for TikTok LIVE Studio capture, a click-to-enable-voice overlay, and automatic muting of dashboard tabs while a stage is open (no double audio).
- Guide: docs/going-live-on-tiktok.md.
- 2 new backend tests (148), 4 new frontend tests (44). Verified on the Docker stack: relay comment answered on air, gift thanked; stage view rendered in landscape and portrait.

Not yet verified:
- An actual TikTok LIVE Studio capture with audio (needs your TikTok account with LIVE access).
- Headless screenshots show a black band because headless Edge reports a smaller viewport than it captures; this is not expected in a real window, but check the stage fills the window when you first open it.

## Football history database and training dataset (complete)

Direction from the client: the team makes the predictions; Sokokali presents them and must be an expert on football history (and markets) to help analysts decide. The model is trained on the data as worked analyses, and always checks exact numbers with tools.

Done:
- `historical_matches` table plus an ingest from football-data.co.uk: all 34 EPL seasons (1993/94 to the current season), 12,774 matches with results, half-time scores, shots, corners, fouls, cards, referees and market odds. Cached downloads, CLI (`python -m app.history.ingest`) and an admin refresh endpoint.
- Analysis engine: all-time head-to-head, team stats by venue and seasons, form and streaks, league table for any season or date, season-by-season history. Verified against known records (Arsenal 2003/04 26-12-0 90 pts; Liverpool 2024/25 84 pts; Man United 1993/94 92 pts and 1999/00 91 pts).
- `/api/v1/football/*` endpoints and three new Claude tools (all-time head-to-head, team history stats, league tables).
- Grounding check now treats goal lines (0.5, 1.5, 2.5, ...) as market names, not statistics. Before this, a Claude reply mentioning "over 2.5 goals" was wrongly discarded.
- Training dataset builder (`python -m app.training.dataset`): 1,766 grounded conversations (head-to-heads, team stats, champions, finishes, guardrails) in English/Kiswahili/Sheng, 0 rejected, with a deterministic train/eval split.
- `training/finetune_qlora.py` (QLoRA, completion-only loss on the assistant tool-call and answer turns, push to the Hugging Face Hub, `--dry-run`) and `training/README.md`.
- Dry run with the real Qwen3-8B and Qwen2.5-7B chat templates: 1,679 conversations become 3,215 training pairs, 0 skipped, max 3,480 tokens.
- 12 new backend tests (160 total).

Not yet done / verified:
- Actual GPU training (no NVIDIA GPU on this machine). Run it on Colab, Google Cloud or Hugging Face per training/README.md.
- Serving the fine-tuned model and plugging it into Sokokali next to Claude. An evaluation script for the fine-tuned model.
- Expert picks (the team's predictions) in the database, the Analyst workspace, and forex history data for training.

## Next: expert picks + analyst workspace, model serving/evaluation, Google Cloud (needs decisions)
