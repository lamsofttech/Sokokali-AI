# Deploying Sokokali

## 1. Locally with Docker (what runs today)

Requirements: Docker Desktop (Windows/macOS) or Docker Engine (Linux).

```powershell
cd "C:\Users\Local User\Desktop\SOKO"
Copy-Item .env.example .env      # once; add your keys (optional)
docker compose up -d --build     # build and start everything
docker compose ps                # all four services should be "healthy"
```

Open http://localhost:8080 (dashboard). The API docs are at http://localhost:8080/docs.

| Service | What it is | Port |
|---|---|---|
| `frontend` | nginx serving the dashboard and proxying `/api`, `/ws`, `/health`, `/ready`, `/metrics`, `/docs` | 127.0.0.1:8080 |
| `backend` | FastAPI app (one worker; see "Scaling" below) | 127.0.0.1:8000 |
| `postgres` | PostgreSQL 17: predictions, broadcast log, engagement state | internal only |
| `redis` | Redis 7: shared rate limits | internal only |

Ports are bound to `127.0.0.1`, so nothing is reachable from your network.

Everyday commands:

```powershell
docker compose logs -f backend          # follow the backend logs
docker compose restart backend          # restart one service (state is restored from PostgreSQL)
docker compose up -d --build            # rebuild after code changes
docker compose down                     # stop (data is kept in Docker volumes)
docker compose down -v                  # stop AND delete all stored data
```

### Configuration

The backend reads `.env` (see `.env.example`). Docker Compose sets `SOKOKALI_DATABASE_URL`, `SOKOKALI_REDIS_URL` and `SOKOKALI_CORS_ORIGINS` itself. To change the local database password, set `POSTGRES_PASSWORD=...` in `.env` **before** the first `docker compose up`. Once the volume exists, the password is fixed until you `down -v`.

### Health, readiness and monitoring

- `GET /health`: the process is alive (used by Docker's health check).
- `GET /ready`: the data providers, PostgreSQL and Redis are reachable (503 otherwise).
- `GET /api/v1/status`: per-component status for the dashboard.
- `GET /metrics`: Prometheus metrics. These cover HTTP requests and latency by route, chat replies by engine and intent, live events by kind, queue size, WebSocket clients, and broadcast running/errors. Open in development; outside it, send the admin token.
- Logs are JSON, one line per event, with request IDs.
- Restart policy: `unless-stopped` for every service. The backend waits for healthy PostgreSQL and Redis. On shutdown it stops the broadcast, saves the engagement snapshot and flushes pending writes (20 s grace period).

### What is stored

| Table | Contents |
|---|---|
| `predictions` | Every distinct prediction: match, probabilities, expected goals, model version, data source and date, simulated or not |
| `broadcast_log` | Everything Sokokali said on air: source (viewer, trivia, ...), the viewer's comment, the reply, the engine |
| `gamification_snapshot` | Points, milestones, cosmetics, totals (restored on startup) |

Read them through `GET /api/v1/history/predictions` and `GET /api/v1/history/broadcast` (admin), or with any PostgreSQL client.

Tables are created automatically on startup. When the schema needs to change on a database with real data, add Alembic migrations first. `create_all` only creates missing tables; it never alters existing ones.

## 2. Google Cloud (planned)

The same containers map onto managed Google Cloud services:

| Local | Google Cloud |
|---|---|
| `backend` container | **Cloud Run** service, min instances = max instances = **1** |
| `frontend` container | Cloud Run service (or Cloud Storage + Cloud CDN for the static files, with a load balancer routing `/api` and `/ws` to the backend) |
| `postgres` | **Cloud SQL for PostgreSQL** (private IP, automated backups) |
| `redis` | **Memorystore for Redis** (via a Serverless VPC connector / Direct VPC egress) |
| `.env` secrets | **Secret Manager** (`ANTHROPIC_API_KEY`, `SOKOKALI_ADMIN_TOKEN`, `FOOTBALL_DATA_API_KEY`, database password) mounted as environment variables |
| `docker compose build` | **Cloud Build** pushing to **Artifact Registry**, triggered from GitHub |
| `/metrics` and JSON logs | **Cloud Logging** (automatic) and Cloud Monitoring (Managed Service for Prometheus, or log-based metrics) |

Points to get right when we do it:

- **Exactly one backend instance.** The live show (queue, pacing, WebSocket clients) lives in one process. Set `--min-instances=1 --max-instances=1` and CPU "always allocated", so the broadcast keeps running between requests. Running several instances would need the live state moved to Redis first.
- **WebSockets on Cloud Run** are supported. Set the request timeout to the maximum (60 minutes); the dashboard reconnects automatically after each timeout.
- **Production settings:** `SOKOKALI_ENVIRONMENT=production` (admin endpoints then refuse everything until `SOKOKALI_ADMIN_TOKEN` is set), `SOKOKALI_CORS_ORIGINS` set to the real dashboard URL, HTTPS only.
- **Real client IPs:** uvicorn runs with `--proxy-headers`, so rate limits use the client IP from Google's load balancer.
- **Cost control:** one always-on Cloud Run instance, the smallest Cloud SQL tier and Basic Memorystore are enough to start. Claude API usage is billed separately per reply.
- **Region:** choose the region with the lowest latency to Kenyan viewers, and check that every service above is offered there. `africa-south1` (Johannesburg) is the obvious candidate to compare against European regions. Check Google's current region list when deploying.

## 3. Scaling notes

- The backend deliberately runs **one uvicorn worker**. Chat, predictions and history would scale horizontally today, because rate limits are already shared through Redis. The broadcast controller would not.
- For more viewers, scale the stateless parts first (put the chat API behind several instances) and keep one dedicated broadcast instance.
