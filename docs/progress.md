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

## Next: Phase 3, sports analytics (not started; needs approval)
