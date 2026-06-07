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

## Local Kubernetes (kind)

Manifests live in [k8s/](k8s/) and deploy into a dedicated `snip` namespace:
namespace, ConfigMap, Secret, a Redis Deployment + Service + PVC, and the app
Deployment (2 replicas, liveness/readiness probes) behind a NodePort Service.
Requires a running [kind](https://kind.sigs.k8s.io/) cluster and `kubectl`.

> This project uses an existing kind cluster named `learn`; adjust `--name` /
> context if yours differs. The app Deployment pulls from a private ECR repo, so
> a pull secret is required (see below). To run fully locally without ECR,
> change the `image:` in [k8s/app-deployment.yaml](k8s/app-deployment.yaml) back
> to `snip:latest` with `imagePullPolicy: IfNotPresent` and `kind load` it.

### Setup

```bash
# 1. Build the image and load it into the cluster (only needed for the
#    local-image workflow; skip if pulling from ECR).
docker compose build app
kind load docker-image snip:latest --name learn

# 2. Create the ECR pull secret (tokens expire ~12h — re-run to refresh).
kubectl create secret docker-registry ecr-pull-secret \
  --docker-server=344378332628.dkr.ecr.us-east-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password="$(aws ecr get-login-password --region us-east-1)" \
  -n snip --dry-run=client -o yaml | kubectl apply -f -

# 3. Apply the manifests (namespace first to satisfy ordering).
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/

# 4. Wait for both pods to be Ready.
kubectl rollout status deployment/redis -n snip
kubectl rollout status deployment/snip -n snip
```

Inspect what's running:

```bash
kubectl get all,configmap,secret,pvc -n snip
kubectl get endpoints snip -n snip      # app pod IPs behind the Service
```

### Access for manual testing (Postman)

The NodePort isn't mapped to the host on this cluster, so use `port-forward`.
Leave this running in its own terminal:

```bash
kubectl port-forward svc/snip 8080:80 -n snip
```

The app is now at `http://localhost:8080`. Smoke-check it:

```bash
curl -i http://localhost:8080/healthz     # => 200 {"status":"ok"}
```

Then run the Postman collection in
[postman/snip.postman_collection.json](postman/snip.postman_collection.json) —
its `baseUrl` variable already defaults to `http://localhost:8080`. Import the
file and use **Run** to exercise every endpoint, or click requests individually.

### Teardown

```bash
kubectl delete -f k8s/            # remove all snip resources
# or, to drop the namespace (and everything in it) wholesale:
kubectl delete namespace snip
```
