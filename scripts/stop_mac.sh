#!/usr/bin/env bash
# FinAlly — stop and remove the container on macOS/Linux.
# The named volume `finally-data` is intentionally NOT removed so SQLite data
# persists across restarts. Use `docker volume rm finally-data` to wipe it.
set -euo pipefail

CONTAINER="finally"

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker is not installed or not on PATH." >&2
    exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Stopping container '$CONTAINER'..."
    docker rm -f "$CONTAINER" >/dev/null
    echo "Container removed. Volume 'finally-data' was preserved."
else
    echo "No container named '$CONTAINER' is running."
fi
