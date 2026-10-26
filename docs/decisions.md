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
