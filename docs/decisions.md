# Architecture decisions

## D1: Modular monolith first (Phase 1)
One FastAPI process with clear service boundaries (`services/`, `integrations/`). We split into separate services only if load testing shows a need. Rejected: microservices from day one, which add operational cost with no benefit at this stage.

## D2: Provider interface for sports data
All services depend on `SportsDataProvider`. The simulated provider is the default, so the app runs offline. Real providers in Phase 3 implement the same interface. Every response carries `DataFreshness.is_simulated`.

## D3: Rule-based NLU before the LLM
Phase 1 uses deterministic templates, so every number comes from verified data and the tests are deterministic. The Phase 2 LLM will sit behind the same `ChatService` flow. It will get sports lookups as tools and will not be allowed to change numbers.

## D4: Baseline prediction model = Poisson + Elo blend
This model is transparent, explainable and needs only scores. It is a baseline to beat with calibrated models (for example gradient boosting) in Phase 3, measured by log loss and Brier score on chronological splits.

## D5: No SQLAlchemy/PostgreSQL/Redis in Phase 1
Nothing in Phase 1 needs persistence. We add these when there is something to store (prediction history, conversation memory, shared rate limits), so we don't install unused dependencies.

## D6: Legacy prototype archived, not deleted
The original root-level scripts are in `legacy/prototype-v0.1/`. Their behaviour (Poisson maths, greeting replies, refusing to invent scores, CLI `demo`) is carried into the new backend.

## D7: Forex signals behind a compliance boundary
Forex is a second market next to football, built the same way: a provider interface with a simulated provider, plus a separate signal engine. Publishing entry/stop/target levels to the public may be regulated investment advice (Kenya: Capital Markets Authority), so `forex_trade_levels_enabled` defaults to false. Every forex reply carries a risk warning, and there is no broker referral or trade execution. Signals are rule-based technical analysis (EMA trend, MACD momentum, RSI) because it is explainable. We will adopt a more complex model only if Phase 3 backtesting shows it beats this baseline.

## D8: Claude with tools, behind a rule-based fallback
Claude (`claude-opus-5-5`) writes replies, but only from tool results backed by the sports/forex services, and a grounding check rejects replies with unsupported numbers. The rule-based engine stays as the fallback for outages, refusals and failed checks, so the stream never goes silent and never airs invented numbers. We use a manual tool loop instead of the SDK's beta tool runner because we need the tool outputs (prediction and signal objects) for the API response, and a hard cap on rounds. Effort is `low` because replies are short and latency matters on a livestream. Moderation and "guarantee" requests stay deterministic and never reach the model. Rejected: letting the model answer without tools (it can hallucinate fixtures and odds), and sending all traffic to Claude with no fallback (one outage would stop the stream).

## D9: Single-page dashboard with polling and a dev proxy
The Phase 4 dashboard is one React page (no router) polling the REST API: status every 10 s, fixtures and signals every minute. We will switch to the `/ws/live` WebSocket when the broadcast feed exists (Phase 6). The Vite dev server proxies `/api` to the backend, so the browser talks to one origin. No new state or data-fetching libraries: React state plus two small hooks cover the current needs. TypeScript stays on 5.9 instead of 7.0 for tooling compatibility.
