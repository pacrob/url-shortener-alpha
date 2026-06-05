# syntax=docker/dockerfile:1

# ---- Builder: resolve and install dependencies into a venv ----
FROM python:3.13-slim AS builder

# uv is only needed at build time, so it lives in the builder stage.
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Copy only the lockfiles first so dependency install is cached independently
# of application source changes.
COPY pyproject.toml uv.lock ./

# Production dependencies only (excludes the dev group). --no-install-project
# because snip is a non-packaged app run via PYTHONPATH, not an installed dist.
RUN uv sync --frozen --no-dev --no-install-project


# ---- Test: add dev deps on top of the builder for in-container testing ----
FROM builder AS test

RUN uv sync --frozen --no-install-project
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
# tests/ is mounted at run time (excluded from the image via .dockerignore).
CMD ["pytest", "-m", "not slow"]


# ---- Runtime: slim, non-root, production image ----
FROM python:3.13-slim AS runtime

# Non-root user — maps directly to a K8s securityContext later.
RUN useradd --system --create-home --uid 1000 app

WORKDIR /app

# Bring over the prebuilt venv and the application source only.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

# Liveness check baked into the image; mirrors the K8s livenessProbe on /healthz.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
