# Sokokali progress

## Phase 1: Backend foundation (complete, awaiting approval)

Done:
- Refactored the prototype into a `backend/app` FastAPI package with an app factory and dependency container.
- Environment-based settings (`SOKOKALI_*`), JSON structured logging, request IDs and latency logging.
- Endpoints: `/health`, `/ready`, `/api/v1/status`, `/api/v1/chat`, `/api/v1/fixtures`, `/api/v1/predictions/{match_id}`, plus OpenAPI docs at `/docs`.
- Simulated sports provider: deterministic seeded season for two simulated leagues (8 teams each, 112 results) and 8 upcoming fixtures, all flagged `is_simulated`.
- Prediction engine: shrunk attack/defence strengths, Poisson expected goals, Elo with goal-difference multiplier, a 70/30 blend, team form and explanatory factors. Probabilities sum to 1.
- Rule-based chat: English/Kiswahili/Sheng detection, intent classification, team alias matching, moderation (abuse, personal data), refusing "sure bet"/fixed-match requests, per-viewer conversation memory for follow-ups, and per-client rate limiting.
- Terminal chat (`python -m app.cli`), carrying over the prototype's `demo` command.
- 58 automated tests (unit and API).

Known limitations:
- The rule-based language detection and intents are keyword heuristics.
- In chat replies, rounded percentages can add up to 99% or 101%. The structured `prediction` field sums to exactly 1.
- Memory and rate limits are in-process (Redis is planned).
- The model has not been backtested or calibrated (Phase 3).

## Next: Phase 2, conversational intelligence (not started; needs approval)
