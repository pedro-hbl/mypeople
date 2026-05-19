# SEED: mypeople-01-foundation

> seed-format: 1

## Goal

Stand up the **mypeople runtime** on a fresh Debian-12-class Linux host with
`claude` already installed. After this seed runs, two daemons are alive
locally — `queue-server` (HTTP on 127.0.0.1:9900) and `queue-client` (a
heartbeat client) — and the `mp` CLI can ask the server for state. No
agents are spawned yet. This is the foundation every subsequent SEED
builds on.

## Done

All of these must be true. Each is independently verifiable from a fresh
shell, with no help from the agent's transcript.

- `curl -fsS http://127.0.0.1:9900/health` returns HTTP 200 with body containing `"ok"`.
- Two python processes are alive: one running `queue-server.py`, one running `queue-client.py`. Both visible in `ps -ax`.
- `~/.config/mypeople/queue.env` exists and contains a non-empty `QUEUE_URL` and `QUEUE_SECRET`.
- `mp status` exits 0, prints `No active agents.`, and lists the local host under "client(s) heartbeating".
- A second `mp status` invocation 35 seconds later shows the local host's "last seen" counter ≤ 30 seconds (proves the heartbeat loop is alive).

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `QUEUE_PORT` | no | `9900` | `! ss -ltn 2>/dev/null \| awk '{print $4}' \| grep -q ":${QUEUE_PORT:-9900}\$"` (port free) | "TCP port for queue-server on 127.0.0.1 (default 9900). Press Enter to accept." |
| `QUEUE_SECRET` | no | (auto-generated 32-byte hex) | `[ -s "$HOME/.config/mypeople/queue.env" ] && grep -q 'QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"` | "Shared HMAC-style secret for queue-server. If you've installed mypeople before and want to reuse the existing secret, the agent will detect it. Otherwise press Enter to auto-generate." |
| `INSTALL_DIR` | no | `$HOME/mypeople` | `[ -d "$INSTALL_DIR" ]` | "Install directory for mypeople runtime (default `$HOME/mypeople`)." |
| OS deps (`tmux python3 jq`) | yes | (apt-installed) | `command -v tmux && command -v python3 && command -v jq` (all must exist) | (no prompt — agent runs `sudo apt-get install -y tmux python3 jq` non-interactively) |
| claude CLI | yes | (already present) | `command -v claude` | (no prompt — agent stops with `BLOCKED_REASON=claude_not_installed` if missing) |

## Components

| Component | Source | Version constraint |
|---|---|---|
| `queue-server.py` | **inline in this seed** (see Step 3) | matches this seed verbatim |
| `queue-client.py` | **inline in this seed** (see Step 4) | matches this seed verbatim |
| `mp` CLI | **inline in this seed** (see Step 5) | matches this seed verbatim |
| `tmux` | Debian apt: `tmux` | any |
| `python3` | Debian apt: `python3` (stdlib only — no pip deps) | >= 3.9 |
| `jq` | Debian apt: `jq` | any |

**No git clone. No pip install. No npm install. The seed text is the source.**

## Steps

### 0. Interview (mandatory)

Run the `detect` for every row in `## Inputs`. Send ONE message to the
user that lists:
- ✓ inputs already satisfied (e.g. existing secret detected, port free)
- ✗ inputs needing user input
- ⚠ pre-existing state (e.g. an old `~/mypeople/` directory — ask: overwrite or abort?)

Wait for the user's reply. From here on, no further questions: the agent
runs to Done or to a `BLOCKED_REASON=` line.

### 1. Install OS dependencies

**Why**: `tmux` carries every agent pane; `python3` runs the daemons; `jq` is used by future SEEDs' Verify scripts (cheap to install now).
```bash
sudo apt-get update -qq
sudo apt-get install -y tmux python3 jq
```

### 2. Create directory layout

**Why**: predictable paths for daemon code, runtime PIDs/logs, and per-agent status files (the latter is unused in SEED 1 but reserved for SEED 3).
```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$INSTALL_DIR/status"
mkdir -p "$HOME/.config/mypeople"
```

### 3. Write `queue-server.py` from the inline heredoc below

**Why**: the queue-server is the single source of truth for who's alive and what tasks are pending. SEED 1 only exposes `/health`, `/heartbeat`, `/clients`, `/agents`. Later SEEDs add `/task/submit`, `/task/poll`, etc.

```bash
cat > "$INSTALL_DIR/bin/queue-server.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-server — foundation (SEED 1).

Endpoints:
  GET  /health           — 200 ok, public (no secret).
  GET  /agents           — list registered agents (empty in SEED 1).
  GET  /clients          — list heartbeating clients.
  POST /heartbeat        — body {"hostname":"..."}; refresh client liveness.

All endpoints except /health require header X-Queue-Secret: <SECRET>.
"""

import http.server, json, os, sys, threading, time
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

PORT = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET = os.environ.get("QUEUE_SECRET", "")
START_TS = time.time()

clients_lock = threading.Lock()
clients = {}   # hostname -> {"ts": float}
agents_lock = threading.Lock()
agents = {}    # agent_id -> {"state": str, "host": str, "ts": float}


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok_secret(self):
        return self.headers.get("X-Queue-Secret", "") == SECRET

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} {fmt % args}\n")

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            return self._json(200, {"status": "ok", "uptime": int(time.time() - START_TS)})
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        if p == "/clients":
            with clients_lock:
                return self._json(200, [{"hostname": h, **v} for h, v in clients.items()])
        if p == "/agents":
            with agents_lock:
                return self._json(200, [{"agent_id": k, **v} for k, v in agents.items()])
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        p = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})
        if p == "/heartbeat":
            host = (data.get("hostname") or "").strip()
            if not host:
                return self._json(400, {"error": "hostname required"})
            with clients_lock:
                clients[host] = {"ts": time.time()}
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "not found"})


class ThreadingServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    if not SECRET:
        print("FATAL: QUEUE_SECRET not set", file=sys.stderr)
        sys.exit(1)
    server = ThreadingServer(("127.0.0.1", PORT), Handler)
    print(f"queue-server listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-server.py"
```

### 4. Write `queue-client.py` from the inline heredoc below

**Why**: the client proves "this host is alive and reachable." For SEED 1 its only job is the heartbeat loop. SEED 2 extends it to also poll for tasks (spawn, send, etc.).

```bash
cat > "$INSTALL_DIR/bin/queue-client.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-client — foundation (SEED 1).

Heartbeats to the queue-server every QUEUE_HEARTBEAT seconds (default 30).
"""

import json, os, socket, sys, time, urllib.error, urllib.request

QUEUE_URL = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900")
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
HOSTNAME = socket.gethostname()


def post_json(path, data):
    req = urllib.request.Request(
        f"{QUEUE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Queue-Secret": SECRET},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    if not SECRET:
        print("FATAL: QUEUE_SECRET not set", file=sys.stderr)
        sys.exit(1)
    print(f"queue-client started, heartbeat={HEARTBEAT}s, host={HOSTNAME}", flush=True)
    while True:
        try:
            post_json("/heartbeat", {"hostname": HOSTNAME})
            print(f"{time.strftime('%H:%M:%S')} heartbeat ok", flush=True)
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} heartbeat FAILED: {e}", file=sys.stderr, flush=True)
        time.sleep(HEARTBEAT)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-client.py"
```

### 5. Write the `mp` CLI from the inline heredoc below

**Why**: a single command users type. SEED 1 only ships `mp status`. Subsequent SEEDs add `spawn`, `send`, `peek`, `kill`.

```bash
cat > "$INSTALL_DIR/bin/mp" <<'PY_EOF'
#!/usr/bin/env python3
"""mp — mypeople CLI (foundation SEED 1).

Subcommands: status
"""

import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "queue.env"


def load_env():
    cfg = {}
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg["QUEUE_URL"] = os.environ.get("QUEUE_URL", cfg.get("QUEUE_URL", "http://127.0.0.1:9900"))
    cfg["QUEUE_SECRET"] = os.environ.get("QUEUE_SECRET", cfg.get("QUEUE_SECRET", ""))
    return cfg


def http_get(url, secret):
    req = urllib.request.Request(url, headers={"X-Queue-Secret": secret})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def cmd_status(cfg):
    url = cfg["QUEUE_URL"]
    secret = cfg["QUEUE_SECRET"]
    if not secret:
        print("FATAL: QUEUE_SECRET not configured", file=sys.stderr)
        sys.exit(1)
    try:
        agents = http_get(f"{url}/agents", secret)
        clients = http_get(f"{url}/clients", secret)
    except urllib.error.URLError as e:
        print(f"queue-server unreachable at {url}: {e}", file=sys.stderr)
        sys.exit(1)
    if not agents:
        print("No active agents.")
    else:
        for a in agents:
            print(f"  {a['agent_id']} [{a.get('state','?')}] @ {a.get('host','?')}")
    print(f"\n{len(clients)} client(s) heartbeating:")
    now = time.time()
    for c in clients:
        age = int(now - c["ts"])
        print(f"  {c['hostname']} (last seen {age}s ago)")


def main():
    if len(sys.argv) < 2:
        print("Usage: mp <command>\n\nCommands: status", file=sys.stderr)
        sys.exit(2)
    cfg = load_env()
    cmd = sys.argv[1]
    if cmd == "status":
        return cmd_status(cfg)
    print(f"Unknown command: {cmd}\n\nCommands: status", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/mp"

# Symlink mp onto PATH (~/.local/bin is on PATH in Debian; create if missing)
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/bin/mp" "$HOME/.local/bin/mp"
```

### 6. Write `queue.env` (config the daemons + CLI read)

**Why**: a single file holds the URL + secret so daemons and CLI agree without env-var passing.

```bash
# Use existing secret if present (idempotency); otherwise generate.
if [ -s "$HOME/.config/mypeople/queue.env" ] && grep -q '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"; then
  SECRET=$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | head -1 | cut -d= -f2- | tr -d "\"'")
else
  SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fi
QUEUE_PORT="${QUEUE_PORT:-9900}"
cat > "$HOME/.config/mypeople/queue.env" <<EOF
QUEUE_URL=http://127.0.0.1:${QUEUE_PORT}
QUEUE_SECRET=${SECRET}
QUEUE_PORT=${QUEUE_PORT}
QUEUE_HEARTBEAT=30
EOF
chmod 600 "$HOME/.config/mypeople/queue.env"
```

### 7. Start `queue-server` (background, write PID)

**Why**: server must be up before client first heartbeats.
```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a
nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" \
  > "$INSTALL_DIR/run/queue-server.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-server.pid"

# Wait up to 5s for /health to respond before continuing.
for i in $(seq 1 25); do
  if curl -fsS "http://127.0.0.1:${QUEUE_PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
curl -fsS "http://127.0.0.1:${QUEUE_PORT}/health" >/dev/null || {
  echo "BLOCKED_REASON=queue_server_failed_to_start"
  tail -20 "$INSTALL_DIR/run/queue-server.log" >&2
  exit 1
}
```

### 8. Start `queue-client` (background, write PID)

```bash
nohup python3 -u "$INSTALL_DIR/bin/queue-client.py" \
  > "$INSTALL_DIR/run/queue-client.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-client.pid"
```

### 9. Sanity-print the running state

```bash
sleep 1
echo "---"
echo "INSTALL_DIR=$INSTALL_DIR"
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o pid,command 2>/dev/null
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o pid,command 2>/dev/null
mp status || true
echo "SEED_RESULT=DONE"
```

## Verify

This script is the truth. Run it from a fresh shell; exit 0 = Done.

```bash
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"

# 1. /health responds 200 with body containing "ok"
BODY=$(curl -fsS http://127.0.0.1:9900/health) || { echo "FAIL: /health unreachable"; exit 1; }
echo "$BODY" | grep -q '"status": *"ok"' || { echo "FAIL: /health body unexpected: $BODY"; exit 1; }

# 2. Both daemons alive
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o command= 2>/dev/null | grep -q queue-server.py || { echo "FAIL: queue-server.py not running"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: queue-client.py not running"; exit 1; }

# 3. queue.env exists with required keys
[ -f "$HOME/.config/mypeople/queue.env" ] || { echo "FAIL: queue.env missing"; exit 1; }
grep -qE '^QUEUE_URL=https?://[^[:space:]]+' "$HOME/.config/mypeople/queue.env" || { echo "FAIL: QUEUE_URL not set"; exit 1; }
grep -qE '^QUEUE_SECRET=[a-f0-9]{32,}' "$HOME/.config/mypeople/queue.env" || { echo "FAIL: QUEUE_SECRET not set"; exit 1; }

# 4. `mp status` exits 0, says "No active agents.", lists local host as heartbeating
OUT=$(mp status) || { echo "FAIL: mp status exited non-zero"; exit 1; }
echo "$OUT" | grep -q 'No active agents.' || { echo "FAIL: mp status didn't say 'No active agents.': $OUT"; exit 1; }
echo "$OUT" | grep -q "$(hostname)" || { echo "FAIL: mp status didn't list local hostname: $OUT"; exit 1; }

# 5. heartbeat loop alive — wait 35s and check the "last seen" counter drops below 31
sleep 35
OUT2=$(mp status)
AGE=$(echo "$OUT2" | grep "$(hostname)" | grep -oE 'last seen [0-9]+s' | grep -oE '[0-9]+')
[ -n "$AGE" ] || { echo "FAIL: couldn't parse last-seen age from: $OUT2"; exit 1; }
[ "$AGE" -le 30 ] || { echo "FAIL: heartbeat age $AGE > 30, client isn't refreshing"; exit 1; }

echo "VERIFY_OK"
```

## Failure modes

**Symptom: `BLOCKED_REASON=queue_server_failed_to_start`**
- Detect: `tail -20 $INSTALL_DIR/run/queue-server.log` shows `Address already in use`.
- Fix: another process is bound to `QUEUE_PORT`. Either kill it or rerun the Interview with a different port.

**Symptom: `mp status` prints `queue-server unreachable`**
- Detect: `! curl -fsS http://127.0.0.1:9900/health`.
- Fix: queue-server died. Re-run Step 7 (will pick up existing secret from `queue.env`).

**Symptom: `mp status` prints `FATAL: QUEUE_SECRET not configured`**
- Detect: `[ ! -s ~/.config/mypeople/queue.env ]` or the file lacks `QUEUE_SECRET=`.
- Fix: Re-run Step 6.

**Symptom: `mp: command not found`**
- Detect: `! command -v mp` after Step 5.
- Fix: `~/.local/bin` is not on `$PATH`. Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` and re-source.

## Cleanup

Returns the host to pre-SEED state so Verify re-runs from clean.

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"

# Stop daemons (best-effort)
for name in queue-client queue-server; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && kill "$(cat $pidfile)" 2>/dev/null || true
done

# Kill orphans by name (in case PID files are missing)
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true

# Remove runtime artifacts (preserve QUEUE_SECRET for idempotent re-runs unless --hard)
rm -rf "$INSTALL_DIR/run" "$INSTALL_DIR/bin"
# Note: $HOME/.config/mypeople/queue.env is preserved by design — re-runs reuse the secret.
# To fully reset: rm -rf $HOME/.config/mypeople $INSTALL_DIR
```
