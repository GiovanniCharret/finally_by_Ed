# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Stage 1: build the Next.js static export
# -----------------------------------------------------------------------------
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Install deps using the lockfile so the build is reproducible. Copying
# package*.json before the rest of the source lets Docker cache npm ci between
# rebuilds when only application code changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./

# `output: "export"` writes the static site to ./out
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2: Python runtime with FastAPI + uv
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    UV_LINK_MODE=copy

# uv ships a static binary; copying from the official image avoids pip / curl.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install backend dependencies first so the layer is cached when only app code
# changes. uv.lock + pyproject.toml together describe the full dep graph.
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --project /app/backend --frozen --no-install-project --no-dev

# Copy the rest of the backend source.
COPY backend/ ./backend/

# Install the project itself (editable not needed in a container).
RUN uv sync --project /app/backend --frozen --no-dev

# Copy the static frontend build into the location FastAPI mounts at "/".
COPY --from=frontend-builder /app/frontend/out/ ./backend/static/

# SQLite volume mount target. The backend writes db/finally.db here at runtime.
RUN mkdir -p /app/db
VOLUME ["/app/db"]

EXPOSE 8000

# Use uv run so the venv is picked up implicitly. Working dir is /app so the
# backend's DB_PATH (= project_root/db/finally.db) resolves to /app/db/finally.db.
WORKDIR /app/backend
CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
