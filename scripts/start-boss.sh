#!/usr/bin/env bash
# Start the Boss as a Kimi web UI session.
# The user interacts with the Boss in Brave on Windows.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Load queue secret to reuse as the web UI auth token (LAN only).
source "$HOME/.config/mypeople/queue.env" 2>/dev/null || true
BOSS_TOKEN="${QUEUE_SECRET:-}"
if [[ -z "$BOSS_TOKEN" ]]; then
  echo "[boss] ERROR: QUEUE_SECRET not set. Run scripts/install.sh first." >&2
  exit 1
fi

echo "[boss] Starting Kimi web UI for the Boss..."
echo "[boss] On Windows, run: ./scripts/start-boss.ps1"
exec kimi \
  --agent-file "$REPO_DIR/agents/boss-kimi.yaml" \
  --work-dir "$REPO_DIR" \
  web \
  --network \
  --no-open \
  --auth-token "$BOSS_TOKEN" \
  --port "${BOSS_PORT:-5494}" \
  "$@"
