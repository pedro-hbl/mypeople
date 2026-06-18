#!/usr/bin/env bash
# mypeople install script for WSL / Ubuntu / Debian.
#
# Sets up:
#   - ~/.config/mypeople/queue.env (queue URL + secret)
#   - ~/.kimi/config.toml hook entries for mypeople
#   - symlinks mp into ~/.local/bin
#
# Run from the repo root:
#   ./scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MYPEOPLE_DIR="$HOME/.config/mypeople"
KIMI_CONFIG="$HOME/.kimi/config.toml"
LOCAL_BIN="$HOME/.local/bin"

mkdir -p "$MYPEOPLE_DIR" "$LOCAL_BIN"

# ---------------------------------------------------------------------------
# Kimi login check
# ---------------------------------------------------------------------------
echo "[install] Reminder: ensure 'kimi login' has been run in WSL."
echo "[install] mp send / worker prompts require an active Kimi session."

# ---------------------------------------------------------------------------
# Queue configuration
# ---------------------------------------------------------------------------
if [[ -f "$MYPEOPLE_DIR/queue.env" ]]; then
  echo "[install] $MYPEOPLE_DIR/queue.env already exists; leaving it in place."
else
  SECRET="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$MYPEOPLE_DIR/queue.env" <<EOF
QUEUE_URL=http://127.0.0.1:9900
QUEUE_SECRET=$SECRET
HOST_ID=$(hostname)
EOF
  echo "[install] wrote $MYPEOPLE_DIR/queue.env"
fi

# ---------------------------------------------------------------------------
# Kimi hooks
# ---------------------------------------------------------------------------
HOOK_PATH="$REPO_DIR/hooks/mypeople-hook.py"
chmod +x "$HOOK_PATH"

mkdir -p "$(dirname "$KIMI_CONFIG")"

# Remove the default empty `hooks = []` array if present; it conflicts with
# `[[hooks]]` array-of-tables syntax.
if [ -f "$KIMI_CONFIG" ]; then
  sed -i '/^[[:space:]]*hooks[[:space:]]*=[[:space:]]*\[\][[:space:]]*$/d' "$KIMI_CONFIG"
fi

# Helper: append a hook block if the command is not already registered.
add_hook() {
  local event="$1"
  local matcher="${2:-}"
  if [[ -f "$KIMI_CONFIG" ]] && grep -qF "command = \"$HOOK_PATH\"" "$KIMI_CONFIG" && grep -qF "event = \"$event\"" "$KIMI_CONFIG"; then
    return
  fi
  {
    echo ""
    echo "[[hooks]]"
    echo "event = \"$event\""
    if [[ -n "$matcher" ]]; then
      echo "matcher = \"$matcher\""
    fi
    echo "command = \"$HOOK_PATH\""
  } >> "$KIMI_CONFIG"
}

add_hook "SessionStart"
add_hook "Stop"
add_hook "StopFailure"
add_hook "SessionEnd"
add_hook "PreToolUse" "AskUserQuestion"

echo "[install] registered hooks in $KIMI_CONFIG"

# ---------------------------------------------------------------------------
# CLI symlink
# ---------------------------------------------------------------------------
MP_SRC="$REPO_DIR/src/mypeople/mp"
chmod +x "$MP_SRC"
if [[ -L "$LOCAL_BIN/mp" ]]; then
  rm "$LOCAL_BIN/mp"
fi
ln -s "$MP_SRC" "$LOCAL_BIN/mp"
echo "[install] linked mp -> $MP_SRC"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "mypeople for Kimi installed."
echo ""
echo "Next steps:"
echo "  1. Start the queue server:  ./scripts/start-queue-server.sh"
echo "  2. Open the dashboard:       http://127.0.0.1:9900/dashboard"
echo "  3. Start the Boss in Brave:  ./scripts/start-boss.sh"
echo "  4. Spawn workers:            mp spawn <host>/<session>:<tab> --cwd <dir>"
