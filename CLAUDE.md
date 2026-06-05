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

## Local image tag

The Compose build tags the image `snip:latest` (see
[docker-compose.yml](docker-compose.yml)). That's the tag `kind load
docker-image snip:latest` expects in Phase 7.

## Conventions

- Python/deps managed with **uv**. Tests use an in-memory fake Redis (no real
  Redis needed): `make test` (fast), `make test-all`, `make test-slow`.
- Red/green TDD per the spec: failing test first, confirm it fails for the
  right reason, then minimal implementation.
