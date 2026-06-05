# url-shortener-alpha

`snip` — a URL shortener service used to learn components of K8s and FastAPI.

A production-shaped [FastAPI](https://fastapi.tiangolo.com/) service backed by
[Redis](https://redis.io/). It generates short codes for URLs, redirects on
lookup, tracks click counts, and supports optional link expiry (TTL). The app is
stateless so it scales horizontally. See [SPEC.md](SPEC.md) for the full,
phased build plan.

## API

| Method   | Path            | Behavior                                              |
|----------|-----------------|-------------------------------------------------------|
| `GET`    | `/healthz`      | Liveness — always `200 {"status":"ok"}`.              |
| `GET`    | `/readyz`       | Readiness — `200` if Redis is reachable, else `503`.  |
| `POST`   | `/links`        | Create a link. Body: `{"url": "...", "ttl_seconds": 3600}` (`ttl_seconds` optional). Returns `201 {"code","short_url"}`. |
| `GET`    | `/{code}`       | `307` redirect to the original URL (bumps clicks), or `404`. |
| `GET`    | `/links/{code}` | Link metadata: `{url, created_at, clicks}`.           |
| `DELETE` | `/links/{code}` | Delete the link. Returns `204`.                       |

## Requirements

- [uv](https://docs.astral.sh/uv/) for Python and dependency management
- [Docker](https://docs.docker.com/) (with Compose) for the full local stack

## Local development

Install dependencies into a local virtualenv:

```bash
make install        # uv sync
```

Run the app locally (expects a Redis reachable at `REDIS_URL`,
default `redis://localhost:6379/0`):

```bash
uv run uvicorn app.main:app --reload
```

Configuration is read from the environment (see [app/config.py](app/config.py)):

| Variable              | Default                      | Purpose                                  |
|-----------------------|------------------------------|------------------------------------------|
| `REDIS_URL`           | `redis://localhost:6379/0`   | Redis connection string.                 |
| `BASE_URL`            | `http://localhost`           | Prefix used to build `short_url`.        |
| `DEFAULT_TTL_SECONDS` | _(unset)_                    | Default link TTL when none is supplied.  |

## Testing

The test suite uses an in-memory fake Redis, so **no real Redis is needed** to
run it.

```bash
make test       # fast suite (excludes @pytest.mark.slow)
make test-slow  # only the slow tests (e.g. the ~2s TTL-expiry test)
make test-all   # everything
make lint       # ruff check --fix + format
```

## Full stack with Docker Compose

Build the image and run the app against a real Redis container:

```bash
docker compose up --build      # starts redis + app on http://localhost:8000
```

Exercise the round-trip once it's up:

```bash
# Create a short link
curl -s -X POST http://localhost:8000/links \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/page"}'
# => {"code":"wSKWbp","short_url":"http://localhost:8000/wSKWbp"}

# Follow the redirect (use the code from above)
curl -i http://localhost:8000/wSKWbp        # => 307, Location: https://example.com/page

# Inspect metadata (url, created_at, clicks)
curl -s http://localhost:8000/links/wSKWbp

# Delete it
curl -i -X DELETE http://localhost:8000/links/wSKWbp   # => 204
```

Run the test suite inside the image (against the fake Redis):

```bash
docker compose run --rm test
```

Tear everything down (add `-v` to also drop the Redis volume):

```bash
docker compose down
```
