# SEED: mypeople-02-core-loop

> seed-format: 1

## Goal

Extend the foundation runtime (`SEED 1`) with the **core agent loop**: spawn a Claude Code agent into a tmux pane, send it a message, peek what's on screen, kill it. Every action goes through the HTTP queue (no direct tmux bypass anywhere — fire-and-forget doctrine). Per-spawn `tmux-boss-hooks` plugin is loaded so spawned claudes will (in SEED 3) emit lifecycle events back.

This seed is a **superset** of SEED 1 — paste it into a fresh container and you get both the foundation AND the core agent loop. SEED 1 is a dev milestone, not a ship target.

## Done

Each is independently verifiable from a fresh shell, no help from the agent's transcript.

- `curl -fsS http://127.0.0.1:9900/health` returns 200 with `"status": "ok"` (from SEED 1).
- Both daemons alive (`queue-server`, `queue-client`) in `ps`.
- `mp status` exits 0 and lists the local host as a heartbeating client (from SEED 1).
- `mp spawn box1/test:w1 --backend claude` creates a tmux window `mc-test:w1` and a claude process is running inside it with `--plugin-dir` pointing at `~/mypeople/plugins/tmux-boss-hooks`.
- `mp send box1/test:w1 "echo MARK-XYZ"` delivers the message; within 5s, `tmux capture-pane -t mc-test:w1 -p` contains the literal string `MARK-XYZ`.
- `mp peek box1/test:w1` returns a non-empty string equal to what `tmux capture-pane -t mc-test:w1 -p` would print (peek goes through the queue, NOT via direct capture-pane).
- `mp kill box1/test:w1` removes the tmux window; `tmux list-windows -t mc-test` does not list `w1`.
- `mp status` after kill no longer lists `box1/test:w1`.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `QUEUE_PORT` | no | `9900` | port free or already-bound by our own queue-server | "TCP port for queue-server (default 9900)" |
| `QUEUE_SECRET` | no | (auto-generated if absent) | `[ -s "$HOME/.config/mypeople/queue.env" ] && grep -q QUEUE_SECRET= "$HOME/.config/mypeople/queue.env"` | "Reuse existing secret if present; else auto-generate." |
| `INSTALL_DIR` | no | `$HOME/mypeople` | dir exists | "Install dir (default `$HOME/mypeople`)" |
| `HOST_ID` | no | `$(hostname -s)` | always available | "Short hostname for the global agent-id scheme `<host>/<session>:<tab>`. Default: container's hostname." |
| OS deps (`tmux python3 jq procps`) | yes | apt-installed | `command -v tmux && command -v python3 && command -v jq && command -v ps` | (no prompt — agent runs `sudo apt-get install -y tmux python3 jq procps` non-interactively. `procps` provides `ps`, which the minimal Debian-slim image lacks.) |
| claude CLI | yes | already present | `command -v claude` | `BLOCKED_REASON=claude_not_installed` if missing |

## Components

| Component | Source | Notes |
|---|---|---|
| `queue-server.py` | **inline in this seed** | adds task queue endpoints on top of SEED 1's clients/agents |
| `queue-client.py` | **inline in this seed** | adds task-poll loop; executes spawn/send/peek/kill via tmux |
| `mp` CLI | **inline in this seed** | adds `spawn`, `send`, `peek`, `kill` verbs |
| `plugins/tmux-boss-hooks/` | **inline in this seed** | per-spawn plugin; in this seed it's installed but only `SessionStart` / `SessionEnd` events emit (Stop-hook routing comes in SEED 3) |
| OS pkgs | apt: `tmux python3 jq procps` | |

**No git clone. No pip install. The seed text is the source.**

## Steps

### 0. Interview (mandatory)

Run `detect` for every row in `## Inputs`. Send ONE consolidated message to the CEO listing:
- ✓ inputs already satisfied (reuse existing secret if present)
- ✗ inputs needing input (likely none — almost everything has a sensible default)
- ⚠ pre-existing state to confirm (e.g. existing tmux session `mc-test` would conflict)

Wait for CEO reply. From there: run to Done autonomously.

### 1. Install OS deps

```bash
sudo apt-get update -qq
sudo apt-get install -y tmux python3 jq procps
```

### 2. Stop any prior daemons (idempotent restart)

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
for name in queue-client queue-server; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && kill "$(cat $pidfile)" 2>/dev/null || true
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true
```

### 3. Create directory layout (idempotent)

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$INSTALL_DIR/status" "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin" "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks"
mkdir -p "$HOME/.config/mypeople" "$HOME/.local/bin"
```

### 3.5. Pre-accept the trust dialog in `~/.claude.json` for spawn directories

**Why**: when we spawn `claude --dangerously-skip-permissions ...` into a directory, claude STILL shows a "Is this a project you trust?" dialog if the directory's `hasTrustDialogAccepted` flag isn't set in `~/.claude.json`. `--dangerously-skip-permissions` does not bypass this dialog. Without this step, every spawned claude blocks on the trust prompt and never reaches the input loop. We pre-accept it for `$HOME` and `$INSTALL_DIR` (the default spawn cwds).

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / ".claude.json"
try:
    data = json.loads(path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
data.setdefault("projects", {})
for d in [str(Path.home()), os.environ.get("INSTALL_DIR", str(Path.home() / "mypeople"))]:
    data["projects"].setdefault(d, {})
    data["projects"][d]["hasTrustDialogAccepted"] = True
path.write_text(json.dumps(data, indent=2))
path.chmod(0o600)
print("trusted:", list(data["projects"].keys()))
PY
```

After this Step, when `entrypoint.sh` snapshots `~/.claude.json` next, the trusted flag will persist into the volume's `.app-config-snapshot.json` — so even brand-new containers restored from snapshot will already have the trust flag set.

### 4. Write `queue-server.py` (extended)

```bash
cat > "$INSTALL_DIR/bin/queue-server.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-server — core loop (SEED 2).

Endpoints (all require X-Queue-Secret except /health):
  GET  /health                 — 200 ok, public.
  POST /heartbeat              — client liveness {"hostname":...}.
  GET  /clients                — list known clients.
  GET  /agents                 — list registered agents.
  POST /agents/register        — client → server: agent now exists.
  POST /agents/unregister      — client → server: agent gone.
  POST /task/submit            — caller (CLI / agent) submits a task. Returns {task_id}.
  GET  /task/poll?hostname=H   — queue-client polls for next pending task for its host.
  POST /task/result            — queue-client reports task completion.
  GET  /task/<id>              — caller fetches result.

Task shapes:
  spawn:  {"action":"spawn", "target_host":H, "payload":{"agent_id":"H/sess:tab","backend":"claude","cwd":"..."}}
  send:   {"action":"send",  "target_agent":"H/sess:tab", "payload":{"message":"..."}}
  peek:   {"action":"peek",  "target_agent":"H/sess:tab"}
  kill:   {"action":"kill",  "target_agent":"H/sess:tab"}
"""

import http.server, json, os, sys, threading, time, uuid
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET = os.environ.get("QUEUE_SECRET", "")
START_TS = time.time()

_lock = threading.Lock()
clients = {}     # hostname -> {"ts": float}
agents = {}      # agent_id -> {"host":..., "session":..., "tab":..., "backend":..., "state":..., "ts":...}
tasks = {}       # task_id -> {"status": pending|running|done|failed, "action", "target_host", "target_agent", "payload", "result", "error", "submitted_ts", "completed_ts"}


def _host_of(agent_id):
    # agent_id is "<host>/<session>:<tab>"
    if "/" in agent_id and ":" in agent_id:
        return agent_id.split("/", 1)[0]
    return ""


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

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/health":
            return self._json(200, {"status": "ok", "uptime": int(time.time() - START_TS)})
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        if p == "/clients":
            with _lock:
                return self._json(200, [{"hostname": h, **v} for h, v in clients.items()])
        if p == "/agents":
            with _lock:
                return self._json(200, [{"agent_id": k, **v} for k, v in agents.items()])
        if p == "/task/poll":
            qs = parse_qs(u.query)
            host = (qs.get("hostname", [""])[0]).strip()
            if not host:
                return self._json(400, {"error": "hostname required"})
            with _lock:
                for tid, t in tasks.items():
                    if t["status"] == "pending" and t.get("target_host", "") == host:
                        t["status"] = "running"
                        t["picked_ts"] = time.time()
                        return self._json(200, {"task_id": tid, **t})
            return self._json(200, {})  # empty body = no pending tasks
        if p.startswith("/task/"):
            tid = p.split("/")[-1]
            with _lock:
                t = tasks.get(tid)
                if not t:
                    return self._json(404, {"error": "no such task"})
                return self._json(200, {"task_id": tid, **t})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        p = u.path
        data = self._read_json()
        if data is None:
            return self._json(400, {"error": "bad json"})

        if p == "/heartbeat":
            host = (data.get("hostname") or "").strip()
            if not host:
                return self._json(400, {"error": "hostname required"})
            with _lock:
                clients[host] = {"ts": time.time()}
            return self._json(200, {"ok": True})

        if p == "/agents/register":
            aid = data.get("agent_id", "").strip()
            if not aid or "/" not in aid or ":" not in aid:
                return self._json(400, {"error": "agent_id must be <host>/<session>:<tab>"})
            host_part, rest = aid.split("/", 1)
            sess, tab = rest.split(":", 1)
            with _lock:
                agents[aid] = {
                    "host": host_part, "session": sess, "tab": tab,
                    "backend": data.get("backend", ""),
                    "state": data.get("state", "alive"),
                    "ts": time.time(),
                }
            return self._json(200, {"ok": True})

        if p == "/agents/unregister":
            aid = data.get("agent_id", "").strip()
            with _lock:
                agents.pop(aid, None)
            return self._json(200, {"ok": True})

        if p == "/task/submit":
            action = data.get("action", "")
            if action not in ("spawn", "send", "peek", "kill"):
                return self._json(400, {"error": f"unknown action {action!r}"})
            tid = uuid.uuid4().hex
            t = {
                "status": "pending",
                "action": action,
                "target_host": data.get("target_host", "") or _host_of(data.get("target_agent", "")),
                "target_agent": data.get("target_agent", ""),
                "payload": data.get("payload", {}),
                "result": None,
                "error": "",
                "submitted_ts": time.time(),
            }
            if not t["target_host"]:
                return self._json(400, {"error": "target_host or target_agent (containing host) required"})
            with _lock:
                tasks[tid] = t
            return self._json(200, {"task_id": tid})

        if p == "/task/result":
            tid = data.get("task_id", "")
            with _lock:
                t = tasks.get(tid)
                if not t:
                    return self._json(404, {"error": "no such task"})
                t["status"] = "done" if data.get("ok") else "failed"
                t["result"] = data.get("result")
                t["error"] = data.get("error", "")
                t["completed_ts"] = time.time()
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

### 5. Write `queue-client.py` (extended)

```bash
cat > "$INSTALL_DIR/bin/queue-client.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-client — core loop (SEED 2).

Two threads:
  - heartbeat loop: POST /heartbeat every QUEUE_HEARTBEAT seconds.
  - task-poll loop: GET /task/poll?hostname=$HOSTNAME; execute; POST /task/result.

Task execution:
  spawn — tmux new-session/new-window; exec `claude --plugin-dir ...` with env vars.
  send  — tmux send-keys with bracketed-paste markers; sleep 0.1; Enter.
  peek  — tmux capture-pane -p (this is the ONLY place capture-pane is allowed;
          callers must go through the queue, not bypass).
  kill  — tmux kill-window (or kill-session if last tab).
"""

import json, os, shlex, socket, subprocess, sys, threading, time, urllib.error, urllib.request

QUEUE_URL = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900")
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
POLL_INTERVAL = float(os.environ.get("QUEUE_POLL_INTERVAL", "1.0"))
HOSTNAME = os.environ.get("HOST_ID", "") or socket.gethostname()
INSTALL_DIR = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
PLUGIN_DIR = os.path.join(INSTALL_DIR, "plugins", "tmux-boss-hooks")

PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"


def post_json(path, data):
    req = urllib.request.Request(
        f"{QUEUE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Queue-Secret": SECRET},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_json(path):
    req = urllib.request.Request(f"{QUEUE_URL}{path}", headers={"X-Queue-Secret": SECRET})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def heartbeat_loop():
    while True:
        try:
            post_json("/heartbeat", {"hostname": HOSTNAME})
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} heartbeat FAIL: {e}", file=sys.stderr, flush=True)
        time.sleep(HEARTBEAT)


def tmux_run(*args, timeout=5):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)


def tmux_send_text(target, text):
    """Bracketed-paste safe send + Enter."""
    safe = text.replace(PASTE_END, "").replace(PASTE_START, "")
    payload = f"{PASTE_START}{safe}{PASTE_END}"
    r = tmux_run("send-keys", "-t", target, "-l", "--", payload)
    if r.returncode != 0:
        return False, r.stderr.strip()
    time.sleep(0.1)
    r = tmux_run("send-keys", "-t", target, "Enter")
    if r.returncode != 0:
        return False, r.stderr.strip()
    return True, ""


def parse_agent_id(aid):
    """`H/sess:tab` → (host, session, tab). Returns None on bad input."""
    if "/" not in aid or ":" not in aid:
        return None
    host, rest = aid.split("/", 1)
    if ":" not in rest:
        return None
    sess, tab = rest.split(":", 1)
    return host, sess, tab


def execute_spawn(task):
    payload = task.get("payload", {})
    aid = payload.get("agent_id", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad agent_id"
    _, sess, tab = parsed
    backend = payload.get("backend", "claude")
    cwd = payload.get("cwd", os.path.expanduser("~"))
    mc_sess = f"mc-{sess}"

    # Create session if missing (with this tab as first window), else add a new window.
    has_sess = tmux_run("has-session", "-t", mc_sess).returncode == 0
    if not has_sess:
        r = tmux_run("new-session", "-d", "-s", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-session failed: {r.stderr.strip()}"
    else:
        # Check window doesn't already exist.
        wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
        if tab in wins:
            return False, f"window {tab} already exists in {mc_sess}"
        r = tmux_run("new-window", "-t", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-window failed: {r.stderr.strip()}"

    # Build the exec command: env vars + claude with plugin-dir + settings.
    if backend == "claude":
        spawn_cmd = (
            f"claude --dangerously-skip-permissions "
            f"--settings {shlex.quote(json.dumps({'skipDangerousModePermissionPrompt': True}))} "
            f"--plugin-dir {shlex.quote(PLUGIN_DIR)}"
        )
    else:
        return False, f"backend {backend!r} not supported in SEED 2"

    env_parts = [
        f"export AGENT_NAME={shlex.quote(tab)}",
        f"export AGENT_SESSION={shlex.quote(mc_sess)}",
        f"export AGENT_ID={shlex.quote(aid)}",
        f"export QUEUE_URL={shlex.quote(QUEUE_URL)}",
        f"export QUEUE_SECRET={shlex.quote(SECRET)}",
        f"export HOST_ID={shlex.quote(HOSTNAME)}",
    ]
    shell_cmd = f"cd {shlex.quote(cwd)} && {' && '.join(env_parts)} && exec {spawn_cmd}"

    target = f"{mc_sess}:{tab}"
    ok, err = tmux_send_text(target, shell_cmd)
    if not ok:
        return False, f"shell-cmd send failed: {err}"

    # Wait for the spawned claude TUI to be truly ready before declaring the
    # spawn successful. Claude runs an auto-update probe at startup that eats
    # the first ~few keystrokes — if we return immediately, the caller's next
    # `mp send` lands in a dead pane and the message is dropped. The signal we
    # wait for is the "bypass permissions on" banner that claude renders once
    # its input loop is alive. 30s budget should cover slow first-startups.
    if backend == "claude":
        deadline = time.time() + 30
        while time.time() < deadline:
            r = tmux_run("capture-pane", "-t", target, "-p")
            if "bypass permissions on" in (r.stdout or ""):
                break
            time.sleep(0.5)
        else:
            return False, "claude TUI didn't show 'bypass permissions on' banner within 30s"

    # Register the agent with the server.
    try:
        post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive"})
    except urllib.error.URLError as e:
        return False, f"register failed: {e}"

    return True, {"agent_id": aid, "tmux_target": target}


def execute_send(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    target = f"mc-{sess}:{tab}"
    if tmux_run("has-session", "-t", f"mc-{sess}").returncode != 0:
        return False, f"session mc-{sess} does not exist"
    msg = task.get("payload", {}).get("message", "")
    ok, err = tmux_send_text(target, msg)
    if not ok:
        return False, err
    return True, {"delivered_to": target}


def execute_peek(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    target = f"mc-{sess}:{tab}"
    if tmux_run("has-session", "-t", f"mc-{sess}").returncode != 0:
        return False, f"session mc-{sess} does not exist"
    r = tmux_run("capture-pane", "-t", target, "-p", "-S", "-200")
    if r.returncode != 0:
        return False, r.stderr.strip()
    return True, {"content": r.stdout}


def execute_kill(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    mc_sess = f"mc-{sess}"
    target = f"{mc_sess}:{tab}"
    if tmux_run("has-session", "-t", mc_sess).returncode != 0:
        # Already gone — unregister and call it done.
        try:
            post_json("/agents/unregister", {"agent_id": aid})
        except urllib.error.URLError:
            pass
        return True, {"already_gone": True}
    # Kill the window. If it's the last window, kill the session.
    wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
    if len(wins) <= 1:
        r = tmux_run("kill-session", "-t", mc_sess)
    else:
        r = tmux_run("kill-window", "-t", target)
    if r.returncode != 0:
        return False, r.stderr.strip()
    try:
        post_json("/agents/unregister", {"agent_id": aid})
    except urllib.error.URLError:
        pass
    return True, {"killed": target}


HANDLERS = {
    "spawn": execute_spawn,
    "send": execute_send,
    "peek": execute_peek,
    "kill": execute_kill,
}


def task_loop():
    while True:
        try:
            task = get_json(f"/task/poll?hostname={urllib.parse.quote(HOSTNAME)}")
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} poll FAIL: {e}", file=sys.stderr, flush=True)
            time.sleep(POLL_INTERVAL)
            continue
        if not task:
            time.sleep(POLL_INTERVAL)
            continue
        tid = task.get("task_id")
        action = task.get("action", "")
        handler = HANDLERS.get(action)
        if not handler:
            try:
                post_json("/task/result", {"task_id": tid, "ok": False, "error": f"unknown action {action!r}"})
            except urllib.error.URLError:
                pass
            continue
        try:
            ok, payload = handler(task)
        except Exception as e:
            ok, payload = False, f"handler raised: {e}"
        try:
            if ok:
                post_json("/task/result", {"task_id": tid, "ok": True, "result": payload})
            else:
                post_json("/task/result", {"task_id": tid, "ok": False, "error": str(payload)})
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} result POST FAIL: {e}", file=sys.stderr, flush=True)
        print(f"{time.strftime('%H:%M:%S')} task {tid[:8]} {action} → ok={ok}", flush=True)


def main():
    if not SECRET:
        print("FATAL: QUEUE_SECRET not set", file=sys.stderr)
        sys.exit(1)
    print(f"queue-client started, host={HOSTNAME}, heartbeat={HEARTBEAT}s, poll={POLL_INTERVAL}s", flush=True)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    task_loop()


if __name__ == "__main__":
    import urllib.parse  # used in task_loop
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-client.py"
```

### 6. Write the `mp` CLI (extended)

```bash
cat > "$INSTALL_DIR/bin/mp" <<'PY_EOF'
#!/usr/bin/env python3
"""mp — mypeople CLI (SEED 2).

Verbs: status, spawn, send, peek, kill.

Everything except `status` goes via the queue (fire-and-forget):
  - submit task → get task_id
  - poll /task/<id> until status != pending
  - for `peek`: print the captured content
  - for `spawn`: print the new agent_id
"""

import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "queue.env"
DEFAULT_TIMEOUT = 30  # seconds to wait for task completion
POLL_INTERVAL = 0.3


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
    cfg["HOST_ID"] = os.environ.get("HOST_ID", cfg.get("HOST_ID", "")) or _hostname()
    return cfg


def _hostname():
    import socket
    return socket.gethostname()


def http_get(url, secret):
    req = urllib.request.Request(url, headers={"X-Queue-Secret": secret})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def http_post(url, secret, data):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Queue-Secret": secret},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def canonicalize_agent_id(arg, host_id):
    """Accept either `H/sess:tab` or `sess:tab`; default host to local."""
    if "/" in arg and ":" in arg:
        return arg
    if ":" in arg:
        return f"{host_id}/{arg}"
    raise ValueError(f"agent_id must be <host>/<session>:<tab> or <session>:<tab>; got {arg!r}")


def submit_and_wait(cfg, body, timeout=DEFAULT_TIMEOUT):
    url, secret = cfg["QUEUE_URL"], cfg["QUEUE_SECRET"]
    r = http_post(f"{url}/task/submit", secret, body)
    tid = r.get("task_id")
    if not tid:
        raise RuntimeError(f"submit returned no task_id: {r}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = http_get(f"{url}/task/{tid}", secret)
        status = t.get("status")
        if status in ("done", "failed"):
            return t
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {tid} did not complete in {timeout}s")


def cmd_status(cfg, args):
    url, secret = cfg["QUEUE_URL"], cfg["QUEUE_SECRET"]
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
            print(f"  {a['agent_id']} [{a.get('state','?')}] backend={a.get('backend','?')}")
    print(f"\n{len(clients)} client(s) heartbeating:")
    now = time.time()
    for c in clients:
        age = int(now - c["ts"])
        print(f"  {c['hostname']} (last seen {age}s ago)")


def cmd_spawn(cfg, args):
    if len(args) < 1:
        print("Usage: mp spawn <agent_id> [--backend claude] [--cwd PATH]", file=sys.stderr)
        sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    backend = "claude"
    cwd = os.path.expanduser("~")
    i = 1
    while i < len(args):
        if args[i] == "--backend" and i + 1 < len(args):
            backend = args[i + 1]; i += 2
        elif args[i] == "--cwd" and i + 1 < len(args):
            cwd = args[i + 1]; i += 2
        else:
            print(f"unknown arg: {args[i]}", file=sys.stderr); sys.exit(2)
    target_host = aid.split("/", 1)[0]
    body = {"action": "spawn", "target_host": target_host,
            "payload": {"agent_id": aid, "backend": backend, "cwd": cwd}}
    t = submit_and_wait(cfg, body, timeout=20)
    if t["status"] == "done":
        r = t.get("result") or {}
        print(f"Spawned {r.get('agent_id', aid)}  [tmux={r.get('tmux_target','?')}]")
    else:
        print(f"Spawn FAILED: {t.get('error', '?')}", file=sys.stderr)
        sys.exit(1)


def cmd_send(cfg, args):
    if len(args) < 2:
        print("Usage: mp send <agent_id> <message>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    msg = " ".join(args[1:])
    body = {"action": "send", "target_agent": aid, "payload": {"message": msg}}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        print(f"Sent to {aid}")
    else:
        print(f"Send FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_peek(cfg, args):
    if len(args) < 1:
        print("Usage: mp peek <agent_id>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    body = {"action": "peek", "target_agent": aid}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        sys.stdout.write((t.get("result") or {}).get("content", ""))
    else:
        print(f"Peek FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


def cmd_kill(cfg, args):
    if len(args) < 1:
        print("Usage: mp kill <agent_id>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    body = {"action": "kill", "target_agent": aid}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        print(f"Killed {aid}")
    else:
        print(f"Kill FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


COMMANDS = {"status": cmd_status, "spawn": cmd_spawn, "send": cmd_send, "peek": cmd_peek, "kill": cmd_kill}


def main():
    if len(sys.argv) < 2:
        print("Usage: mp <command> [args]\n\nCommands: " + ", ".join(COMMANDS.keys()), file=sys.stderr); sys.exit(2)
    cfg = load_env()
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}\n\nCommands: " + ", ".join(COMMANDS.keys()), file=sys.stderr); sys.exit(2)
    return fn(cfg, rest)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/mp"
ln -sf "$INSTALL_DIR/bin/mp" "$HOME/.local/bin/mp"
```

### 7. Write the `tmux-boss-hooks` plugin (SessionStart + SessionEnd only in SEED 2)

```bash
cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "tmux-boss-hooks",
  "description": "Per-spawn lifecycle hooks for mypeople-managed agents.",
  "version": "1.0.0"
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/hooks.json" <<EOF
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event",
        "timeout": 5
      }]
    }],
    "SessionEnd": [{
      "hooks": [{
        "type": "command",
        "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event",
        "timeout": 5
      }]
    }]
  }
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event" <<'EOF'
#!/bin/bash
# Stub for SEED 2. Logs the lifecycle event locally; full HTTP routing comes in SEED 3.
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/run"
LOG="$INSTALL_DIR/run/hook-events.log"
INPUT=""
IFS= read -t 5 -d '' -r INPUT || true
if [ -z "$INPUT" ]; then exit 0; fi
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // "?"' 2>/dev/null)
SID=$(echo "$INPUT" | jq -r '.session_id // "?"' 2>/dev/null)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"ts\":\"$TS\",\"event\":\"$EVENT\",\"session_id\":\"$SID\",\"agent_id\":\"${AGENT_ID:-}\"}" >> "$LOG"
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event"
```

### 8. Write `queue.env` (preserve existing secret if present)

```bash
if [ -s "$HOME/.config/mypeople/queue.env" ] && grep -q '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"; then
  SECRET=$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | head -1 | cut -d= -f2- | tr -d "\"'")
else
  SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fi
QUEUE_PORT="${QUEUE_PORT:-9900}"
HOST_ID="${HOST_ID:-$(hostname -s)}"
cat > "$HOME/.config/mypeople/queue.env" <<EOF
QUEUE_URL=http://127.0.0.1:${QUEUE_PORT}
QUEUE_SECRET=${SECRET}
QUEUE_PORT=${QUEUE_PORT}
QUEUE_HEARTBEAT=30
QUEUE_POLL_INTERVAL=1.0
HOST_ID=${HOST_ID}
INSTALL_DIR=${INSTALL_DIR:-$HOME/mypeople}
EOF
chmod 600 "$HOME/.config/mypeople/queue.env"
```

### 9. Start daemons (with the new code)

```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a
nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" > "$INSTALL_DIR/run/queue-server.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-server.pid"
for i in $(seq 1 25); do
  curl -fsS "http://127.0.0.1:${QUEUE_PORT}/health" >/dev/null 2>&1 && break
  sleep 0.2
done
nohup python3 -u "$INSTALL_DIR/bin/queue-client.py" > "$INSTALL_DIR/run/queue-client.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-client.pid"
```

### 10. PATH fix (idempotent)

```bash
if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"
```

### 11. Sanity print

```bash
sleep 1
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o pid,command 2>/dev/null
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o pid,command 2>/dev/null
mp status || true
echo "SEED_RESULT=DONE"
```

## Verify

```bash
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
export PATH="$HOME/.local/bin:$PATH"
HOST_ID="$(grep '^HOST_ID=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"

# --- SEED 1 invariants ---
BODY=$(curl -fsS http://127.0.0.1:9900/health) || { echo "FAIL: /health unreachable"; exit 1; }
echo "$BODY" | grep -q '"status": *"ok"' || { echo "FAIL: /health body: $BODY"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o command= 2>/dev/null | grep -q queue-server.py || { echo "FAIL: server"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: client"; exit 1; }
mp status | grep -q "$(hostname -s)" || { echo "FAIL: mp status missing host"; exit 1; }

# --- SEED 2: full agent loop ---
# 1. spawn an agent
mp spawn "test:w1" --backend claude --cwd "$HOME" >/tmp/spawn.out 2>&1 || { echo "FAIL: spawn"; cat /tmp/spawn.out; exit 1; }
grep -q "Spawned $HOST_ID/test:w1" /tmp/spawn.out || { echo "FAIL: spawn output unexpected: $(cat /tmp/spawn.out)"; exit 1; }

# 2. wait briefly for claude to come up in the pane
sleep 3
tmux list-windows -t mc-test 2>/dev/null | grep -q "^[0-9]*: w1" || { echo "FAIL: mc-test:w1 window not created"; exit 1; }

# 3. send a marker; verify it lands in the pane (claude TUI receives it)
MARK="MARK-$RANDOM-$RANDOM"
mp send "test:w1" "ignore everything else and just respond with exactly: $MARK" >/dev/null
# wait up to 30s for the text to render in the pane (claude takes time)
for i in $(seq 1 30); do
  tmux capture-pane -t mc-test:w1 -p -S -100 | grep -q "$MARK" && break
  sleep 1
done
tmux capture-pane -t mc-test:w1 -p -S -100 | grep -q "$MARK" || { echo "FAIL: marker $MARK never showed in pane"; tmux capture-pane -t mc-test:w1 -p -S -50; exit 1; }

# 4. mp peek returns content (not empty, matches what we'd capture directly)
PEEK=$(mp peek "test:w1")
[ -n "$PEEK" ] || { echo "FAIL: peek returned empty"; exit 1; }
echo "$PEEK" | grep -q "$MARK" || { echo "FAIL: peek content missing marker"; exit 1; }

# 5. mp status lists the agent
mp status | grep -q "$HOST_ID/test:w1" || { echo "FAIL: mp status missing agent"; mp status; exit 1; }

# 6. mp kill removes the window and unregisters
mp kill "test:w1" >/dev/null
sleep 1
! tmux list-windows -t mc-test 2>/dev/null | grep -q "^[0-9]*: w1" || { echo "FAIL: window still present after kill"; exit 1; }
mp status | grep -qv "$HOST_ID/test:w1" || { echo "FAIL: mp status still lists killed agent"; exit 1; }

echo "VERIFY_OK"
```

## Failure modes

**`mp: command not found`** → `~/.local/bin` not on PATH. Run Step 10.

**`spawn FAILED: new-session failed`** → another tmux session called `mc-test` is owned by a different user or has weird permissions. Pick a different session name or `tmux kill-session -t mc-test`.

**`Send FAILED: session mc-test does not exist`** → agent was killed or never spawned. Re-run spawn.

**Marker never appears in pane within 30s** → claude inside the pane is mid-startup. Increase the verify wait, or check `mp peek` for the actual claude state (often it's still on the welcome banner — proves send works, claude just hasn't begun rendering the response).

**`procps` not installed → `ps -p` fails** → Steps include `apt-get install procps`. If you skipped it, install now.

## Cleanup

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"

# Kill all spawned agent sessions (anything matching mc-*)
for s in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^mc-'); do
  tmux kill-session -t "$s" 2>/dev/null || true
done

# Stop our daemons
for name in queue-client queue-server; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && kill "$(cat $pidfile)" 2>/dev/null || true
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true

# Drop runtime; preserve queue.env (so secret survives across re-runs)
rm -rf "$INSTALL_DIR/run" "$INSTALL_DIR/bin" "$INSTALL_DIR/plugins"
# To fully reset: rm -rf $HOME/.config/mypeople $INSTALL_DIR
```
