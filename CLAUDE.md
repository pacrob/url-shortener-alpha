# CLAUDE.md

Project context for `snip`, the URL shortener. The phased build plan lives in
[SPEC.md](SPEC.md); this file records facts and deviations that later phases
need but the spec doesn't capture.

## Deviations from SPEC.md

- **ECR repo name is `snip-url-shortener`, not `snip`.** The spec (Phases 6–8)
  assumes a repo named `snip`. The actual repo created in Phase 6 is
  `snip-url-shortener`.
- **Config env vars are unprefixed.** Phase 1 originally used a `SNIP_` prefix;
  dropped in Phase 5 so the spec's `REDIS_URL` / `BASE_URL` /
  `DEFAULT_TTL_SECONDS` names work directly (Compose env + Phase 7 ConfigMap).
- **In-container tests run via a dedicated `test` service**, not
  `docker compose run app pytest`. The production `app` image intentionally
  omits dev deps and `tests/`. Use `docker compose run --rm test`.

## Deployment facts (for Phases 7–8)

- **ECR image URI:** `344378332628.dkr.ecr.us-east-1.amazonaws.com/snip-url-shortener:latest`
- **Registry host** (pull-secret `--docker-server`): `344378332628.dkr.ecr.us-east-1.amazonaws.com`
- **Region:** `us-east-1` · **Account:** `344378332628`
- Prefer pinning by **digest** over `:latest` in manifests (`latest` is mutable;
  K8s caches it). Last known digest:
  `sha256:435fc3036f08bdab0d7269cf0f53c56703127f5194f998dbe99eb9e16c3f8c7e`
- **Phase 7 uses the local image** (`kind load docker-image snip:latest`), not
  ECR. ECR + `imagePullSecrets` are introduced in Phase 8.

## Kubernetes (Phase 7)

- Deployed into the existing **`kind-learn`** cluster (not a fresh `kind` one),
  all under the **`snip`** namespace. Manifests in [k8s/](k8s/).
- Apply order matters: `kubectl apply -f k8s/namespace.yaml` first, then
  `kubectl apply -f k8s/` (alphabetical apply would otherwise hit
  app-deployment before namespace exists).
- Load the local image before applying:
  `kind load docker-image snip:latest --name learn`.
- Access: `kubectl port-forward svc/snip 8080:80 -n snip`, then curl
  `http://localhost:8080`. NodePort is `30080`.
- **`runAsNonRoot` needs a numeric UID.** The image declares `USER app` (a
  name), so the app Deployment sets `securityContext.runAsUser: 1000`;
  without it pods fail with `CreateContainerConfigError` ("image has
  non-numeric user"). Alternative fix: change the Dockerfile to `USER 1000`.
- Teardown: `kubectl delete -f k8s/` (or `kubectl delete ns snip`).

## Pull from ECR (Phase 8)

- App Deployment now pulls `…/snip-url-shortener:latest` from ECR (was the
  kind-loaded `snip:latest`), `imagePullPolicy: Always`.
- **Pull secret `ecr-pull-secret`** (type `dockerconfigjson`) in the `snip`
  namespace, referenced via `imagePullSecrets` in app-deployment.yaml. It is
  **not** in the repo — the ECR token is short-lived. Recreate/refresh with:
  ```
  kubectl create secret docker-registry ecr-pull-secret \
    --docker-server=344378332628.dkr.ecr.us-east-1.amazonaws.com \
    --docker-username=AWS \
    --docker-password="$(aws ecr get-login-password --region us-east-1)" \
    -n snip --dry-run=client -o yaml | kubectl apply -f -
  ```
- **ECR auth tokens expire ~12h.** When pods later fail with `ImagePullBackOff`
  / 401, the secret is stale — re-run the command above and
  `kubectl rollout restart deployment/snip -n snip`. (IRSA would avoid manual
  refresh; out of scope here.)
- Rollout mgmt: `kubectl rollout status|history|undo deployment/snip -n snip`.

## Local image tag

The Compose build tags the image `snip:latest` (see
[docker-compose.yml](docker-compose.yml)). That's the tag `kind load
docker-image snip:latest` expects in Phase 7.

## Conventions

- Python/deps managed with **uv**. Tests use an in-memory fake Redis (no real
  Redis needed): `make test` (fast), `make test-all`, `make test-slow`.
- Red/green TDD per the spec: failing test first, confirm it fails for the
  right reason, then minimal implementation.
