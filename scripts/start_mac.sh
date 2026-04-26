#!/usr/bin/env bash
# FinAlly — start the container on macOS/Linux.
#
# Usage:
#   scripts/start_mac.sh           # build if missing, then start
#   scripts/start_mac.sh --build   # force a rebuild before starting
#   scripts/start_mac.sh --open    # also open the browser when ready
set -euo pipefail

IMAGE="finally:latest"
CONTAINER="finally"
VOLUME="finally-data"
PORT="8000"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

force_build=0
open_browser=0
for arg in "$@"; do
    case "$arg" in
        --build) force_build=1 ;;
        --open) open_browser=1 ;;
        -h|--help)
            sed -n '2,7p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker is not installed or not on PATH." >&2
    exit 1
fi

env_args=()
if [[ -f "$REPO_ROOT/.env" ]]; then
    env_args+=(--env-file "$REPO_ROOT/.env")
else
    echo "Warning: $REPO_ROOT/.env not found — copy .env.example to .env if you need API keys." >&2
fi

# Stop and remove any prior container so this script is idempotent.
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Removing existing container '$CONTAINER'..."
    docker rm -f "$CONTAINER" >/dev/null
fi

# Build the image if missing or if --build was passed.
if [[ "$force_build" -eq 1 ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building image '$IMAGE'..."
    docker build -t "$IMAGE" "$REPO_ROOT"
fi

# Ensure the named volume exists (docker creates it on first run otherwise,
# but doing it explicitly makes the script's intent clearer).
if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    docker volume create "$VOLUME" >/dev/null
fi

echo "Starting container '$CONTAINER' on port $PORT..."
docker run -d \
    --name "$CONTAINER" \
    -p "${PORT}:8000" \
    -v "${VOLUME}:/app/db" \
    "${env_args[@]}" \
    "$IMAGE" >/dev/null

url="http://localhost:${PORT}"
echo "FinAlly is starting at ${url}"
echo "  docker logs -f $CONTAINER     # follow logs"
echo "  scripts/stop_mac.sh           # stop"

if [[ "$open_browser" -eq 1 ]]; then
    if command -v open >/dev/null 2>&1; then
        open "$url"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
    fi
fi
