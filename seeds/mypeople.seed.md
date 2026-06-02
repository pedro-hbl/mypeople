# SEED: mypeople

> seed-format: 1

> **You're an AI agent reading this seed.** Your job: run `## Step 0 Interview` to gather inputs, then execute every Step in order, then run the `## Verify` block in a sub-shell. On exit code 0 print `SEED_RESULT=DONE` and stop. On any blocker print `BLOCKED_REASON=<short reason>` and stop. Do not ask the user what to do with this file — that's already specified below.

## Goal

Install the mypeople runtime on this host with claude already installed: a small HTTP queue (queue-server), a heartbeat/dispatch client (queue-client), a CLI (`mp`) for `spawn / send / peek / kill / status`, a per-spawn Claude Code hooks plugin so agents emit lifecycle events, a Boss role that internalizes a doctrine on spawn, a HUD + per-tab browser-attach (ttyd), and a Tailscale tailnet join so the HUD + ttyd are reachable from anywhere on the tailnet via a stable hostname.

After install: `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` (HUD) and `http://<TS_HOSTNAME>.<tailnet>.ts.net:7681/?arg=-t&arg=mc-main:Boss` (ttyd attach) Just Work from any tailnet node.

The seed describes **intent**; the agent reading it adapts to whatever OS / package manager / privilege model the host has. macOS, Debian, Ubuntu, RHEL — pick the right install incantation for each component named in `## Components`. If you're inside a sandboxed Linux container without TUN, that's a sandbox issue you resolve outside the seed (e.g. `--cap-add NET_ADMIN --device /dev/net/tun`).

## Done

Each independently verifiable from a fresh shell.

**Runtime:**
- `curl http://127.0.0.1:9900/health` returns 200 with `{"status": "ok"}`.
- `queue-server` and `queue-client` processes both alive in `ps`.
- `ttyd` running with `tmux attach` so per-tab attach URLs work.
- tailscaled running, node online on the tailnet, HUD + ttyd reachable on the tailscale IP.

**Boss role:**
- `~/mypeople/boss-CLAUDE.md` is installed (the Boss's job description, inlined in this seed).
- `mp spawn <host>/main:Boss --master --backend claude` creates the Boss tab AND sends an onboarding prompt that has the agent read `boss-CLAUDE.md`.
- After the Boss's onboarding turn, `~/mypeople/status/mc-main/Boss.json` exists with `status: "idle"` and a `summary` that mentions ≥2 doctrine keywords (`plan`, `approve`, `queue`, `mp`, `fire-and-forget`, `autonomous`).

**Agent loop:**
- `mp spawn <host>/main:worker-1 --backend claude --boss <host>/main:Boss` creates a worker tab whose env has `BOSS_ID=<host>/main:Boss`.
- `mp send <host>/main:worker-1 "msg"` types the message into the worker's pane via bracketed-paste, intact.
- When the worker's Stop hook fires: status JSON written, `[AGENT NOTIFICATION]` line typed into the Boss's pane via the queue.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `QUEUE_PORT` | no | `9900` | port free or our own server | "TCP port (default 9900)" |
| `QUEUE_SECRET` | no | (auto) | existing key in `queue.env` | "Reuse or auto-gen" |
| `INSTALL_DIR` | no | `$HOME/mypeople` | dir exists | default |
| `HOST_ID` | no | `$(hostname -s)` | `hostname -s` works | default |
| OS deps (`tmux python3 jq procps`) | yes | apt | `command -v` each | (no prompt — agent runs apt install non-interactively) |
| claude CLI | yes | present | `command -v claude` | `BLOCKED_REASON=claude_not_installed` |
| `TS_AUTHKEY` | **yes** | none | `[ -n "$TS_AUTHKEY" ]` (env or queue.env) | "Tailscale auth key — generate at https://login.tailscale.com/admin/settings/keys (reusable, ephemeral OFF, tag is fine). The seed cannot proceed without one." |
| `TS_HOSTNAME` | no | `mypeople-$(hostname -s)` | always available | "Stable hostname to announce on the tailnet. Default: `mypeople-<short hostname>`. Reachable as `<hostname>.<tailnet>.ts.net`." |
| TUN device (Linux only) | conditional | host-provided | `[ -c /dev/net/tun ]` on Linux | If missing on Linux: `BLOCKED_REASON=no_tun_device` — Tailscale needs a kernel TUN device. Sandboxed containers must be started with `--device /dev/net/tun --cap-add NET_ADMIN`. On macOS Tailscale uses the system extension instead; this input is N/A. |

## Components

| Component | Source | Notes |
|---|---|---|
| `queue-server.py` | inline | HTTP queue: clients, agents, task submit/poll/result, dashboard |
| `queue-client.py` | inline | heartbeat + task dispatcher; tmux input via bracketed-paste |
| `mp` CLI | inline | `spawn / send / peek / kill / status` |
| `plugins/tmux-boss-hooks/` | inline | Claude Code hooks plugin: SessionStart / Stop / SessionEnd → status file + boss notification |
| `boss-CLAUDE.md` | inline | doctrine read by every Boss at spawn |
| `dashboard.html` | inline | HUD page, served from queue-server, polls /agents + /clients |
| OS pkgs | apt: `tmux python3 jq procps ttyd tailscale` (with ttyd binary fallback) | |

## Steps

### 0. Interview (mandatory)

Detect all inputs. Send ONE consolidated Interview message. Wait for CEO reply. Then run autonomously.

### 1. Install OS deps

**Intent**: ensure `tmux`, `python3` (>= 3.8, stdlib only — no pip deps), `jq`, `ps` (procps on Linux; built-in on macOS), `curl`, `tailscale`, and `ttyd` are all on `PATH`. Use whatever package manager the host has.

Detect what's missing with `command -v <name>`; install only what's absent. Suggested commands per platform — the agent picks the right one for THIS host:

- **macOS** (Homebrew): `brew install tmux jq ttyd`. `python3` ships with the OS or via Xcode CLT; `ps` is built-in.
  - **Tailscale CLI on macOS — IMPORTANT**: if Tailscale.app is already installed (Mac App Store / direct download), the `tailscale` CLI is bundled inside the app but NOT on `PATH` by default. Don't reinstall via `brew install tailscale` — that creates a competing install path. Instead:
    1. Open Tailscale.app → settings/preferences → enable "Install CLI" (or equivalent menu item). This creates a symlink at `/usr/local/bin/tailscale` pointing to the app's bundled binary. The user must click this manually on first install of mypeople — surface it in the Interview if `command -v tailscale` returns nothing and `/Applications/Tailscale.app` exists.
    2. If Tailscale.app is NOT installed at all: `brew install --cask tailscale` (preferred — keeps a single source of truth) or `brew install tailscale` for CLI-only.
  - After whichever path: verify `command -v tailscale` resolves. Do NOT proceed with two install paths fighting each other.
- **Debian / Ubuntu**: `sudo apt-get update && sudo apt-get install -y tmux python3 jq procps curl ttyd tailscale`. If `ttyd` isn't in this distro's repos, download the prebuilt binary from `https://github.com/tsl0922/ttyd/releases/latest` (architectures: `ttyd.x86_64`, `ttyd.aarch64`) and place it on `PATH`. Tailscale install per `https://tailscale.com/download/linux/` (sets up its own apt repo).
- **RHEL/Fedora**: `sudo dnf install tmux jq procps-ng ttyd tailscale` (Tailscale repo per `https://tailscale.com/download/`).
- **Other**: install each by name from the host's native package manager.

Stop with `BLOCKED_REASON=<tool>_install_failed` if any of `tmux jq ttyd tailscale` is unreachable after install.

On **Linux only**, also verify `[ -c /dev/net/tun ]`. If missing, you're in a sandboxed container without the right permissions — stop with `BLOCKED_REASON=no_tun_device` (caller fixes by re-creating the container with `--device /dev/net/tun --cap-add NET_ADMIN`). On macOS the TUN check is N/A.

### 2. Stop any prior mypeople daemons (idempotent reinstall)

**Intent**: previous installs may have running queue-server, queue-client, ttyd, and (Linux-no-systemd only) a user-launched `tailscaled`. Kill them so this Step's re-write of code and config is clean.

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
for name in queue-client queue-server ttyd tailscaled; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && { sudo kill "$(cat $pidfile)" 2>/dev/null || kill "$(cat $pidfile)" 2>/dev/null || true; }
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true
pkill -f "ttyd -W -p" 2>/dev/null || true
# DO NOT kill a system-managed tailscaled (macOS Tailscale.app, Linux systemd).
# Only kill a userland tailscaled this install previously started.
[ -f "$INSTALL_DIR/run/tailscaled.pid" ] && sudo kill "$(cat $INSTALL_DIR/run/tailscaled.pid)" 2>/dev/null || true
```

### 3. Create directory layout

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$INSTALL_DIR/status" "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin" "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks"
mkdir -p "$HOME/.config/mypeople" "$HOME/.local/bin"
```

### 3.5. Pre-accept the trust dialog in `~/.claude.json` for spawn directories

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

### 3.6. Install the Boss doctrine (`boss-CLAUDE.md`)

**Why**: `mp spawn --master` will send an onboarding prompt that tells the new agent to read this file. Without the doctrine on disk, a spawned "Boss" is a vanilla claude with no idea it's a Boss.

```bash
cat > "$INSTALL_DIR/boss-CLAUDE.md" <<'EOF'
# Boss CLAUDE.md — doctrine

This is your job description. You are the Boss for this mypeople deployment.

## Rule 1 — Plan gate (no engineering without a plan)

You do not start engineering work, and you do not let your team start, until ALL four conditions are met:

1. Brainstorm complete (CEO + you explored the problem).
2. PLAN written (markdown doc: user journey, scope, smallest meaningful slice, non-goals, agents involved).
3. E2E Verify drafted (a runnable shell script proving the feature from the pane).
4. CEO explicitly approves ("approved" / "go" / "ship it"). Silence is not approval.

If anyone asks to start coding before these four are met: "Stop. We don't have a plan yet." Walk them through which is missing.

## Rule 2 — Autonomous loop (keep the team working)

Triggers you must respond to:
- `[AGENT NOTIFICATION] ...` arrives → read result, update PLAN, assign next task.
- All agents idle + work in PLAN → dispatch next task.
- All idle + no work → send CEO one short message: "Team idle. Next: <propose>?"
- Task failed → mp peek, then reassign or escalate.

Pacing: act on notifications within 30s. No "exploring" without a deliverable.

## Rule 3 — Fire-and-forget through the system (never bypass)

Every action on another agent goes through the `mp` CLI / queue. NEVER `tmux send-keys` or `tmux capture-pane` directly. Not even to read.

Available verbs:
- `mp spawn <host>/<session>:<tab> --backend claude [--boss <agent_id>]` — create an agent. Pass `--boss $AGENT_ID` so worker Stop notifications route back to you.
- `mp send <agent_id> "msg"` — queue a message.
- `mp peek <agent_id>` — queued peek; response returns via the queue.
- `mp status` — list agents.
- `mp kill <agent_id>` — graceful exit.

Fire-and-forget: every verb returns immediately. You wait for notifications; you don't poll. If you reach for raw tmux, stop — find the mp verb or flag a missing feature.

## Your environment

- `$AGENT_ID` — your own address; use it as `--boss $AGENT_ID` when spawning workers.
- `$BOSS_ID` — your boss's address (empty if you ARE the top-level Boss).
- The mypeople runtime lives at `$INSTALL_DIR`.
EOF
chmod 644 "$INSTALL_DIR/boss-CLAUDE.md"
```

### 3.7. Install TPM + Dracula tmux config (CEO's preferred look)

**Why**: tmux defaults are bad (no mouse, no status bar, 0-indexed windows). When the human attaches via ttyd in the HUD, this is what they see. Install Tmux Plugin Manager + Dracula theme so the UX is usable out of the box.

```bash
# Clone TPM if missing
[ -d "$HOME/.tmux/plugins/tpm" ] || git clone --depth 1 https://github.com/tmux-plugins/tpm "$HOME/.tmux/plugins/tpm"

# Write tmux config (matches host's Dracula setup)
cat > "$HOME/.tmux.conf" <<'EOF'
# ── Dracula Theme ──────────────────────────────────────────
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'dracula/tmux'

set -g @dracula-plugins "cpu-usage ram-usage time"
set -g @dracula-show-powerline false
set -g @dracula-show-left-icon session
set -g @dracula-military-time true
set -g @dracula-day-month false
set -g @dracula-cpu-usage-label "CPU"
set -g @dracula-ram-usage-label "RAM"
set -g @dracula-show-timezone false

# ── General ───────────────────────────────────────────────
set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",xterm-256color:Tc"
set -g mouse on
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g history-limit 50000
set -sg escape-time 10

# ── Mouse selection ───────────────────────────────────────
# Default MouseDown1Pane (begin-selection) is what we want — do NOT rebind
# it to cancel/exit-copy-mode or click-drag will snap the view away.
# unbind here to clear any prior server state.
unbind-key -T copy-mode    MouseDown1Pane
unbind-key -T copy-mode-vi MouseDown1Pane
# copy-pipe-and-cancel (NOT copy-pipe) — without -and-cancel the pane stays
# in copy-mode after every mouse-drag selection and silently swallows the
# user's next keystrokes until they press Escape. On macOS pbcopy lands the
# selection on the host clipboard; on Linux the pipe silently no-ops
# (acceptable — ttyd's own browser selection handles host clipboard).
bind-key   -T copy-mode    MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"
bind-key   -T copy-mode-vi MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "pbcopy"

# ── Mouse-wheel scroll ────────────────────────────────────
# Claude TUI renders on the MAIN screen (alternate_on=0) and does not
# request mouse mode, so tmux's default WheelUpPane binding falls through
# to `copy-mode -e` and silently traps every subsequent keystroke until
# Escape. Kill the wheel→copy-mode path entirely. Users who want scrollback
# can still enter copy-mode explicitly via `prefix [`.
unbind-key -T root WheelUpPane
unbind-key -T root WheelDownPane

# ── TPM (must be last) ────────────────────────────────────
run '~/.tmux/plugins/tpm/tpm'
EOF
chmod 644 "$HOME/.tmux.conf"

# Clone the one plugin TPM would install on first prefix-I anyway.
# TPM's install_plugins.sh requires an already-running tmux server with
# the conf loaded — chicken-and-egg at install time. Direct clone bypasses
# that and makes first attach instant instead of "wait for clone".
# Convention: a TPM plugin `<owner>/<repo>` clones to ~/.tmux/plugins/<repo>.
[ -d "$HOME/.tmux/plugins/tmux" ] || git clone --depth 1 https://github.com/dracula/tmux "$HOME/.tmux/plugins/tmux"

# If a tmux server is already running from a prior install, re-source the
# conf so the new look takes effect immediately.
tmux source-file "$HOME/.tmux.conf" 2>/dev/null || true
```

### 4. Write `queue-server.py`

```bash
cat > "$INSTALL_DIR/bin/queue-server.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-server."""

import http.server, json, os, sys, threading, time, uuid
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET = os.environ.get("QUEUE_SECRET", "")
START_TS = time.time()

_lock = threading.Lock()
clients = {}
agents = {}
tasks = {}


def _host_of(agent_id):
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
        # /dashboard is PUBLIC (no secret check) — secret is injected into HTML
        # for the in-page fetch calls. Browser users don't have the secret.
        if p == "/dashboard":
            install_dir = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
            html_path = os.path.join(install_dir, "bin", "dashboard.html")
            try:
                with open(html_path) as f:
                    html = f.read().replace("__INJECT_SECRET__", SECRET)
            except FileNotFoundError:
                html = "<h1>dashboard.html not found</h1>"
            data = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not self._ok_secret():
            return self._json(401, {"error": "unauthorized"})
        if p == "/clients":
            with _lock:
                return self._json(200, [{"hostname": h, **v} for h, v in clients.items()])
        if p == "/agents":
            install_dir = os.environ.get("INSTALL_DIR", os.path.expanduser("~/mypeople"))
            with _lock:
                items = []
                for k, v in agents.items():
                    item = {"agent_id": k, **v}
                    # `session` in the registry is the BARE session name (e.g.
                    # "main"); the tmux session name and status-dir name both
                    # use the "mc-" prefix consistently. Build the mc-prefixed
                    # form once and use it everywhere.
                    bare_sess = v.get("session", "")
                    mc_sess = bare_sess if bare_sess.startswith("mc-") else f"mc-{bare_sess}"
                    tab = v.get("tab", "")
                    status_path = os.path.join(install_dir, "status", mc_sess, f"{tab}.json")
                    try:
                        import json as _json
                        with open(status_path) as f:
                            sf = _json.load(f)
                        item["summary"] = sf.get("summary", "")
                        item["last_stop_ts"] = sf.get("timestamp", "")
                    except (FileNotFoundError, ValueError):
                        item["summary"] = ""
                    item["tmux_target"] = f"{mc_sess}:{tab}"
                    items.append(item)
                return self._json(200, items)
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
            return self._json(200, {})
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
                entry = {"ts": time.time()}
                attach_base = (data.get("attach_base") or "").strip()
                if attach_base:
                    entry["attach_base"] = attach_base
                clients[host] = entry
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
                    "boss_id": data.get("boss_id", ""),
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
                return self._json(400, {"error": "target_host or target_agent required"})
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
    # Bind to all interfaces (not just loopback) so the HUD page is
    # reachable from outside this host (e.g. another tailnet node) via
    # the tailscale IP after Step 8.5.
    server = ThreadingServer(("0.0.0.0", PORT), Handler)
    print(f"queue-server listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-server.py"
```

### 5. Write `queue-client.py`

```bash
cat > "$INSTALL_DIR/bin/queue-client.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-client."""

import json, os, shlex, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

QUEUE_URL = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900")
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
POLL_INTERVAL = float(os.environ.get("QUEUE_POLL_INTERVAL", "1.0"))
HOSTNAME = os.environ.get("HOST_ID", "") or socket.gethostname()
TTYD_PUBLIC_URL = os.environ.get("TTYD_PUBLIC_URL", "")  # browser-reachable ttyd base for this host (e.g. its Tailscale addr); empty -> HUD falls back to localhost
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
            post_json("/heartbeat", {"hostname": HOSTNAME, "attach_base": TTYD_PUBLIC_URL})
        except urllib.error.URLError as e:
            print(f"{time.strftime('%H:%M:%S')} heartbeat FAIL: {e}", file=sys.stderr, flush=True)
        time.sleep(HEARTBEAT)


def tmux_run(*args, timeout=5):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)


def tmux_send_text(target, text):
    """Bracketed-paste safe send + Enter, with symmetric pane-state defense.

    Single biggest historical source of unreliability: typing into a pane
    that's in tmux's copy-mode (user scrolled with the mouse, selected text,
    or otherwise entered a view-mode). In that state, send-keys types INTO
    copy-mode commands instead of the TUI's input buffer — silent failure
    that's invisible to the sender.

    Defense (tmux-primitive only, no TUI-specific assumptions): if
    `pane_in_mode == 1`, send `-X cancel` to return the pane to its primary
    buffer. Apply the check BOTH before typing (so the paste lands) AND
    after Enter (so the pane is left clean for any human who picks it up
    next — `pane_in_mode == 0` is an invariant of this function's return).
    """
    # Exit copy-mode / view-mode if active.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)

    # Bracketed-paste send.
    safe = text.replace(PASTE_END, "").replace(PASTE_START, "")
    payload = f"{PASTE_START}{safe}{PASTE_END}"
    r = tmux_run("send-keys", "-t", target, "-l", "--", payload)
    if r.returncode != 0:
        return False, r.stderr.strip()
    time.sleep(0.1)
    r = tmux_run("send-keys", "-t", target, "Enter")
    if r.returncode != 0:
        return False, r.stderr.strip()

    # Post-injection mirror: ensure pane is left in text-editing mode.
    time.sleep(0.15)
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
    return True, ""


def parse_agent_id(aid):
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
    # Reject non-existent cwd upfront — otherwise `cd ...` fails inside the
    # shell command, `exec claude` runs in the wrong directory, and the
    # caller sees a confusing partial-failure with no clean error. This is
    # the kind of silent fallthrough we never want.
    if not os.path.isdir(cwd):
        return False, f"cwd does not exist on this host: {cwd!r}"
    boss_id = payload.get("boss_id", "")
    is_master = bool(payload.get("is_master", False))
    mc_sess = f"mc-{sess}"

    has_sess = tmux_run("has-session", "-t", mc_sess).returncode == 0
    if not has_sess:
        r = tmux_run("new-session", "-d", "-s", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-session failed: {r.stderr.strip()}"
    else:
        wins = tmux_run("list-windows", "-t", mc_sess, "-F", "#{window_name}").stdout.splitlines()
        if tab in wins:
            # Idempotent re-spawn: window already exists, re-register and
            # return success. Callers (e.g. a Boss orchestrating workers) may
            # legitimately spawn the same id twice if a worker disconnected
            # but its tmux window survived.
            try:
                post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
            except urllib.error.URLError as e:
                return False, f"re-register failed: {e}"
            return True, {"agent_id": aid, "tmux_target": f"{mc_sess}:{tab}", "boss_id": boss_id, "is_master": is_master, "reused_existing": True}
        r = tmux_run("new-window", "-t", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-window failed: {r.stderr.strip()}"

    if backend == "claude":
        spawn_cmd = (
            f"claude --dangerously-skip-permissions "
            f"--settings {shlex.quote(json.dumps({'skipDangerousModePermissionPrompt': True}))} "
            f"--plugin-dir {shlex.quote(PLUGIN_DIR)}"
        )
    else:
        return False, f"backend {backend!r} not supported"

    env_parts = [
        f"export AGENT_NAME={shlex.quote(tab)}",
        f"export AGENT_SESSION={shlex.quote(mc_sess)}",
        f"export AGENT_ID={shlex.quote(aid)}",
        f"export QUEUE_URL={shlex.quote(QUEUE_URL)}",
        f"export QUEUE_SECRET={shlex.quote(SECRET)}",
        f"export HOST_ID={shlex.quote(HOSTNAME)}",
        f"export INSTALL_DIR={shlex.quote(INSTALL_DIR)}",
    ]
    if boss_id:
        env_parts.append(f"export BOSS_ID={shlex.quote(boss_id)}")
    shell_cmd = f"cd {shlex.quote(cwd)} && {' && '.join(env_parts)} && exec {spawn_cmd}"

    target = f"{mc_sess}:{tab}"
    ok, err = tmux_send_text(target, shell_cmd)
    if not ok:
        return False, f"shell-cmd send failed: {err}"

    if backend == "claude":
        deadline = time.time() + 30
        while time.time() < deadline:
            r = tmux_run("capture-pane", "-t", target, "-p")
            if "bypass permissions on" in (r.stdout or ""):
                break
            time.sleep(0.5)
        else:
            return False, "claude TUI didn't show 'bypass permissions on' banner within 30s"

    # If --master, bootstrap the Boss with its doctrine: send an onboarding
    # prompt that instructs the agent to read ~/mypeople/boss-CLAUDE.md and
    # ack with a one-line summary. The spawn returns once the prompt is sent;
    # the agent's first Stop event will fire when it finishes reading + acking,
    # at which point its status.json will reflect the doctrine.
    if is_master and backend == "claude":
        time.sleep(0.5)  # let the banner settle
        doctrine = os.path.join(INSTALL_DIR, "boss-CLAUDE.md")
        onboarding = (
            f"You are the Boss for this mypeople deployment. Your AGENT_ID is {aid}. "
            f"Read {doctrine} now — it is your full job description (plan-gate, autonomous loop, fire-and-forget). "
            f"Then reply in ONE line summarizing your role and the mp verbs you have available. "
            f"After that, await CEO instructions."
        )
        ok, err = tmux_send_text(target, onboarding)
        if not ok:
            return False, f"onboarding send failed: {err}"

    try:
        post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
    except urllib.error.URLError as e:
        return False, f"register failed: {e}"

    return True, {"agent_id": aid, "tmux_target": target, "boss_id": boss_id, "is_master": is_master}


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
        try:
            post_json("/agents/unregister", {"agent_id": aid})
        except urllib.error.URLError:
            pass
        return True, {"already_gone": True}
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


HANDLERS = {"spawn": execute_spawn, "send": execute_send, "peek": execute_peek, "kill": execute_kill}


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
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-client.py"
```

### 6. Write the `mp` CLI

```bash
cat > "$INSTALL_DIR/bin/mp" <<'PY_EOF'
#!/usr/bin/env python3
"""mp — mypeople CLI. Verbs: status, spawn, send, peek, kill."""

import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "queue.env"
DEFAULT_TIMEOUT = 60
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
        if t.get("status") in ("done", "failed"):
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
            boss = a.get("boss_id", "")
            boss_part = f" boss={boss}" if boss else ""
            print(f"  {a['agent_id']} [{a.get('state','?')}] backend={a.get('backend','?')}{boss_part}")
    print(f"\n{len(clients)} client(s) heartbeating:")
    now = time.time()
    for c in clients:
        age = int(now - c["ts"])
        print(f"  {c['hostname']} (last seen {age}s ago)")


def cmd_spawn(cfg, args):
    if len(args) < 1:
        print("Usage: mp spawn <agent_id> [--backend claude] [--cwd PATH] [--boss <agent_id>] [--master]", file=sys.stderr)
        sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    backend = "claude"
    cwd = os.path.expanduser("~")
    boss_id = ""
    is_master = False
    i = 1
    while i < len(args):
        if args[i] == "--backend" and i + 1 < len(args):
            backend = args[i + 1]; i += 2
        elif args[i] == "--cwd" and i + 1 < len(args):
            cwd = args[i + 1]; i += 2
        elif args[i] == "--boss" and i + 1 < len(args):
            boss_id = canonicalize_agent_id(args[i + 1], cfg["HOST_ID"]); i += 2
        elif args[i] == "--master":
            is_master = True; i += 1
        else:
            print(f"unknown arg: {args[i]}", file=sys.stderr); sys.exit(2)
    target_host = aid.split("/", 1)[0]
    body = {"action": "spawn", "target_host": target_host,
            "payload": {"agent_id": aid, "backend": backend, "cwd": cwd, "boss_id": boss_id, "is_master": is_master}}
    t = submit_and_wait(cfg, body, timeout=60)
    if t["status"] == "done":
        r = t.get("result") or {}
        boss_part = f" boss={r.get('boss_id','')}" if r.get("boss_id") else ""
        master_part = " [MASTER — onboarding sent]" if r.get("is_master") else ""
        print(f"Spawned {r.get('agent_id', aid)}  [tmux={r.get('tmux_target','?')}]{boss_part}{master_part}")
    else:
        print(f"Spawn FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


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

### 7. Write the `tmux-boss-hooks` plugin

```bash
cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "tmux-boss-hooks",
  "description": "Per-spawn lifecycle hooks for mypeople-managed agents.",
  "version": "1.1.0"
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/hooks.json" <<EOF
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 5}]}],
    "Stop":         [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 10}]}],
    "SessionEnd":   [{"hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 5}]}]
  }
}
EOF

cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event" <<'EOF'
#!/bin/bash
# Lifecycle hook for mypeople-managed Claude agents.
#
# Triggered by Claude Code on SessionStart / Stop / SessionEnd.
# Reads the hook payload JSON from stdin. For Stop: writes a status file
# under $INSTALL_DIR/status/<session>/<agent>.json AND submits an
# "[AGENT NOTIFICATION]" send task targeting $BOSS_ID (if set).
#
# Gating: requires AGENT_ID env var. Unmanaged claude invocations are no-ops.

set -e
[ -z "${AGENT_ID:-}" ] && exit 0   # not managed by mypeople

INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/run"
LOG="$INSTALL_DIR/run/hook-events.log"

INPUT=""
IFS= read -t 5 -d '' -r INPUT || true
[ -z "$INPUT" ] && exit 0

EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // "?"' 2>/dev/null || echo "?")
SID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null || echo "")
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // ""' 2>/dev/null || echo "")
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Append to local log
echo "{\"ts\":\"$TS\",\"event\":\"$EVENT\",\"agent_id\":\"$AGENT_ID\",\"session_id\":\"$SID\"}" >> "$LOG"

if [ "$EVENT" != "Stop" ]; then
  # SessionStart / SessionEnd: just log, no notification.
  exit 0
fi

# --- Stop event handling ---

# Truncate summary to 1000 chars, single-line. 200 was too tight — Boss
# onboarding summaries got cut off mid-word at "autonomo", barely failing
# the doctrine-keyword check in Verify.
SUMMARY=$(echo "$LAST_MSG" | tr '\n' ' ' | cut -c1-1000)

# Parse session+tab from AGENT_ID = host/session:tab
HOST_PART="${AGENT_ID%%/*}"
REST="${AGENT_ID#*/}"
SESS_PART="${REST%%:*}"
TAB_PART="${REST#*:}"

# Write status file
STATUS_DIR="$INSTALL_DIR/status/mc-$SESS_PART"
mkdir -p "$STATUS_DIR"
jq -n \
  --arg agent "$TAB_PART" \
  --arg session "mc-$SESS_PART" \
  --arg ts "$TS" \
  --arg session_id "$SID" \
  --arg summary "$SUMMARY" \
  --arg agent_id "$AGENT_ID" \
  --arg boss_id "${BOSS_ID:-}" \
  '{agent: $agent, session: $session, status: "idle", timestamp: $ts, session_id: $session_id, summary: $summary, agent_id: $agent_id, boss_id: $boss_id}' \
  > "$STATUS_DIR/$TAB_PART.json"

# If no boss, we're done (status file is enough)
[ -z "${BOSS_ID:-}" ] && exit 0

# POST a send task to deliver the notification to the boss's pane
NOTIF="[AGENT NOTIFICATION] $AGENT_ID finished: $SUMMARY"
BOSS_HOST="${BOSS_ID%%/*}"
PAYLOAD=$(jq -n \
  --arg target_agent "$BOSS_ID" \
  --arg target_host "$BOSS_HOST" \
  --arg msg "$NOTIF" \
  '{action: "send", target_agent: $target_agent, target_host: $target_host, payload: {message: $msg}}')

curl -fsS -X POST "$QUEUE_URL/task/submit" \
  -H "Content-Type: application/json" \
  -H "X-Queue-Secret: $QUEUE_SECRET" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event"
```

### 7.5. Write the HUD dashboard HTML

**Why**: queue-server's `/dashboard` route serves this file with `__INJECT_SECRET__` replaced by the live `QUEUE_SECRET`. The page then polls `/agents` + `/clients` every 3s and renders rows. Each row has a "attach" link to ttyd with the correct `mc-<sess>:<tab>` target.

```bash
cat > "$INSTALL_DIR/bin/dashboard.html" <<'HTML_EOF'
<!doctype html>
<html><head><meta charset="utf-8"><title>mypeople — HUD</title>
<style>
  body { font: 14px -apple-system,system-ui; margin: 24px; background: #f4f4f4; color: #111; }
  h1 { margin: 0 0 12px; font-size: 20px; }
  .meta { color: #666; font-size: 12px; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }
  th, td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
  th { background: #f6f6f6; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #666; }
  tr:last-child td { border-bottom: 0; }
  .alive { color: #1e6e2c; font-weight: 600; }
  .dead, .gone { color: #a52a2a; font-weight: 600; }
  code { background: #f1f1f1; padding: 1px 5px; border-radius: 3px; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  a { color: #1f6feb; text-decoration: none; font-weight: 600; }
  .summary { color: #444; }
</style></head>
<body>
<h1>mypeople — HUD</h1>
<div class="meta">Refreshed: <span id="ts">never</span> · <span id="clients">? clients</span></div>
<table>
  <thead><tr><th>agent_id</th><th>state</th><th>backend</th><th>boss</th><th>summary</th><th>attach</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
const SECRET = "__INJECT_SECRET__";
async function getJson(path) {
  const r = await fetch(path, { headers: { 'X-Queue-Secret': SECRET } });
  return r.json();
}
async function refresh() {
  try {
    const [a, c] = await Promise.all([getJson('/agents'), getJson('/clients')]);
    const clientMap = {};
    (c || []).forEach(cl => { clientMap[cl.hostname] = cl; });
    const localBase = `http://${location.hostname || '127.0.0.1'}:7681`;
    const rows = a.map(x => {
      const target = x.tmux_target || '';
      // per-host attach: a cross-host/container node uses the ttyd base it
      // advertises (its Tailscale addr); same-host falls back to localhost.
      const cl = clientMap[x.host];
      const base = (cl && cl.attach_base) ? cl.attach_base : localBase;
      const url = `${base}/?arg=-t&arg=${encodeURIComponent(target)}`;
      const safeSummary = (x.summary || '').replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])).slice(0, 120);
      return `<tr>
        <td><code>${x.agent_id}</code></td>
        <td class="${x.state}">${x.state||''}</td>
        <td>${x.backend||''}</td>
        <td><code>${x.boss_id||''}</code></td>
        <td class="summary">${safeSummary}</td>
        <td><a href="${url}" target="_blank">attach</a></td>
      </tr>`;
    }).join('');
    document.getElementById('rows').innerHTML = rows || '<tr><td colspan=6 style="color:#888">No active agents.</td></tr>';
    document.getElementById('clients').textContent = c.length + ' client' + (c.length === 1 ? '' : 's') + ' heartbeating';
    document.getElementById('ts').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('ts').textContent = 'ERROR: ' + e.message;
  }
}
refresh();
setInterval(refresh, 3000);
</script>
</body></html>
HTML_EOF
chmod 644 "$INSTALL_DIR/bin/dashboard.html"
```

### 8. Write `queue.env`

```bash
if [ -s "$HOME/.config/mypeople/queue.env" ] && grep -q '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"; then
  SECRET=$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | head -1 | cut -d= -f2-)
else
  SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fi
QUEUE_PORT="${QUEUE_PORT:-9900}"
HOST_ID="${HOST_ID:-$(hostname -s)}"
TS_HOSTNAME="${TS_HOSTNAME:-mypeople-$(hostname -s)}"
cat > "$HOME/.config/mypeople/queue.env" <<EOF
QUEUE_URL=http://127.0.0.1:${QUEUE_PORT}
QUEUE_SECRET=${SECRET}
QUEUE_PORT=${QUEUE_PORT}
QUEUE_HEARTBEAT=30
QUEUE_POLL_INTERVAL=1.0
HOST_ID=${HOST_ID}
INSTALL_DIR=${INSTALL_DIR:-$HOME/mypeople}
TTYD_PORT=${TTYD_PORT:-7681}
TS_HOSTNAME=${TS_HOSTNAME}
# UTF-8 locale is REQUIRED. Hosts that default to POSIX (many Linux
# containers, some bare-metal Linux installs) cause tmux to collapse
# multi-byte UTF-8 chars (every glyph claude TUI uses — ●, ⏺, ✻, ⏵, ⎿,
# ❯, box-drawing — gets stripped to ASCII `_` in tmux's internal buffer
# and that's what reaches the browser via ttyd). macOS defaults to
# UTF-8 already; setting these explicitly is harmless and makes the
# behavior portable.
LANG=C.UTF-8
LC_ALL=C.UTF-8
EOF
chmod 600 "$HOME/.config/mypeople/queue.env"
```

### 8.5. Bring this host onto the tailnet

**Intent**: this host gets its own tailnet identity (`$TS_HOSTNAME`) and a tailscale IP. After this Step, `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` will be reachable from any other tailnet node.

The mechanism varies by host:

- **macOS**: Tailscale runs as a system app (or the standalone CLI from `brew install tailscale`). If the GUI app is installed and the user is already signed in, this Step is a no-op. Otherwise, `sudo tailscale up --authkey=$TS_AUTHKEY --hostname=$TS_HOSTNAME --ssh=false --accept-routes=false`. No daemon to start manually — the app/service handles it.

- **Linux (systemd host)**: `tailscaled` is already managed by systemd after install. Just `sudo tailscale up --authkey=$TS_AUTHKEY --hostname=$TS_HOSTNAME --ssh=false --accept-routes=false`.

- **Linux (no systemd, e.g. sandboxed container)**: start `tailscaled` manually as a userland daemon with state files under `$INSTALL_DIR/run/tailscale-state/` (it needs `/dev/net/tun` + `NET_ADMIN` — see Step 1 prereq). Then `tailscale up` with the same flags, pointing at the custom socket via `--socket=<path>`. Sample (Linux-no-systemd):
  ```bash
  TS_STATE_DIR="$INSTALL_DIR/run/tailscale-state"
  sudo mkdir -p "$TS_STATE_DIR"
  sudo nohup tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --socket="$TS_STATE_DIR/tailscaled.sock" \
    > "$INSTALL_DIR/run/tailscaled.log" 2>&1 &
  echo $! | sudo tee "$INSTALL_DIR/run/tailscaled.pid" >/dev/null
  # wait up to 15s for socket, then:
  sudo tailscale --socket="$TS_STATE_DIR/tailscaled.sock" up \
    --authkey="$TS_AUTHKEY" --hostname="$TS_HOSTNAME" \
    --ssh=false --accept-routes=false
  ```

`$TS_AUTHKEY` is required. If unset, stop with `BLOCKED_REASON=ts_authkey_not_set`.

**Verify by intent**: `tailscale status --json` reports `.Self.Online == true` and `.Self.HostName == $TS_HOSTNAME`; `tailscale ip -4` returns a `100.x.x.x` address. Stop with `BLOCKED_REASON=tailscale_no_ipv4_assigned` if not.

### 9. Start daemons

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

# ttyd: per-tab browser-attach.
#   -W = writable so the browser user can type.
#   -a = allow client to pass command args via URL (?arg=foo&arg=bar).
#        Without -a the HUD's attach links — http://host:7681/?arg=-t&arg=mc-X:Y
#        — are silently ignored and the user lands in a default tmux session
#        (sometimes even a bogus session named `-t`). MANDATORY for per-tab attach.
#   -t fontFamily/fontSize = xterm.js options (default xterm.js font lacks
#        glyphs claude uses: ❯ ● ✻ etc.). Menlo/Monaco standard on macOS; on
#        Linux the browser falls back to its first available monospace match.
#   -t disableLeaveAlert=true = kill the browser's "are you sure you want to
#        close this page?" prompt on tab close. ttyd registers a beforeunload
#        handler by default; this client option makes it removeEventListener
#        the handler on connect. Safe: the underlying tmux session persists
#        across detach — closing the tab only drops this ttyd client, no work
#        is lost.
TTYD_PORT="${TTYD_PORT:-7681}"
nohup ttyd -W -a -p "$TTYD_PORT" \
  -t 'fontFamily=Menlo, Monaco, "Cascadia Mono", "Fira Code", "Courier New", monospace' \
  -t 'fontSize=13' \
  -t 'disableLeaveAlert=true' \
  tmux attach > "$INSTALL_DIR/run/ttyd.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/ttyd.pid"
for i in $(seq 1 25); do
  curl -fsS -o /dev/null "http://127.0.0.1:${TTYD_PORT}/" && break
  sleep 0.2
done
```

### 10. PATH fix

```bash
if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"
```

### 11. Sanity

```bash
sleep 1
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

# --- core runtime invariants ---
curl -fsS http://127.0.0.1:9900/health | grep -q '"status": *"ok"' || { echo "FAIL: /health"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" -o command= 2>/dev/null | grep -q queue-server.py || { echo "FAIL: server pid"; exit 1; }
ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: client pid"; exit 1; }

# --- transport: status file + notification routing ---
BOSS_ID="$HOST_ID/main:Boss"
WORKER_ID="$HOST_ID/main:worker-1"

# Spawn the Boss with --master (triggers doctrine onboarding)
mp spawn "main:Boss" --master --backend claude --cwd "$HOME" >/tmp/v-boss.out 2>&1 || { echo "FAIL: boss spawn"; cat /tmp/v-boss.out; exit 1; }
grep -q "MASTER" /tmp/v-boss.out || { echo "FAIL: spawn didn't report MASTER (onboarding probably not sent)"; cat /tmp/v-boss.out; exit 1; }

# Wait up to 120s for Boss's onboarding turn to complete (Boss.json status file appears with non-empty summary)
BOSS_STATUS="$INSTALL_DIR/status/mc-main/Boss.json"
for i in $(seq 1 120); do
  if [ -f "$BOSS_STATUS" ] && jq -e '.summary | length > 20' "$BOSS_STATUS" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[ -f "$BOSS_STATUS" ] || { echo "FAIL: Boss never finished onboarding (no status file)"; exit 1; }

# --- role behavior: Boss internalized doctrine ---
# Boss's onboarding summary should mention at least 2 doctrine keywords.
BOSS_SUMMARY=$(jq -r .summary "$BOSS_STATUS" | tr '[:upper:]' '[:lower:]')
KEYWORD_HITS=0
for kw in plan approve queue mp fire-and-forget autonomous "stop hook" notification; do
  echo "$BOSS_SUMMARY" | grep -qF "$kw" && KEYWORD_HITS=$((KEYWORD_HITS + 1))
done
[ "$KEYWORD_HITS" -ge 2 ] || {
  echo "FAIL: Boss onboarding summary mentions $KEYWORD_HITS doctrine keywords (need ≥2)"
  echo "summary was: $BOSS_SUMMARY"
  exit 1
}

# Spawn the worker, addressing notifications back to Boss
mp spawn "main:worker-1" --backend claude --boss "main:Boss" --cwd "$HOME" >/tmp/v-w1.out 2>&1 || { echo "FAIL: worker spawn"; cat /tmp/v-w1.out; exit 1; }

# Tell the worker to finish a turn with a known summary
MARK="PONG-$RANDOM"
mp send "main:worker-1" "reply with exactly: $MARK" >/dev/null

# Wait up to 90s for the worker status file with our marker
STATUS_FILE="$INSTALL_DIR/status/mc-main/worker-1.json"
for i in $(seq 1 90); do
  if [ -f "$STATUS_FILE" ] && jq -e --arg m "$MARK" '.summary | contains($m)' "$STATUS_FILE" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[ -f "$STATUS_FILE" ] || { echo "FAIL: worker status file never written"; exit 1; }
jq -e --arg m "$MARK" '.summary | contains($m)' "$STATUS_FILE" >/dev/null 2>&1 || {
  echo "FAIL: worker summary missing $MARK"; cat "$STATUS_FILE"; exit 1
}
jq -e --arg b "$BOSS_ID" '.boss_id == $b' "$STATUS_FILE" >/dev/null || { echo "FAIL: worker boss_id mismatch"; exit 1; }

# Notification reached Boss's pane
for i in $(seq 1 30); do
  tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT NOTIFICATION\].*worker-1.*$MARK" && break
  sleep 1
done
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT NOTIFICATION\].*worker-1" || {
  echo "FAIL: boss pane never received [AGENT NOTIFICATION]"
  tmux capture-pane -t mc-main:Boss -p -S -300 | tail -25
  exit 1
}

# --- HUD + ttyd ---

# /dashboard reachable (PUBLIC; no secret needed)
curl -fsS http://127.0.0.1:9900/dashboard | grep -q "mypeople — HUD" || { echo "FAIL: /dashboard not serving expected HTML"; exit 1; }

# /dashboard injected the live secret (not the placeholder)
curl -fsS http://127.0.0.1:9900/dashboard | grep -q '__INJECT_SECRET__' && { echo "FAIL: /dashboard didn't inject secret"; exit 1; }

# /agents merged status-file summary into each agent record
mp spawn "main:Boss" --master --backend claude --cwd "$HOME" >/dev/null
for i in $(seq 1 60); do [ -s "$INSTALL_DIR/status/mc-main/Boss.json" ] && break; sleep 1; done
AGENTS_JSON=$(curl -fsS -H "X-Queue-Secret: $(grep ^QUEUE_SECRET= ~/.config/mypeople/queue.env | cut -d= -f2-)" http://127.0.0.1:9900/agents)
echo "$AGENTS_JSON" | jq -e --arg a "$HOST_ID/main:Boss" '.[] | select(.agent_id == $a) | .summary | length > 10' >/dev/null || {
  echo "FAIL: /agents didn't merge Boss summary"; echo "$AGENTS_JSON"; exit 1
}
echo "$AGENTS_JSON" | jq -e '.[] | .tmux_target' >/dev/null || { echo "FAIL: /agents missing tmux_target"; exit 1; }

# ttyd alive on its port
TTYD_PORT="$(grep ^TTYD_PORT= ~/.config/mypeople/queue.env 2>/dev/null | cut -d= -f2- || echo 7681)"
curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TTYD_PORT}/" | grep -q 200 || { echo "FAIL: ttyd not responding on $TTYD_PORT"; exit 1; }

# ttyd MUST be running with both `-a` (allow URL args) and `tmux attach`.
# Historic bugs:
#  - bare `tmux` (no `attach`) lands user in default session
#  - missing `-a` → URL `?arg=-t&arg=mc-X:Y` is silently ignored, also
#    lands user in default session (sometimes creating a bogus session
#    named "-t" from misparsed args)
ps -ax -o command | grep -E 'ttyd.*-a.* tmux attach' | grep -qv grep || { echo "FAIL: ttyd not running with '-a ... tmux attach' — attach links would be ignored or land in a default session"; ps -ax -o command | grep ttyd | head -3; exit 1; }
# ttyd MUST be running with disableLeaveAlert=true so the browser doesn't
# fire its "are you sure you want to close this page?" prompt on tab close.
ps -ax -o command | grep -E 'ttyd.*disableLeaveAlert=true' | grep -qv grep || { echo "FAIL: ttyd not running with -t disableLeaveAlert=true — closing the HUD attach tab will prompt the user"; ps -ax -o command | grep ttyd | head -3; exit 1; }
# End-to-end: attach URL with args must return 200 (not just trigger 404 or default)
curl -fsS -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${TTYD_PORT:-7681}/?arg=-t&arg=mc-main:Boss" | grep -q '^200$' || { echo "FAIL: ttyd attach-URL with args does not return 200"; exit 1; }

# tmux server (started by queue-client) MUST run with UTF-8 locale.
# If the host default is POSIX, tmux strips multi-byte chars (●, ⏺, ✻,
# ⏵, ⎿, ❯, box-drawing) to ASCII `_` inside its buffer — those bytes
# never reach the browser. Historic bug; assert by inspecting the
# running queue-client's environment.
#   - Linux: /proc/<pid>/environ (NUL-separated)
#   - macOS: `ps eww -p <pid>` (space-separated KEY=val on a single line)
QC_PID=$(cat "$INSTALL_DIR/run/queue-client.pid")
if [ -r "/proc/$QC_PID/environ" ]; then
  QC_ENV=$(tr '\0' '\n' < /proc/$QC_PID/environ)
else
  QC_ENV=$(ps eww -p "$QC_PID" -o command= 2>/dev/null | tr ' ' '\n')
fi
echo "$QC_ENV" | grep -qE '^LANG=.*[Uu][Tt][Ff].?8' || { echo "FAIL: queue-client running without UTF-8 LANG — tmux will mangle unicode to underscores"; echo "$QC_ENV" | grep -E '^LANG=|^LC_' || true; exit 1; }

# --- Tailscale ---

# tailscale status shows our node — works whether tailscaled runs via
# systemd / macOS system service / userland (Step 8.5 sets up the
# socket symlink in all three paths).
TS_STATUS=$(tailscale status --json 2>&1)
echo "$TS_STATUS" | jq -e '.Self.Online == true' >/dev/null || { echo "FAIL: tailscale Self.Online != true"; echo "$TS_STATUS" | head -40; exit 1; }
echo "$TS_STATUS" | jq -e '.Self.HostName' >/dev/null || { echo "FAIL: tailscale Self.HostName missing"; exit 1; }
TS_HOSTNAME_ACTUAL=$(echo "$TS_STATUS" | jq -r '.Self.HostName')
TS_IP=$(echo "$TS_STATUS" | jq -r '.Self.TailscaleIPs[0]')
echo "tailnet identity: $TS_HOSTNAME_ACTUAL @ $TS_IP"

# HUD reachable on the tailscale IP (proves the bind reaches the tailscale interface)
curl -fsS -o /dev/null -w 'HUD via TS IP: HTTP %{http_code}\n' "http://$TS_IP:9900/dashboard" | grep -q 200 || { echo "FAIL: HUD not reachable on tailscale IP"; exit 1; }

# ttyd reachable on tailscale IP
curl -fsS -o /dev/null -w 'ttyd via TS IP: HTTP %{http_code}\n' "http://$TS_IP:7681/" | grep -q 200 || { echo "FAIL: ttyd not reachable on tailscale IP"; exit 1; }

# Cleanup
mp kill "main:worker-1" >/dev/null 2>&1 || true
mp kill "main:Boss" >/dev/null 2>&1 || true

echo "VERIFY_OK"
```

## Failure modes


**Status file never written** → Stop hook didn't fire. Check `$INSTALL_DIR/run/hook-events.log` for any entries; if empty, the plugin didn't load — verify `--plugin-dir` was on the spawned `claude` command line and `hooks.json` parses.

**Status file exists but `summary` is empty** → claude didn't actually emit a last_assistant_message before stopping. Either the worker hit an error early or claude's Stop hook payload schema changed. Inspect `hook-events.log` and the worker's pane.

**Notification never lands in Boss pane** → check that `BOSS_ID` env var was set on the worker (`tmux capture-pane -t mc-main:worker-1 -p -S -100 | grep BOSS_ID`); check queue-client log for the inbound send task targeting Boss; check queue-server log for the POST from emit-event.

**Pane in copy-mode swallowed our send** → the target pane was scrolled (mouse wheel, manual entry, etc.) which puts tmux in copy/view-mode (`#{pane_in_mode}=1`). In that state `send-keys` types INTO copy-mode commands instead of the TUI's input buffer — silent failure. `tmux_send_text` auto-exits via `send-keys -X cancel` before every paste, AND mirrors the check after Enter so the pane is returned to text-editing mode for any human who picks it up next. Invariant: `pane_in_mode == 0` on every successful return of `tmux_send_text`. Keep both halves of this defense.

**macOS: `tailscale: command not found` but `/Applications/Tailscale.app` exists** → the Tailscale.app GUI is installed but its bundled CLI isn't symlinked into `PATH`. Two fixes:
- (Preferred) Open Tailscale.app → preferences → enable "Install CLI". Creates `/usr/local/bin/tailscale` pointing into the app bundle. Single source of truth.
- (Don't) `brew install tailscale`. Creates a parallel install path that competes with the app's bundled binary. If you've already started this and want to abort, `pkill -f 'brew.sh install tailscale'` and continue with the app's CLI symlink.

**Clicking a HUD attach link drops me in a default tmux session (not the target window)** → ttyd was started WITHOUT `-a` / `--url-arg`. By default ttyd refuses URL-supplied command args for safety, so `?arg=-t&arg=mc-X:Y` is silently dropped. Without those args the command run becomes bare `tmux attach`, which finds whatever tmux session exists or starts a new one — never the right window. The seed's Step 9 launches `ttyd -W -a -p ...`; the `-a` is mandatory. If a LaunchAgent / systemd unit on this host pre-existed and is missing `-a`, edit its ProgramArguments to insert `-a` before `-p` and restart the service.

**A bogus tmux session named `-t` shows up in `tmux list-sessions`** → side effect of the missing-`-a` bug above. When ttyd dropped the URL args but the user (or a script) then ran some `tmux ... -t ...` invocation, tmux created a session literally named `-t`. Safe cleanup (the leading dash trips up `tmux kill-session -t -t`):
```bash
tmux list-sessions -F '#{session_id} #{session_name}' | \
  awk '$2 == "-t" {print $1}' | \
  while read sid; do tmux kill-session -t "$sid"; done
```

## Cleanup

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
for s in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^mc-'); do
  tmux kill-session -t "$s" 2>/dev/null || true
done
for name in queue-client queue-server ttyd tailscaled; do
  pidfile="$INSTALL_DIR/run/$name.pid"
  [ -f "$pidfile" ] && sudo kill "$(cat $pidfile)" 2>/dev/null || true
done
pkill -f "$INSTALL_DIR/bin/queue-client.py" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/queue-server.py" 2>/dev/null || true
pkill -f "ttyd -W -p" 2>/dev/null || true
sudo pkill -f tailscaled 2>/dev/null || true
rm -rf "$INSTALL_DIR/run" "$INSTALL_DIR/bin" "$INSTALL_DIR/plugins" "$INSTALL_DIR/status"
```
