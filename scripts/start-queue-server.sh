#!/usr/bin/env bash
# Start the mypeople queue server.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$HOME/.config/mypeople/queue.env" 2>/dev/null || true

export QUEUE_URL="${QUEUE_URL:-http://127.0.0.1:9900}"
export QUEUE_SECRET="${QUEUE_SECRET:-}"
export HOST_ID="${HOST_ID:-$(hostname)}"

# Expose the WSL-accessible Kimi web URL so the dashboard links work from Brave.
WSL_IP=$(hostname -I | awk '{print $1}')
export KIMI_WEB_URL="${KIMI_WEB_URL:-http://${WSL_IP}:5494}"

cd "$REPO_DIR"
exec python3 "$REPO_DIR/src/mypeople/queue_server.py" --port "${QUEUE_PORT:-9900}"
