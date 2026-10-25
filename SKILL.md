---
name: soco-cali-builder
description: Design, implement, test, and deploy Soco Cali (also called Soko Kali or Soco Kali), a 24/7 autonomous AI sports livestream host. Use for architecture, backlog planning, Python backend code, sports prediction models, real-time chat ingestion, persona/LLM responses, voice/avatar synchronization, gamification, cloud operations, security, and compliant streaming integrations.
---

# Soco Cali Implementation Guide

## Mission and boundaries
Build an AI sports presenter that receives authorized live chat events, answers viewers naturally in English, Kiswahili or Sheng, retrieves current sports data, communicates calibrated predictions, and controls a speaking animated avatar. Support 24/7 *high availability*, not a promise of zero downtime. Treat the spellings Soco Cali, Soco Kali and Soko Kali as project aliases until the user chooses a canonical brand.

The skill guides engineering work; it does not itself run a persistent agent or grant API permissions. Do not claim an integration is supported without verifying official documentation and access. Do not present betting outcomes as guaranteed. Keep gamification separate from wagering, and do not reward betting deposits, losses, or stakes with gifts, privileges, or pressure.

## Interaction contract
1. Identify the component the user asks to implement. Respect the user's decision to control the sequence; do not automatically move to the next module.
2. Ask only for blockers (e.g. deployment cloud, authorized platform access, provider credentials). Otherwise state assumptions and implement a working vertical slice.
3. For every component, deliver: objective, interfaces, event/data schemas, implementation files, configuration, tests, security controls, deployment/run commands, acceptance criteria, and unresolved dependencies.
4. Prefer executable, tested code over pseudocode when implementation is requested. Never embed credentials; use environment variables and secret managers.
5. Separate verified facts from proposed targets and assumptions. Keep architecture decisions and status in `docs/decisions.md` and `docs/progress.md` when a repository exists.

## Reference architecture
`Authorized Platform Adapter -> Event Bus -> Moderation/Queue -> Conversation Orchestrator -> Sports Data Cache/Prediction API -> Response Validator -> Streaming TTS -> Avatar Renderer -> Broadcast Encoder -> Platform`.

Parallel services: `Gamification Service`, `PostgreSQL`, `Redis`, `Observability`, `Admin Control Plane`, `Scheduler`, `Secrets Manager`.

Start as a modular Python FastAPI application with background workers and managed PostgreSQL/Redis. Split into independently deployed services only when load testing shows need. Prefer cloud-managed queues over self-hosted Kafka for MVP. Use idempotency keys for duplicated chat/gift events.

## Work packages
### A. Chat intake and orchestration
- Define normalized `LiveEvent`: `event_id`, `platform`, `stream_id`, `viewer_id_hash`, `kind`, `text`, `received_at`, `platform_timestamp`, `metadata`.
- Verify event authenticity and permission. Use official authorized APIs where possible; do not bypass access controls or anti-bot measures.
- Rate-limit, deduplicate, filter abuse and personal information, prioritize unique useful questions, and enforce response cooldowns.
- Route intents: match facts, fixtures, predictions, greetings, trivia, moderation, unsupported requests.
- Keep bounded conversation context with TTL and explicit privacy retention policies.

### B. Sports ingestion and predictions
- Normalize fixture/team/player IDs across provider feeds; attach provider, source timestamp, ingestion timestamp and freshness TTL to each fact.
- Use a baseline football model (Poisson expected-goals + home advantage; optionally Elo), then compare against stronger calibrated models such as gradient boosting.
- Train and evaluate using chronological splits; avoid future-data leakage. Report log loss, Brier score, calibration, class distribution, and performance by league/season.
- Produce probabilities for home/draw/away that sum to 1 within tolerance. Include `model_version`, `as_of`, `data_freshness`, `confidence_notes`, and supporting factors.
- Do not fabricate injuries, live scores or predictions if feeds are unavailable. Fall back to labeled historical analysis or decline.

### C. Persona and response generation
- Maintain configurable persona: energetic, informative sports presenter; multilingual English/Kiswahili/Sheng when appropriate.
- Pass structured verified match facts and prediction outputs to the LLM; prohibit it from inventing facts or changing numerical probabilities.
- Label predictions as uncertain and explain assumptions in plain language. Check final response for grounding, moderation, length, and TTS suitability.

### D. Voice, avatar and broadcast
- Convert validated responses to streaming TTS; provide audio chunks and timing/phoneme or viseme cues to avatar renderer.
- Queue speech with interrupt/cancel capability and backpressure; prevent overlapping responses.
- Mix audio/video with FFmpeg or a supported broadcaster; test platform ingest and permissions independently.
- Maintain fallback scenes and prerecorded neutral transitions when upstream services fail.

### E. Gamification
- Accept only verified comments/likes/gifts, with idempotent event processing.
- Offer free community goals, trivia, polls, cosmetic avatar upgrades and optional thank-you effects. Avoid manipulative incentives or pay-to-win prediction accuracy.
- Keep gift processing separate from sports prediction and betting/referral logic. Enforce platform policies and jurisdictional advertising restrictions.

### F. Cloud and operations
- Containerize services; configure readiness/liveness probes, autoscaling, circuit breakers, retries with jitter, quotas, API budgets, distributed tracing and alerting.
- Use managed secrets, TLS, least-privilege service identities, encryption at rest, minimal viewer data retention, audit logs, and admin kill switch.
- Set measurable SLOs after testing: initial target 99.9% monthly service availability, plus per-stage p50/p95 latency, freshness and error budgets. Avoid promising uninterrupted service.
- Add staging, CI tests, infrastructure-as-code, backups, restoration drills, rolling deployments and failover playbooks.

## Implementation order and definition of done
Use incremental vertical slices, subject to user direction:
1. Repo scaffold, typed schemas, local Docker Compose and simulated chat stream.
2. Sports provider adapter, cache, baseline prediction API and backtests.
3. Moderated conversation orchestrator and structured response validator.
4. TTS, avatar renderer and local broadcast preview.
5. Authorized platform integration and interactive event handling.
6. Gamification, admin console, observability, load/security testing and cloud deployment.

A slice is complete only when its happy path and failure modes are tested, sample payloads and `.env.example` are supplied, and a developer can run it from a clean checkout. For deployment or commercial betting integrations, verify current provider terms, local laws, age restrictions and advertising rules before enabling.

## Default repository layout
```text
soco-cali/
  apps/api/                 # FastAPI entrypoint
  services/chat/            # platform adapters, moderation, orchestration
  services/sports/          # ingestion, features, prediction
  services/media/           # TTS, avatar and encoder integration
  services/gamification/    # events, milestones and cosmetics
  packages/contracts/       # Pydantic schemas and event versions
  infra/                    # containers, IaC, CI
  tests/                    # unit, contract, integration, load
  docs/decisions.md
  docs/progress.md
  .env.example
```

## Output format for implementation turns
State `Component`, `Assumptions`, `Design`, `Files/Code`, `Run and Test`, `Acceptance Criteria`, `Risks/Dependencies`, and `Next user decision`. When the user asks only for planning, avoid creating code without permission.
