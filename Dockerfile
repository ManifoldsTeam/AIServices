# ── Stage 1: Build dependencies ──────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements-docker.txt ./requirements.txt

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ ./src/

# Env files are NOT baked in.
# - Local:      mounted via docker-compose  (.env + .env.develop)
# - Production: mounted or injected via Cloud Run env-vars
#   (if using Cloud Run env-vars, remove the FileNotFoundError guard in settings.py)

# Default port (overridden by docker-compose or Cloud Run)
ENV PORT=8080

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 65"]
