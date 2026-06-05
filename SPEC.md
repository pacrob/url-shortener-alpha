# `snip` — URL Shortener · Project Spec

## Purpose

A learning project to build a production-shaped FastAPI service, containerize it, push it to AWS ECR, and use it as a hands-on substrate for studying Kubernetes and the KCNA/CKAD certification material.

The app itself is a URL shortener backed by Redis. Short codes are random alphanumeric strings. The app is designed to be stateless so it scales horizontally without coordination.

---

## Ground Rules

**Red/green TDD at every step.** Before writing any implementation code:

1. Write a failing test that describes the behavior you want.
2. Confirm it fails for the right reason (not an import error, not a wrong assertion — the behavior is genuinely absent).
3. Write the minimum implementation to make it pass.
4. Refactor if needed, keeping tests green.

Each phase below ends with a fully green test suite before you move on. Do not carry forward a broken test.

**Each phase is self-contained.** The app should be runnable and testable at the end of every phase. You are not building toward a big bang — you are building a working thing and then extending it.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Web framework | FastAPI |
| Backing store | Redis |
| Redis client | `redis-py` (async via `redis.asyncio`) |
| Settings | `pydantic-settings` |
| Testing | `pytest` + `httpx` + `pytest-asyncio` |
| Containerization | Docker + Docker Compose |
| Registry | AWS ECR |
| Orchestration | Kubernetes (via `kind` for local) |

---

## Project Layout

```
snip/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # Settings (pydantic-settings)
│   ├── routes/
│   │   ├── links.py         # POST /links, GET /{code}, etc.
│   │   └── health.py        # GET /healthz, GET /readyz
│   └── services/
│       └── redis.py         # Redis client wrapper
├── tests/
│   ├── conftest.py          # Shared fixtures (test client, fake Redis)
│   ├── test_links.py
│   └── test_health.py
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── redis-deployment.yaml
│   ├── redis-service.yaml
│   ├── app-deployment.yaml
│   └── app-service.yaml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── SPEC.md
```

---

## Phase 1 — Bare FastAPI App

**Goal:** A minimal, testable FastAPI application. No Redis yet. No real routes. Just enough scaffolding to prove the test harness works.

**What you'll build:**
- `app/main.py` with a FastAPI app instance
- `app/config.py` with a `Settings` class using `pydantic-settings` (reads from env)
- `tests/conftest.py` with an `AsyncClient` fixture pointed at the app
- One smoke-test: `GET /healthz` returns `200 {"status": "ok"}`

**TDD steps:**
1. Write `test_health.py::test_liveness` — it should fail because the route doesn't exist.
2. Add `app/routes/health.py` with just `/healthz`.
3. Wire the router into `app/main.py`.
4. Test passes. Suite is green.

**K8s concept introduced:** None yet — this phase is purely about getting the test harness right so every future phase starts from a known-good baseline.

**Exit criteria:** `pytest` runs, one test passes, zero failures.

---

## Phase 2 — Readiness Probe with a Fake Redis

**Goal:** Add `/readyz` which checks whether Redis is reachable. Introduce a Redis service abstraction that can be swapped for a fake in tests.

**What you'll build:**
- `app/services/redis.py` — a thin async wrapper around `redis.asyncio`. Exposes `ping()`, `set()`, `get()`, `delete()`.
- `/readyz` calls `redis.ping()`. Returns `200 {"status": "ok"}` if reachable, `503 {"status": "unavailable"}` if not.
- A `fake_redis` fixture in `conftest.py` — an in-memory dict that satisfies the same interface, injected via FastAPI dependency override.

**TDD steps:*
1. Write `test_health.py::test_readiness_ok` — should fail (route absent).
2. Write `test_health.py::test_readiness_redis_down` — uses a fake that raises on `ping()`.
3. Build the Redis wrapper and the `/readyz` route.
4. Both tests pass.

**K8s concept introduced:** The `livenessProbe` vs `readinessProbe` distinction. Liveness answers "is the process alive?" — if it fails, K8s restarts the pod. Readiness answers "is this pod ready to serve traffic?" — if it fails, K8s pulls the pod from the Service's endpoint list without restarting it. Your two health endpoints map directly to these two probes.

**Exit criteria:** `pytest` green. You can explain why the two probes exist and why they behave differently.

---

## Phase 3 — Core Link CRUD

**Goal:** Implement the URL shortener's core behavior. This is the main feature work.

**Endpoints:**

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/links` | Accept `{"url": "https://..."}`, generate a random 6-char alphanumeric code, store it in Redis, return `{"code": "abc123", "short_url": "http://localhost/abc123"}` |
| `GET` | `/{code}` | Look up code in Redis. If found, return `307 Temporary Redirect` to the original URL. If not found, `404`. |
| `GET` | `/links/{code}` | Return JSON metadata: original URL, creation timestamp, click count. |
| `DELETE` | `/links/{code}` | Delete the key from Redis. Return `204 No Content`. |

**Data shape in Redis:**

Store each link as a Redis hash:
```
key:   snip:{code}
fields: url, created_at, clicks
```

Click count is incremented atomically on each `GET /{code}` redirect.

**TDD steps (suggested order):**
1. `test_create_link` — POST returns a code and a short_url. Fails. Implement. Green.
2. `test_create_link_invalid_url` — POST with a non-URL string returns `422`. FastAPI/Pydantic handles this for free — write the test to document the contract.
3. `test_redirect` — GET /{code} returns 307 to the right URL. Fails. Implement. Green.
4. `test_redirect_not_found` — GET /{unknown} returns 404.
5. `test_get_metadata` — GET /links/{code} returns url, created_at, clicks.
6. `test_clicks_increment` — redirect twice, metadata shows clicks=2.
7. `test_delete_link` — DELETE returns 204, subsequent GET returns 404.

**K8s concept introduced:** `ConfigMap`. The base URL used to construct `short_url` (e.g. `http://localhost` locally vs `https://snip.example.com` in-cluster) should come from a `Settings` field read from an env var — not hardcoded. This is exactly what a K8s `ConfigMap` injects. You won't write the YAML yet, just wire the setting.

**Exit criteria:** All 7 tests pass. The fake Redis fixture covers every test — no real Redis needed to run the suite.

---

## Phase 4 — TTL / Link Expiry

**Goal:** Add optional link expiry. When creating a link, the caller can pass `{"url": "...", "ttl_seconds": 3600}`. After that TTL, the link is gone.

**What you'll build:**
- Extend the `POST /links` request body to accept optional `ttl_seconds` (default: `None` = no expiry).
- If provided, set a Redis key TTL using `EXPIRE`.
- `GET /{code}` already handles missing keys as 404 — expiry is transparent at the app layer.

**TDD steps:**
1. `test_create_link_with_ttl` — POST with `ttl_seconds=1`, sleep 2s, GET returns 404. (Mark as slow with `@pytest.mark.slow` — you'll skip it in normal runs.)
2. `test_create_link_without_ttl` — no TTL field, Redis key persists (fake Redis won't expire, that's fine — you're testing the app layer contract, not Redis internals).

**K8s concept introduced:** `ConfigMap` for the default TTL. Add a `DEFAULT_TTL_SECONDS` setting. If set in the environment, all links get that TTL unless the caller overrides it. This is the pattern K8s operators use to tune app behavior per environment without rebuilding images.

**Exit criteria:** Suite green (excluding `@pytest.mark.slow` in fast runs). `pytest -m slow` runs the expiry test.

---

## Phase 5 — Containerize with Docker

**Goal:** Build a Docker image, run the full app locally against a real Redis container using Docker Compose.

**What you'll build:**
- `Dockerfile` — multi-stage: build stage installs deps, runtime stage is slim.
- `docker-compose.yml` — two services: `app` and `redis`. App reads `REDIS_URL` from the Compose environment. Redis uses a named volume for persistence.
- Confirm `POST /links` → `GET /{code}` round-trip works against the real Redis.

**No new tests in this phase** — the existing suite already covers behavior. You are proving the container build doesn't break anything.

**Docker discipline:**
- `.dockerignore` excludes `tests/`, `k8s/`, `*.md`, `.git`
- App runs as a non-root user inside the container
- `HEALTHCHECK` instruction in the Dockerfile hits `/healthz`

**K8s concept introduced:** The image. Every K8s workload runs a container image. The discipline of a non-root user, a minimal base image, and a built-in health check are not just Docker best practices — they map directly to K8s security contexts and probe configuration.

**Exit criteria:** `docker compose up` starts both services. Manual curl round-trip succeeds. `docker compose run app pytest` runs the suite against the fake Redis.

---

## Phase 6 — Push to AWS ECR

**Goal:** Tag and push the image to a private ECR repository. Understand the authentication flow that K8s will later need to replicate.

**Steps:**
1. Create an ECR repo (`snip`) via the AWS console or CLI.
2. Authenticate Docker to ECR: `aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com`
3. Tag: `docker tag snip:latest <ecr-uri>/snip:latest`
4. Push.

**K8s concept introduced:** `ImagePullSecrets`. When K8s pulls an image from a private registry, it needs credentials. You store those as a K8s `Secret` of type `kubernetes.io/dockerconfigjson` and reference it in your `Deployment`. You'll configure this in Phase 8, but understanding why it exists starts here.

**Exit criteria:** Image visible in ECR console. You can pull it fresh on another terminal with `docker pull <ecr-uri>/snip:latest`.

---

## Phase 7 — Local Kubernetes with `kind`

**Goal:** Get the app running inside a local K8s cluster. No ECR yet — use the local image loaded directly into `kind`.

**What you'll build in `k8s/`:**

`namespace.yaml`
- A `snip` namespace. All resources live here.

`redis-deployment.yaml` + `redis-service.yaml`
- Redis `Deployment` (1 replica, `redis:7-alpine`)
- `ClusterIP` Service — only reachable inside the cluster
- `PersistentVolumeClaim` for `/data`

`configmap.yaml`
- `BASE_URL` — e.g. `http://localhost`
- `DEFAULT_TTL_SECONDS` — optional

`secret.yaml`
- `REDIS_PASSWORD` — even if Redis isn't password-protected yet, add the plumbing now. This is the pattern.

`app-deployment.yaml`
- FastAPI `Deployment`, 2 replicas
- `envFrom` wiring `ConfigMap` into env
- `env` wiring `Secret` value into `REDIS_PASSWORD`
- `livenessProbe` → `/healthz`
- `readinessProbe` → `/readyz`
- `resources.requests` and `resources.limits` set

`app-service.yaml`
- `NodePort` Service (simplest way to reach the app from your host via `kind`)

**Steps:**
1. `kind create cluster`
2. `kind load docker-image snip:latest`
3. `kubectl apply -f k8s/`
4. `kubectl port-forward svc/snip 8080:80 -n snip` and curl the round-trip.

**K8s concepts introduced:** Namespace, Deployment, Service (ClusterIP + NodePort), ConfigMap, Secret, PersistentVolumeClaim, liveness/readiness probes, resource requests/limits. This is the dense phase — take it one manifest at a time, apply it, watch what changes with `kubectl get pods -n snip -w`.

**Exit criteria:** Both pods Running. `kubectl get endpoints -n snip` shows the app pods behind the Service. Manual curl round-trip succeeds.

---

## Phase 8 — Pull from ECR

**Goal:** Replace the `kind`-loaded local image with the ECR image. Introduce `ImagePullSecrets`.

**Steps:**
1. Create an IAM user or use IRSA (IAM Roles for Service Accounts) — for simplicity, start with a static IAM user with `ecr:GetAuthorizationToken` + `ecr:BatchGetImage`.
2. Create the pull secret:
   ```
   kubectl create secret docker-registry ecr-pull-secret \
     --docker-server=<account>.dkr.ecr.<region>.amazonaws.com \
     --docker-username=AWS \
     --docker-password=$(aws ecr get-login-password) \
     -n snip
   ```
3. Add `imagePullSecrets` to `app-deployment.yaml`.
4. Update the image reference to the ECR URI.
5. `kubectl rollout restart deployment/snip -n snip`

**K8s concept introduced:** `ImagePullSecrets` and the `ServiceAccount` attachment pattern. Also: `kubectl rollout status` and `kubectl rollout undo` for deployment management.

**Exit criteria:** Pods pull the ECR image successfully. `kubectl describe pod <name> -n snip` shows the correct image URI and no pull errors.

---

## Phase 9 — Horizontal Pod Autoscaler

**Goal:** Configure the HPA to scale the app Deployment based on CPU utilization.

**What you'll build:**

`hpa.yaml`
- `HorizontalPodAutoscaler` targeting the app Deployment
- Min 2 replicas, max 6
- Scale up when average CPU > 60%

You'll also need `metrics-server` running in the cluster (for `kind`: `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml` with the `--kubelet-insecure-tls` patch).

Generate some load with a simple loop:
```bash
while true; do curl -s http://localhost:8080/links -d '{"url":"https://example.com"}' -H 'Content-Type: application/json' > /dev/null; done
```

Watch the HPA react:
```bash
kubectl get hpa -n snip -w
```

**K8s concept introduced:** `HorizontalPodAutoscaler`, `metrics-server`, and the control loop pattern. The HPA is your first encounter with a K8s controller that reconciles observed state (current CPU) against desired state (target utilization) in a continuous loop — understanding this pattern is foundational for the cert.

**Exit criteria:** Under load, replica count increases. Load removed, replicas scale back down (takes a few minutes).

---

## What's Intentionally Out of Scope

These are real K8s topics but are excluded to keep the project focused:

- **Ingress / TLS** — NodePort is enough to learn the core concepts
- **Helm** — plain manifests are better for learning what each field does
- **RBAC** — worth a separate focused exercise
- **Network Policies** — same
- **Multi-environment promotion** — out of scope for a solo learning project

---

## Cert Coverage Map

| KCNA / CKAD Topic | Where it appears |
|---|---|
| Pods, Deployments, ReplicaSets | Phase 7 |
| Services (ClusterIP, NodePort) | Phase 7 |
| ConfigMaps | Phases 3, 7 |
| Secrets | Phases 6, 7, 8 |
| PersistentVolumes / PVCs | Phase 7 |
| Liveness / Readiness Probes | Phases 2, 7 |
| Resource requests / limits | Phase 7 |
| Namespaces | Phase 7 |
| ImagePullSecrets | Phase 8 |
| HorizontalPodAutoscaler | Phase 9 |
| Rolling updates / rollback | Phase 8 |
| Container image best practices | Phase 5 |
