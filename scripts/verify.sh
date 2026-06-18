#!/usr/bin/env bash
# Verification script for the Kimi-native mypeople runtime.
# This checks the control plane without requiring a working LLM connection.

set -euo pipefail

source "$HOME/.config/mypeople/queue.env" 2>/dev/null || true
HOST=$(hostname)
SECRET="${QUEUE_SECRET:-}"

if [ -z "$SECRET" ]; then
  echo "[verify] QUEUE_SECRET not set. Run scripts/install.sh first."
  exit 1
fi

echo "[verify] health check"
curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/health >/dev/null

echo "[verify] spawn"
mp spawn "$HOST"/verify:w1 --cwd /tmp

echo "[verify] status"
mp status | grep -q "$HOST/verify:w1.*idle"

echo "[verify] peek"
mp peek "$HOST"/verify:w1 | grep -q 'state=idle'

echo "[verify] dashboard"
curl -sf http://127.0.0.1:9900/dashboard?secret="$SECRET" | grep -q 'mypeople dashboard'

echo "[verify] kill"
mp kill "$HOST"/verify:w1
mp status | grep -q "$HOST/verify:w1.*dead"

echo ""
echo "[verify] Control plane OK."
echo "[verify] Next: test a real prompt with 'mp send <agent-id> \"...\"' (requires kimi login)."
