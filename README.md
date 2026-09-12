# URL Shortener + Analytics

A short-link service with per-user accounts and click analytics, built with FastAPI,
PostgreSQL and Redis.

Redirects are the hot path, so they are served from a Redis cache and record their click
in a background task — the visitor never waits on a database write.

## Architecture

```
                  ┌────────────────┐
  POST /api/links │                │  write-through on miss
  ───────────────►│    FastAPI     │◄──────────────┐
                  │                │               │
  GET /{code}     │  rate limiter  │──lookup──►┌───┴────┐
  ───────────────►│  JWT auth      │           │ Redis  │
         307 ◄────│                │◄──hit─────└────────┘
                  └───────┬────────┘
                          │ background task (click event + counter)
                          ▼
                   ┌─────────────┐
                   │ PostgreSQL  │  users · links · click_events
                   └─────────────┘
```

## Design decisions

**Random short codes, not `base62(id)`.** Encoding the primary key is one line shorter, but
it makes every link in the system enumerable — walk the integers and you have everyone's
URLs. Codes are 7 random base62 characters (~3.5 trillion values) inserted under a unique
constraint, retrying on collision. The database, not the application, is the authority on
uniqueness.

**Clicks are written after the response.** The redirect returns as soon as the target is
known; the click event and counter increment run in a FastAPI background task on their own
session. An analytics write is never allowed to slow down or break a redirect.

**The click counter is denormalized onto `links`.** Listing links would otherwise need a
`COUNT(*)` over `click_events` per row. The counter is incremented with a SQL expression
(`click_count = click_count + 1`), so concurrent redirects don't lose updates.

**Cache entries never outlive their link.** A cached redirect is TTL-capped to the link's own
expiry, and deleting a link evicts its key — a cache can't keep serving a link the owner
has already removed.

**Analytics are indexed for the query they actually run.** `click_events` carries a composite
index on `(link_id, clicked_at)`, because every analytics query filters by link and then
ranges over time.

**Visitor IPs are stored as salted hashes.** Unique-visitor counts need a stable per-visitor
token, not the address itself, so nothing here stores a raw IP.

**Postgres and Redis are optional in development.** If either is unreachable at startup the
app logs a warning and falls back to SQLite and an in-memory cache, so the service runs
with no infrastructure. `GET /health` reports which backends are actually live.

## API

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | – | Create an account |
| `POST` | `/auth/login` | – | Exchange credentials for a JWT |
| `GET` | `/auth/me` | Bearer | Current user |
| `POST` | `/api/links` | Bearer | Create a short link (optional custom alias, expiry) |
| `GET` | `/api/links` | Bearer | List your links |
| `GET` | `/api/links/{code}` | Bearer | One link |
| `DELETE` | `/api/links/{code}` | Bearer | Delete a link and evict its cache entry |
| `GET` | `/api/links/{code}/analytics?days=7` | Bearer | Clicks by day, top referrers, top browsers |
| `GET` | `/{code}` | – | Redirect to the target URL |
| `GET` | `/health` | – | Liveness plus active backends |

Interactive docs at `/docs`.

Rate limits are fixed-window per IP, counted in Redis so they hold across workers:
100 requests/minute on the API, 600/minute on redirects.

## Running it

With Docker — Postgres and Redis included:

```bash
cp .env.example .env      # set JWT_SECRET
docker compose up --build
```

Without Docker — falls back to SQLite and an in-memory cache:

```bash
python -m venv .venv && .venv/Scripts/activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Then:

```bash
curl -X POST localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"supersecret"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"supersecret"}' | jq -r .access_token)

curl -X POST localhost:8000/api/links \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target_url":"https://fastapi.tiangolo.com/","custom_alias":"fastapi"}'

curl -sI localhost:8000/fastapi | grep location
curl -s localhost:8000/api/links/fastapi/analytics -H "Authorization: Bearer $TOKEN"
```

## Tests

```bash
pytest -q        # 19 tests: auth, ownership isolation, caching, expiry, rate limiting, analytics
ruff check app tests
```

CI runs the suite against real Postgres and Redis service containers on every push, then
builds the Docker image.

## Deploying

The image reads `$PORT`, so it runs as-is on Render, Railway or Fly. Set:

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | A `postgres://` DSN is rewritten to the async driver automatically |
| `REDIS_URL` | Managed Redis (Upstash works) |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `BASE_URL` | Public origin, used to build the returned short URLs |

Schema is created on startup. A schema-migration tool (Alembic) is the next step before
this takes real traffic.
