# SEED: mypeople

> seed-format: 1

> **You're an AI agent reading this seed.** Your job: run `## Step 0 Interview` to gather inputs, then execute every Step in order, then run the `## Verify` block in a sub-shell. On exit code 0 print `SEED_RESULT=DONE` and stop. On any blocker print `BLOCKED_REASON=<short reason>` and stop. Do not ask the user what to do with this file — that's already specified below.

## Goal

Install the mypeople runtime on this host with claude already installed: a small HTTP queue (queue-server), a heartbeat/dispatch client (queue-client), a CLI (`mp`) for `spawn / send / peek / kill / status`, a per-spawn Claude Code hooks plugin so agents emit lifecycle events, a Boss role that internalizes a doctrine on spawn, a HUD + per-tab browser-attach (ttyd), and a Tailscale tailnet join so the HUD + ttyd are reachable from anywhere on the tailnet via a stable hostname.

The agent backend is pluggable: `--backend claude` (default) and `--backend codex` (OpenAI Codex CLI) share the same queue, tmux, notification pipeline, and `mp` verbs. The queue-client carries a per-backend TUI-marker table so spawn/peek/send work for either; Codex turn-end is bridged to the same Stop-hook contract via the `codex-notify` hook. Codex support is install-complete out of the box, but a working `--backend codex` agent additionally requires the `codex` CLI to be installed AND logged in on this host (see Step 7.6).

After install: `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` (HUD) and `http://<TS_HOSTNAME>.<tailnet>.ts.net:7681/?arg=-t&arg=mc-main:Boss` (ttyd attach) Just Work from any tailnet node.

The seed describes **intent**; the agent reading it adapts to whatever OS / package manager / privilege model the host has. macOS, Debian, Ubuntu, RHEL — pick the right install incantation for each component named in `## Components`. If you're inside a sandboxed Linux container without TUN, that's a sandbox issue you resolve outside the seed (e.g. `--cap-add NET_ADMIN --device /dev/net/tun`).

## Done

Each independently verifiable from a fresh shell.

**JOIN-mode done** (when `UPSTREAM_QUEUE_URL` is set): the node runs a `queue-client` (+ `ttyd`) but NO local `queue-server` / Boss / tailnet identity; it appears in the UPSTREAM's `/clients` (and `mp status`) as a heartbeating client under `HOST_ID`; and a task submitted upstream targeting `HOST_ID/...` round-trips to this node's client. The self-contained criteria below apply only when `UPSTREAM_QUEUE_URL` is unset.

**Runtime (self-contained):**
- `curl http://127.0.0.1:9900/health` returns 200 with `{"status": "ok"}`.
- `queue-server` and `queue-client` processes both alive in `ps`.
- `ttyd` running with `tmux attach` so per-tab attach URLs work.
- tailscaled running, node online on the tailnet, HUD + ttyd reachable on the tailscale IP.
- **Liveness is heartbeat-based**: an agent whose host stops heartbeating (e.g. its container is removed) auto-drops from `/agents` and the HUD within `QUEUE_DEAD_AFTER` seconds — no zombie agents lingering as `alive` after `mp kill` times out on a dead host. The reaper also prunes the dead host from `/clients`.
- **Registry survives a server restart**: the in-memory registry is rebuilt automatically — each queue-client owns a durable record of its agents (`run/agents.json`) and re-announces them every heartbeat, so after a queue-server restart (or a reaper false-prune) the HUD repopulates with the still-running agents within one heartbeat cycle, with no manual re-registration.

**Boss role:**
- `~/mypeople/boss-CLAUDE.md` is installed (the Boss's job description, inlined in this seed).
- `mp spawn <host>/main:Boss --master --backend claude` creates the Boss tab AND sends an onboarding prompt that has the agent read `boss-CLAUDE.md`.
- After the Boss's onboarding turn, `~/mypeople/status/mc-main/Boss.json` exists with `status: "idle"` and a `summary` that mentions ≥2 doctrine keywords (`plan`, `approve`, `queue`, `mp`, `fire-and-forget`, `autonomous`).

**Agent loop:**
- `mp spawn <host>/main:worker-1 --backend claude --boss <host>/main:Boss` creates a worker tab whose env has `BOSS_ID=<host>/main:Boss`.
- `mp send <host>/main:worker-1 "msg"` types the message into the worker's pane via bracketed-paste, intact.
- `mp peek <host>/main:worker-1` reports the agent's TRUE live state: a header `state=BUSY` while a turn is running (even if its composer holds a freshly-queued message) and `state=IDLE` when awaiting input — derived from the Claude TUI footer, not inferred from a raw buffer dump. The Boss can always tell a working agent from a stuck one.
- When the worker's Stop hook fires: status JSON written, `[AGENT NOTIFICATION]` line typed into the Boss's pane via the queue.
- When a worker raises an **AskUserQuestion** form (a blocked turn, not a Stop): the `PreToolUse` hook fires `[AGENT QUESTION]` to the Boss carrying the question + the exact offered options, and the Boss can unblock it remotely with `mp answer <agent> <option-number | text>` — which actually selects/submits the form so the agent proceeds. No silent hang on an interactive question.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `QUEUE_PORT` | no | `9900` | port free or our own server | "TCP port (default 9900)" |
| `QUEUE_SECRET` | no | (auto) | existing key in `queue.env` | "Reuse or auto-gen" |
| `UPSTREAM_QUEUE_URL` | no | (empty ⇒ self-contained) | env / `queue.env` | "JOIN-mode switch. URL of an EXISTING upstream queue-server to register with, e.g. `http://mac-pro.<tailnet>.ts.net:9900`. When SET, this host installs as a JOIN node: it runs ONLY a queue-client (+ttyd) pointed at the upstream — no local queue-server, no local Boss, no own tailnet identity. When EMPTY (default), this host is a self-contained central node (original behavior)." |
| `UPSTREAM_QUEUE_SECRET` | cond. | none | env / `queue.env` | "JOIN-mode only, then REQUIRED: the upstream queue-server's `QUEUE_SECRET` — the join node MUST present the SAME secret or every request is 401. Handle securely — never echo or log it. If unset in JOIN-mode: `BLOCKED_REASON=upstream_secret_not_set`." |
| `QUEUE_DEAD_AFTER` | no | `4 × QUEUE_HEARTBEAT` (120s) | env | (no prompt — secs a host can be silent before its agents are reaped from the HUD; 4 missed heartbeats is generous so a loaded host isn't false-reaped) |
| `INSTALL_DIR` | no | `$HOME/mypeople` | dir exists | default |
| `HOST_ID` | no | `$(hostname -s)` | `hostname -s` works | "Stable host id used in every agent address (`<HOST_ID>/<sess>:<tab>`) and as the heartbeating-client name upstream. Use a durable name with NO transient/state words (e.g. `server`, not `server-temp`). Default: `hostname -s`." |
| OS deps (`tmux python3 jq procps`) | yes | apt | `command -v` each | (no prompt — agent runs apt install non-interactively) |
| claude CLI | yes | present **and `--plugin-dir`-capable** | `command -v claude` AND `claude --help \| grep -q -- --plugin-dir` | `BLOCKED_REASON=claude_not_installed`; if present but too old (no `--plugin-dir`): upgrade in Step 1 (don't block). A pre-installed claude on bare metal can be MONTHS old — `--plugin-dir` landed in 2.1.x. Spawn execs `claude … --plugin-dir <plugindir>`; an older claude rejects it with `error: unknown option '--plugin-dir'` and exits, which the spawn surfaces only as the generic `claude TUI didn't show 'bypass permissions on' banner within 30s` (see Failure modes). |
| `TS_AUTHKEY` | cond. | none | `[ -n "$TS_AUTHKEY" ]` (env or queue.env) | "Tailscale auth key — generate at https://login.tailscale.com/admin/settings/keys (reusable, ephemeral OFF, tag is fine). REQUIRED in self-contained mode (the seed cannot proceed without one). In JOIN-mode it's needed ONLY if this host can't already reach `UPSTREAM_QUEUE_URL` — if `curl $UPSTREAM_QUEUE_URL/health` already returns 200 (host already on the tailnet/LAN), the tailnet-join is skipped and no authkey is required." |
| `TS_HOSTNAME` | no | `mypeople-$(hostname -s)` | always available | "Stable hostname to announce on the tailnet. Default: `mypeople-<short hostname>`. Reachable as `<hostname>.<tailnet>.ts.net`." |
| TUN device (Linux only) | conditional | host-provided | `[ -c /dev/net/tun ]` on Linux | If missing on Linux *and Tailscale is being brought up here*: `BLOCKED_REASON=no_tun_device` — Tailscale needs a kernel TUN device. Sandboxed containers must be started with `--device /dev/net/tun --cap-add NET_ADMIN`. On macOS Tailscale uses the system extension instead; this input is N/A. JOIN-mode exception: if `UPSTREAM_QUEUE_URL` is already reachable, Tailscale is not started here, so the TUN check is N/A — skip it. |

## Components

| Component | Source | Notes |
|---|---|---|
| `queue-server.py` | inline | HTTP queue: clients, agents, task submit/poll/result, dashboard; heartbeat reaper auto-prunes agents on hosts that stop heartbeating |
| `queue-client.py` | inline | heartbeat + task dispatcher; tmux input via bracketed-paste; per-backend marker table drives spawn/peek/send for BOTH `claude` and `codex` (unknown backend falls back to claude) |
| `mp` CLI | inline | `spawn / send / peek / kill / status / answer` (peek classifies BUSY/IDLE; answer submits an AskUserQuestion form) |
| `plugins/tmux-boss-hooks/` | inline | lifecycle hooks. Claude: `emit-event` on SessionStart / Stop / SessionEnd → status file + boss notification; PreToolUse/AskUserQuestion → `[AGENT QUESTION]`. Codex: `codex-notify` on `agent-turn-complete` → the SAME Stop-hook contract (status file + boss notification) |
| `boss-CLAUDE.md` | inline | doctrine read by every Boss at spawn |
| `dashboard.html` | inline | HUD page, served from queue-server, polls /agents + /clients |
| OS pkgs | apt: `tmux python3 jq procps ttyd tailscale` (with ttyd binary fallback) | |

## Steps

### Install mode: self-contained (default) vs JOIN

This seed installs in one of two modes, decided solely by whether `UPSTREAM_QUEUE_URL` is set. Convention used throughout the Steps: **`MODE=join` iff `[ -n "$UPSTREAM_QUEUE_URL" ]`**, else `MODE=self`.

- **self-contained** (`UPSTREAM_QUEUE_URL` empty — default): this host is a central node — local queue-server + queue-client + ttyd + its own tailnet identity + a Boss. Original behavior; unchanged.
- **JOIN** (`UPSTREAM_QUEUE_URL` set): this host is a worker node that registers with an EXISTING upstream queue-server (e.g. a laptop running self-contained). It runs ONLY queue-client + ttyd, pointed at `UPSTREAM_QUEUE_URL` using `UPSTREAM_QUEUE_SECRET`. It does **NOT** start a local queue-server, does **NOT** create a local Boss, and does **NOT** claim its own tailnet identity (it only needs to *reach* the upstream). This is what satisfies capability §12 (cross-host routing): from the upstream, `mp spawn <this-host>/<sess>:<tab> --boss <upstream-host>/main:Boss` lands a tmux window HERE and routes this agent's Stop notifications back to that Boss.

A step tagged **[self-contained only]** is SKIPPED in JOIN-mode; a branch tagged **[JOIN]** runs only in JOIN-mode. (Rule 13 still holds in JOIN-mode: any Claude agents spawned on this node get their OWN fresh device-login — no token/auth volume is copied. The queue-client itself needs no Claude auth.)

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

On **Linux only**, also verify `[ -c /dev/net/tun ]`. If missing, you're in a sandboxed container without the right permissions — stop with `BLOCKED_REASON=no_tun_device` (caller fixes by re-creating the container with `--device /dev/net/tun --cap-add NET_ADMIN`). On macOS the TUN check is N/A. **JOIN-mode exception**: if `UPSTREAM_QUEUE_URL` is already reachable (`curl -fsS "$UPSTREAM_QUEUE_URL/health"` returns 200), this node will NOT bring up Tailscale, so the TUN check is N/A — skip it.

**Deterministic install (paste-and-run).** The prose above is the intent; this block makes a clean container actually install everything so the one-shot needs no human to "pick the command". Idempotent (installs only what's missing) and portable (apt/brew/dnf). `ttyd` is frequently absent from distro repos, so on Debian/Ubuntu it falls back to the static GitHub binary (x86_64/aarch64). A clean container that lacked `ttyd` made Step 9 fail `ttyd_failed_to_bind` — this is the root-cause fix.

```bash
need(){ command -v "$1" >/dev/null 2>&1; }
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq 2>/dev/null || true
  sudo apt-get install -y -qq tmux python3 jq procps curl ca-certificates >/dev/null 2>&1 || true
  if ! need ttyd; then
    case "$(uname -m)" in aarch64|arm64) TA=ttyd.aarch64;; *) TA=ttyd.x86_64;; esac
    sudo curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/latest/download/$TA" 2>/dev/null && sudo chmod +x /usr/local/bin/ttyd
  fi
elif command -v brew >/dev/null 2>&1; then
  for p in tmux jq ttyd; do brew list "$p" >/dev/null 2>&1 || brew install "$p" || true; done
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y tmux jq procps-ng ttyd curl >/dev/null 2>&1 || true
fi
# tailscale — needed for self-contained tailnet identity; skip in JOIN mode when the upstream is already reachable.
if [ -z "${UPSTREAM_QUEUE_URL:-}" ] || ! curl -fsS "${UPSTREAM_QUEUE_URL:-http://255.255.255.255:1}/health" >/dev/null 2>&1; then
  need tailscale || { curl -fsSL https://tailscale.com/install.sh | sudo sh >/dev/null 2>&1 || true; }
fi
for t in tmux jq ttyd python3 curl; do need "$t" || { echo "BLOCKED_REASON=${t}_install_failed"; exit 1; }; done
echo "OS deps OK: tmux jq ttyd python3 curl$(need tailscale && printf ' tailscale')"
```

**Also ensure `claude` is new enough to support `--plugin-dir`** (the spawn path passes it; an older claude rejects it and every spawn fails with a misleading banner-timeout — surfaced live on a Raspberry Pi whose pre-installed claude was 2.0.5). `--plugin-dir` landed in claude **2.1.x**. Detect + upgrade:

```bash
if command -v claude >/dev/null 2>&1 && ! claude --help 2>&1 | grep -q -- '--plugin-dir'; then
  echo "claude $(claude --version 2>&1 | head -1) lacks --plugin-dir — upgrading"
  # global npm install (symlink in /usr/local/bin) needs root; native/local installs can self-update.
  claude update 2>/dev/null \
    || sudo npm install -g @anthropic-ai/claude-code@latest 2>/dev/null \
    || claude install latest 2>/dev/null \
    || { echo "BLOCKED_REASON=claude_too_old_no_plugin_dir"; exit 1; }
  claude --help 2>&1 | grep -q -- '--plugin-dir' || { echo "BLOCKED_REASON=claude_too_old_no_plugin_dir"; exit 1; }
fi
```

A `claude update` / npm upgrade preserves the node's auth (`~/.claude/.credentials.json` is untouched), so re-auth is not needed afterward.

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

### 4. Write `queue-server.py` [self-contained only]

In JOIN-mode this Step is skipped — the node registers with the upstream queue-server instead of running its own.

```bash
# [self-contained only] — JOIN nodes use the upstream's queue-server, not a local one.
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  echo "[JOIN] skipping local queue-server (will use upstream $UPSTREAM_QUEUE_URL)"
else
cat > "$INSTALL_DIR/bin/queue-server.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople queue-server."""

import http.server, json, os, sys, threading, time, uuid
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET = os.environ.get("QUEUE_SECRET", "")
HEARTBEAT = int(os.environ.get("QUEUE_HEARTBEAT", "30"))
# Heartbeat-based liveness. An agent's host re-heartbeats every HEARTBEAT secs;
# a removed container stops heartbeating, so we mark its agents dead once the
# host has been silent for DEAD_AFTER secs (default = 4 missed heartbeats —
# generous so a loaded host isn't false-reaped) and the reaper drops them from
# the registry / HUD. Without this an agent whose container is gone shows
# 'alive' forever, because `state` is written once at register and `mp kill`
# times out on a dead host. Tune via QUEUE_DEAD_AFTER / QUEUE_REAP_INTERVAL.
DEAD_AFTER = float(os.environ.get("QUEUE_DEAD_AFTER", str(HEARTBEAT * 4)))
REAP_INTERVAL = float(os.environ.get("QUEUE_REAP_INTERVAL", str(max(5, HEARTBEAT // 2))))
# Idempotency dedup window. A submit carrying an idempotency_key we've already
# seen within this many seconds is collapsed onto the original task instead of
# enqueuing a duplicate — exactly-once notification delivery even if a Stop hook
# double-fires or a submit is retried. Tune via QUEUE_DEDUP_WINDOW.
DEDUP_WINDOW = float(os.environ.get("QUEUE_DEDUP_WINDOW", "45"))
START_TS = time.time()

_lock = threading.Lock()
clients = {}
agents = {}
tasks = {}
idem_seen = {}   # idempotency_key -> (task_id, ts), pruned on submit


def _host_of(agent_id):
    if "/" in agent_id and ":" in agent_id:
        return agent_id.split("/", 1)[0]
    return ""


def _agent_alive(v, now):
    """True iff the agent's host heartbeated within DEAD_AFTER seconds.

    The host's queue-client heartbeats on a fixed interval; when its container
    is removed the heartbeats stop, so its agents age out of 'alive'. Falls back
    to the agent's own register ts when the host has no heartbeat yet (the
    spawn/heartbeat race right after register), so a just-registered agent on a
    not-yet-heartbeated host isn't reaped. Call under _lock."""
    c = clients.get(v.get("host", ""))
    last = c.get("ts", 0) if c else v.get("ts", 0)
    return (now - last) <= DEAD_AFTER


def reaper_loop():
    """Drop agents whose host stopped heartbeating, plus stale clients, so the
    registry and the HUD reflect true current liveness instead of last-known
    state. This is what keeps a removed container's agent from showing 'alive'
    forever (the zombie-agent bug)."""
    while True:
        time.sleep(REAP_INTERVAL)
        now = time.time()
        with _lock:
            dead_agents = [k for k, v in agents.items() if not _agent_alive(v, now)]
            for k in dead_agents:
                agents.pop(k, None)
            dead_clients = [h for h, c in clients.items()
                            if now - c.get("ts", 0) > DEAD_AFTER]
            for h in dead_clients:
                clients.pop(h, None)
        if dead_agents or dead_clients:
            sys.stderr.write(
                f"{time.strftime('%H:%M:%S')} reaper pruned "
                f"agents={dead_agents} clients={dead_clients}\n")


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
            now = time.time()
            with _lock:
                items = []
                for k, v in agents.items():
                    # Heartbeat-based liveness: never surface an agent whose host
                    # has gone silent (removed container) even if the reaper
                    # hasn't swept it yet — the HUD must show TRUE current state.
                    if not _agent_alive(v, now):
                        continue
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
            if action not in ("spawn", "send", "peek", "kill", "answer"):
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
            ikey = (data.get("idempotency_key") or "").strip()
            with _lock:
                now = time.time()
                if ikey:
                    # Prune expired keys, then collapse a duplicate onto the
                    # original task so a re-fired/retried notification is never
                    # enqueued (and thus never delivered) twice.
                    for k in [k for k, (_, ts) in idem_seen.items()
                              if now - ts > DEDUP_WINDOW]:
                        idem_seen.pop(k, None)
                    prev = idem_seen.get(ikey)
                    if prev and now - prev[1] <= DEDUP_WINDOW:
                        sys.stderr.write(
                            f"{time.strftime('%H:%M:%S')} dedup: dropped duplicate "
                            f"submit key={ikey[:12]} -> task {prev[0][:8]}\n")
                        return self._json(200, {"task_id": prev[0], "deduped": True})
                    idem_seen[ikey] = (tid, now)
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
    threading.Thread(target=reaper_loop, daemon=True).start()
    print(f"queue-server listening on 0.0.0.0:{PORT} "
          f"(reaper: dead_after={DEAD_AFTER:.0f}s every {REAP_INTERVAL:.0f}s)", flush=True)
    server.serve_forever()
PY_EOF
chmod +x "$INSTALL_DIR/bin/queue-server.py"
fi
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

# Durable local record of the agents THIS client manages. The central server's
# registry is in-memory: a server restart — or a heartbeat gap that trips its
# liveness reaper — drops every registration, and agents only register at spawn,
# so the HUD goes empty while the agents are still running. This client owns the
# list and RE-ANNOUNCES it on every heartbeat (see reannounce_agents), making the
# server's agent set a self-healing projection of the live clients.
AGENTS_FILE = os.path.join(INSTALL_DIR, "run", "agents.json")
_agents_lock = threading.Lock()

PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"

# Per-backend TUI marker table. The tmux send/peek mechanism is backend-generic
# (bracketed paste + Enter); only the on-screen chrome it keys off differs.
# Markers captured live from each TUI (Codex strings from codex-cli 0.132.0):
#   - "ready":  substring present once the agent's TUI is up and accepting input
#               (Claude startup banner/footer; Codex startup box ">_ OpenAI Codex").
#   - "busy":   substring shown ONLY while a turn is actively running.
#               Both TUIs print "esc to interrupt"; Codex wraps it as
#               "* Working (Ns * esc to interrupt)".
#   - "prompt": the composer prompt glyph. Claude is U+276F; Codex is U+203A
#               — DIFFERENT glyphs.
#   - "idle":   substrings proving an idle composer is present (prompt glyph, or
#               a stable footer token). Claude "bypass permissions on"; Codex
#               footer "<model> SEP <cwd>" where SEP is U+00B7 surrounded by spaces.
#   - "region_end": footer substring bounding the BOTTOM of the composer region
#               for draft detection. NOTE: _composer_draft also stops at the
#               separator RULE ('────') just under the composer, which sits
#               ABOVE this footer — stopping only at the footer used to swallow
#               that rule line as fake "draft content" (every idle composer read
#               as stuck). The rule is the real bottom edge; the footer is the
#               backstop for backends that don't draw one.
#   - "paste":  lowercased paste-draft tag a stuck multiline draft collapses to.
MARKERS = {
    "claude": {
        "ready": "bypass permissions on",
        "busy": "esc to interrupt",
        "prompt": "❯",
        "idle": ("❯", "bypass permissions on"),
        "region_end": "bypass permissions on",
        "paste": "[pasted text",
    },
    "codex": {
        "ready": "OpenAI Codex",            # startup box: ">_ OpenAI Codex (vX)"
        "busy": "esc to interrupt",         # "* Working (Ns * esc to interrupt)"
        "prompt": "›",
        "idle": ("›", " · "),     # prompt glyph, or "<model> · <cwd>" footer
        "region_end": " · ",           # footer "<model> · <cwd>"
        "paste": "[pasted text",
    },
}
DEFAULT_BACKEND = "claude"


def markers_for(backend):
    return MARKERS.get(backend or DEFAULT_BACKEND, MARKERS[DEFAULT_BACKEND])


def _agent_backend(aid):
    """Backend for an agent id from this client's durable record (agents.json).
    Falls back to 'claude' so existing/unknown agents behave exactly as before."""
    with _agents_lock:
        meta = _load_agents().get(aid) or {}
    return meta.get("backend") or DEFAULT_BACKEND


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
        # Re-announce our agents so a restarted/empty server rebuilds the live
        # set within one heartbeat cycle — no manual re-registration ever needed.
        try:
            reannounce_agents()
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} reannounce FAIL: {e}", file=sys.stderr, flush=True)
        time.sleep(HEARTBEAT)


def tmux_run(*args, timeout=5):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout)


def _pane_backend(target):
    """Best-effort: which backend binary is ACTUALLY RUNNING in this pane?

    Returns 'claude', 'codex', or None (bare shell / can't classify). After the
    spawn's `exec <backend>`, tmux's #{pane_pid} IS the backend process, so its
    command line is ground truth; we also scan its direct children (codex's node
    launcher re-execs a vendored `codex` binary as a child). This is what lets
    the idempotent re-spawn path REFUSE to relabel a pane as a backend it isn't
    running — the 'registry says codex but the process is claude' bug: a
    --backend codex spawn onto a window already holding a claude pane used to
    take the reuse short-circuit, flip the registry label to codex, and return
    success while claude kept running. Verify by the process, never the label."""
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_pid}")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    pid = r.stdout.strip()
    try:
        cmds = subprocess.run(["ps", "-o", "command=", "-p", pid],
                              capture_output=True, text=True, timeout=5).stdout
        kids = subprocess.run(["pgrep", "-P", pid],
                              capture_output=True, text=True, timeout=5).stdout.split()
        for k in kids:
            cmds += "\n" + subprocess.run(["ps", "-o", "command=", "-p", k],
                                          capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    low = cmds.lower()
    # The codex exec line carries `codex ...` (and the codex-notify path); the
    # claude exec line carries `claude ...` (+ the tmux-boss-hooks plugin path,
    # which contains no 'codex' token). So each backend's command matches only
    # its own name — no cross-false-positive.
    if "codex" in low:
        return "codex"
    if "claude" in low:
        return "claude"
    return None


def _load_agents():
    try:
        with open(AGENTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_agents(d):
    os.makedirs(os.path.dirname(AGENTS_FILE), exist_ok=True)
    tmp = AGENTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, AGENTS_FILE)   # atomic


def record_agent(aid, backend, boss_id, is_master=False):
    """Persist an agent this client just spawned so we can re-announce it later."""
    with _agents_lock:
        d = _load_agents()
        d[aid] = {"backend": backend, "boss_id": boss_id, "is_master": bool(is_master)}
        _save_agents(d)


def forget_agent(aid):
    with _agents_lock:
        d = _load_agents()
        if d.pop(aid, None) is not None:
            _save_agents(d)


def _window_alive(aid):
    """aid = host/session:tab — alive iff its tmux window still exists here."""
    try:
        rest = aid.split("/", 1)[1]
        sess, tab = rest.split(":", 1)
    except (IndexError, ValueError):
        return False
    r = tmux_run("list-windows", "-t", f"mc-{sess}", "-F", "#{window_name}")
    return r.returncode == 0 and tab in r.stdout.split()


def reannounce_agents():
    """Re-register every agent this client manages whose tmux window is still
    alive; forget the ones whose window is gone (per-agent self-cleanup). Called
    each heartbeat so the server's registry self-heals after any restart/wipe."""
    with _agents_lock:
        d = _load_agents()
    if not d:
        return
    gone = []
    for aid, meta in d.items():
        if not _window_alive(aid):
            gone.append(aid)
            continue
        try:
            post_json("/agents/register", {
                "agent_id": aid, "backend": meta.get("backend", ""), "state": "alive",
                "boss_id": meta.get("boss_id", ""), "is_master": meta.get("is_master", False)})
        except urllib.error.URLError:
            pass  # server unreachable → next heartbeat retries
    if gone:
        with _agents_lock:
            d = _load_agents()
            for aid in gone:
                d.pop(aid, None)
            _save_agents(d)


def _is_busy(target, backend=DEFAULT_BACKEND):
    """True if a turn is actively running in this pane (busy marker on screen)."""
    m = markers_for(backend)
    r = tmux_run("capture-pane", "-t", target, "-p")
    return r.returncode == 0 and m["busy"] in r.stdout.lower()


def _composer_draft(target, backend=DEFAULT_BACKEND):
    """Classify any UN-submitted draft sitting in the composer.

    Returns 'none' (composer empty → text submitted/queued), 'literal' (typed or
    pasted text still in the box), or 'chip' (a collapsed '[Pasted text #N]'
    placeholder). This is the ground-truth signal `tmux_send_text` keys off to
    decide whether the message actually fired a turn.

    The composer region is the LAST prompt-glyph line down to the FIRST boundary
    below it — the composer's bottom separator RULE ('────') or the footer,
    whichever comes first. Terminating ONLY at the footer (the old bug) swallowed
    the rule line itself as 'draft content', so EVERY idle/empty composer read as
    a stuck draft: verification could never tell "submitted" from "stuck", the
    BSpace+Enter recovery fired blindly on every send, and a paste chip could be
    BSpace-deleted into a lost message. Stopping at the rule fixes the predicate.

    NO busy short-circuit: a draft can sit in the composer while a PRIOR turn is
    still running (paste lands mid-turn, the follow-up Enter absorbed) — that
    orphaned draft, left unsubmitted when the prior turn ends, is the exact
    "agent idle with queued text" bug, so we classify composer content regardless
    of the busy marker. Glyph / footer / paste tag are backend-specific (MARKERS).
    """
    m = markers_for(backend)
    prompt, region_end, paste = m["prompt"], m["region_end"], m["paste"]
    r = tmux_run("capture-pane", "-t", target, "-p")
    if r.returncode != 0:
        return "none"
    lines = r.stdout.splitlines()
    pi = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith(prompt):   # composer prompt glyph
            pi = i
            break
    if pi is None:
        return "none"
    region = []
    for l in lines[pi:]:
        s = l.strip()
        if region_end in l.lower() or (s and set(s) <= {"─"}):  # footer OR rule
            break
        region.append(l)
    if not region:
        return "none"
    text = "\n".join(region)
    if paste in text.lower():
        return "chip"
    first_after_prompt = region[0].split(prompt, 1)[1] if prompt in region[0] else ""
    if backend == "codex" and not "\n".join(region[1:]).strip():
        codex_placeholders = {
            "Explain this codebase",
            "Find and fix a bug in @filename",
            "Write tests for @filename",
            "Summarize recent commits",
            "Use /skills to list available skills",
            "Implement {feature}",
        }
        if first_after_prompt.strip() in codex_placeholders:
            return "none"
    if first_after_prompt.strip() or "\n".join(region[1:]).strip():
        return "literal"
    return "none"


def tmux_send_text(target, text, backend=DEFAULT_BACKEND):
    """Bracketed-paste send that reliably SUBMITS a turn, with copy-mode defense.

    Three failure modes are handled:
    1. copy-mode: typing into a pane in tmux's view-mode types INTO copy-mode
       commands, not the composer. Cancel it before AND after.
    2. absorbed Enter / paste-draft: a paste landing at/after turn-end (or under
       heavy load) captures the follow-up Enter as a trailing newline, so the
       message becomes an un-submitted draft. We DELAY the Enter so it settles as
       a submit, then VERIFY the composer actually emptied; while a draft
       persists we resubmit it — Enter-only for a '[Pasted text #N]' chip (BSpace
       would DELETE the whole chip → lost message), BSpace+Enter for a literal
       multiline draft (eat the trailing newline, then submit).
    3. silent no-fire: text delivered but never became a turn. The success gate
       is POSITIVE — the agent goes busy (our turn started) OR the composer is
       empty across two consecutive reads (submitted / queued behind a running
       turn). So an `mp send` that returns ok has provably fired a turn — or
       fails loudly — instead of leaving text idle in the composer.

    EXACTLY-ONCE submission — do NOT press Up here. `Up` recalls the last
    submitted message back INTO the composer; the draft-check then reads it as a
    fresh draft and resubmits it (the duplicate-notification bug). The recovery
    only ever resubmits the draft ALREADY in the composer, and Enter on an empty
    composer is a harmless no-op (Claude never submits an empty composer), so a
    given message is delivered exactly once.
    """
    # Exit copy-mode / view-mode if active.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)

    # Was a turn already running before we sent? If so, our message can only be
    # QUEUED (composer empty), never drive a fresh busy-edge of its own — so we
    # must NOT read the prior turn's busy marker as proof OUR message submitted.
    busy_before = _is_busy(target, backend)

    # Bracketed-paste send (strip any trailing newline so we control submission).
    safe = text.replace(PASTE_END, "").replace(PASTE_START, "").rstrip("\n")
    payload = f"{PASTE_START}{safe}{PASTE_END}"
    r = tmux_run("send-keys", "-t", target, "-l", "--", payload)
    if r.returncode != 0:
        return False, r.stderr.strip()

    # DELAYED submit: let the paste fully settle before Enter so the Enter is
    # processed as a submit instead of being absorbed into the paste buffer.
    # 0.6s (was 0.4): a large paste under load needs longer to settle before the
    # Enter registers as a submit rather than being eaten by the paste buffer.
    time.sleep(0.6)
    r = tmux_run("send-keys", "-t", target, "Enter")
    if r.returncode != 0:
        return False, r.stderr.strip()

    # VERIFY + RESUBMIT until the message provably fired. Check the draft FIRST
    # (so an orphaned draft sitting under a still-running PRIOR turn is caught,
    # not masked by that turn's busy marker), then accept on a busy-edge of our
    # own or a stably-empty composer. Loud failure if it never clears.
    #
    # PATIENCE under a running turn: when a turn is in flight the pasted message
    # is QUEUED (or held) and the composer clears on its own once the turn ends —
    # so if a draft persists WHILE the target is busy we WAIT for the turn to
    # finish instead of hammering BSpace+Enter. The old code fought every draft
    # with BSpace within an 8×0.4s≈3.2s window: too short for a busy peer, so it
    # reported "never submitted" on messages that were actually queued (a FALSE
    # negative → the caller re-sent → duplicate), and the blind BSpace churn could
    # merge/corrupt a queued message under contention. The wider 20×0.5s≈10s
    # budget + the busy-wait reserves the active key-recovery (BSpace+Enter) for a
    # genuinely absorbed Enter on an IDLE composer. A genuinely stuck draft still
    # persists across the whole budget → still a loud, honest failure. (mp send +
    # boss_ping mp timeouts were widened to 30s to cover the longer budget.)
    ok = False
    empty_idle_seen = 0
    for attempt in range(20):
        time.sleep(0.5)
        kind = _composer_draft(target, backend)
        if kind != "none":                       # a draft is still sitting in the composer
            empty_idle_seen = 0
            if _is_busy(target, backend):        # turn running → msg is queued/held; wait it out, don't corrupt it
                continue
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} mp send: {kind} draft did not submit, resubmitting (attempt {attempt + 1}) -> {target}\n")
            if kind == "chip":
                tmux_run("send-keys", "-t", target, "Enter")    # submit chip (BSpace would delete it)
            else:
                tmux_run("send-keys", "-t", target, "BSpace")   # eat the trailing newline
                time.sleep(0.15)
                tmux_run("send-keys", "-t", target, "Enter")    # then submit the draft
            continue
        # Composer is empty → the text left the input (submitted or queued).
        if busy_before or _is_busy(target, backend):
            ok = True                            # queued behind a running turn (prior or our own) → fired
            break
        empty_idle_seen += 1                     # idle + empty: text submitted; want it stable
        if empty_idle_seen >= 2:
            ok = True
            break

    # Post-injection mirror: ensure pane is left in text-editing mode.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")

    if not ok:
        return False, "message never submitted (composer still held a draft after 20 retries)"
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
            # Idempotent re-spawn: window already exists. Callers (e.g. a Boss
            # orchestrating workers) may legitimately re-spawn the same id if a
            # worker disconnected but its tmux window survived — so reuse is OK
            # *only* when the pane is actually running the requested backend.
            # NEVER silently relabel: if the pane runs a DIFFERENT backend than
            # asked for, reusing it would flip the registry label (e.g. to
            # 'codex') while the process stays 'claude' — the exact CEO-caught
            # bug. Verify by the RUNNING PROCESS and refuse the mismatch loudly
            # instead of lying in the registry.
            running = _pane_backend(f"{mc_sess}:{tab}")
            if running is not None and running != backend:
                return False, (f"window {mc_sess}:{tab} already runs backend={running!r}; "
                               f"refusing to relabel it as {backend!r} (that would make the "
                               f"registry lie). `mp kill {aid}` then re-spawn --backend {backend}.")
            record_agent(aid, backend, boss_id, is_master)
            try:
                post_json("/agents/register", {"agent_id": aid, "backend": backend, "state": "alive", "boss_id": boss_id, "is_master": is_master})
            except urllib.error.URLError as e:
                return False, f"re-register failed: {e}"
            return True, {"agent_id": aid, "tmux_target": f"{mc_sess}:{tab}", "boss_id": boss_id, "is_master": is_master, "reused_existing": True, "running_backend": running}
        r = tmux_run("new-window", "-t", mc_sess, "-n", tab, "-c", cwd)
        if r.returncode != 0:
            return False, f"new-window failed: {r.stderr.strip()}"

    if backend == "claude":
        spawn_cmd = (
            f"claude --dangerously-skip-permissions "
            f"--settings {shlex.quote(json.dumps({'skipDangerousModePermissionPrompt': True}))} "
            f"--plugin-dir {shlex.quote(PLUGIN_DIR)}"
        )
    elif backend == "codex":
        # Codex's turn-end signal is its `notify` program (NOT a Stop hook).
        # Point it at the codex-notify shim per-spawn so no global ~/.codex
        # config edit is required; the shim re-emits emit-event's Stop-branch
        # notification on the SAME queue contract. `-c key=value` parses value
        # as TOML — a JSON array is valid TOML. `--dangerously-bypass-approvals-
        # and-sandbox` is the autonomy analog of Claude's --dangerously-skip-
        # permissions (composer shows "permissions: YOLO mode").
        notify_script = os.path.join(PLUGIN_DIR, "hooks", "codex-notify")
        notify_cfg = "notify=" + json.dumps(["bash", notify_script])
        spawn_cmd = (
            f"codex --dangerously-bypass-approvals-and-sandbox --enable hooks "
            f"-c {shlex.quote(notify_cfg)}"
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
    # Env hygiene for codex: a stray AGENT_ROLE inherited from a parent shell
    # made the legacy codex hook mis-route notifications. mypeople doesn't set
    # AGENT_ROLE, so this is purely defensive (harmless no-op when unset).
    pre_exec = "unset AGENT_ROLE && " if backend == "codex" else ""
    shell_cmd = f"cd {shlex.quote(cwd)} && {' && '.join(env_parts)} && {pre_exec}exec {spawn_cmd}"

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
    elif backend == "codex":
        # Codex shows interactive gates BEFORE the composer on a fresh start: an
        # "Update available" prompt and a directory-trust prompt. Pre-seeding
        # [projects."<cwd>"].trust_level = "trusted" in ~/.codex/config.toml (the
        # CEO already does this per project) and disabling the update notifier
        # removes both; this loop ALSO dismisses them defensively so a spawn
        # never silently hangs on a gate. Ready when the startup banner OR the
        # composer footer (markers_for('codex')['region_end'], "<model> · <cwd>")
        # is on screen — the footer is the true "accepting input" signal and the
        # banner can be delayed by MCP init. Timeout is generous (60s): codex's
        # MCP startup retries on a bad/expired token, which delays the composer.
        cm = markers_for("codex")
        ready, footer = cm["ready"], cm["region_end"]
        deadline = time.time() + 60
        while time.time() < deadline:
            frame = tmux_run("capture-pane", "-t", target, "-p").stdout or ""
            low = frame.lower()
            if "do you trust" in low:                       # trust gate
                tmux_run("send-keys", "-t", target, "Enter")        # default: Yes, continue
                time.sleep(0.5); continue
            # Match the NUMBERED update prompt specifically ("1. Update now"),
            # not the persistent "Update available" info box, so we never
            # mis-fire keystrokes at the composer once it has rendered.
            if "update now" in low:                          # update gate
                tmux_run("send-keys", "-t", target, "Down")         # move off "Update now"
                time.sleep(0.1)
                tmux_run("send-keys", "-t", target, "Enter")        # choose Skip
                time.sleep(0.5); continue
            if ready in frame or footer in frame:
                break
            time.sleep(0.5)
        else:
            return False, "codex TUI didn't reach the composer (ready/footer marker) within 60s"

    # If --master, bootstrap the Boss with its doctrine: send an onboarding
    # prompt that instructs the agent to read ~/mypeople/boss-CLAUDE.md and
    # ack with a one-line summary. The spawn returns once the prompt is sent;
    # the agent's first Stop event will fire when it finishes reading + acking,
    # at which point its status.json will reflect the doctrine.
    if is_master:
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

    record_agent(aid, backend, boss_id, is_master)
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
    ok, err = tmux_send_text(target, msg, _agent_backend(aid))
    if not ok:
        return False, err
    return True, {"delivered_to": target}


# Claude Code's TUI prints "esc to interrupt" in its footer ONLY while a turn is
# actively running; when the agent is idle the footer is just the bypass-perms
# hint and the composer (❯) awaits input. That token is the ground-truth busy
# signal. A raw `capture-pane` dump buries it under the composer + footer, so an
# agent that's mid-turn (e.g. installing) — especially one whose composer holds a
# freshly-queued `mp send` — reads as idle/stuck. peek must classify and surface
# the live state, not make the Boss infer it from the bottom of a text wall.
PEEK_BUSY_MARKER = "esc to interrupt"


def peek_state(pane_text, backend=DEFAULT_BACKEND):
    """Classify an agent pane as BUSY / IDLE / UNKNOWN from its live frame.

    Only the tail (the on-screen UI chrome — status line, composer, footer) is
    inspected so a stale scrollback line can't spoof the state. Use the last 15
    NON-BLANK lines: `capture-pane -S` leaves trailing blank rows on a tall pane
    (e.g. a wide ttyd-attached container is 70+ rows), which would push the
    footer/composer out of a raw last-15 slice and mis-read a healthy idle agent
    as UNKNOWN. Busy/idle markers are backend-specific (see MARKERS)."""
    m = markers_for(backend)
    idle_markers = m["idle"] if isinstance(m["idle"], tuple) else (m["idle"],)
    tail = "\n".join([l for l in pane_text.splitlines() if l.strip()][-15:])
    low = tail.lower()
    if m["busy"] in low:
        return "BUSY", "a turn is actively running (busy marker present)"
    if any((mk in tail) or (mk.lower() in low) for mk in idle_markers):
        return "IDLE", "awaiting input (no turn running)"
    return "UNKNOWN", f"no {backend} TUI footer detected (starting up, a shell, or exited)"


def execute_peek(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    target = f"mc-{sess}:{tab}"
    if tmux_run("has-session", "-t", f"mc-{sess}").returncode != 0:
        return False, f"session mc-{sess} does not exist"
    # One fresh capture: visible frame (bottom = live state) + 200 lines of
    # scrollback for work context. Classify the frame, then surface the verdict
    # in a header so the Boss gets an accurate read at a glance.
    r = tmux_run("capture-pane", "-t", target, "-p", "-S", "-200")
    if r.returncode != 0:
        return False, r.stderr.strip()
    pane = r.stdout
    state, detail = peek_state(pane, _agent_backend(aid))
    header = f"[mp peek {aid}] state={state} — {detail}\n" + ("─" * 72) + "\n"
    return True, {"content": header + pane, "state": state, "activity": detail}


def execute_kill(task):
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    mc_sess = f"mc-{sess}"
    target = f"{mc_sess}:{tab}"
    if tmux_run("has-session", "-t", mc_sess).returncode != 0:
        forget_agent(aid)
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
    forget_agent(aid)
    try:
        post_json("/agents/unregister", {"agent_id": aid})
    except urllib.error.URLError:
        pass
    return True, {"killed": target}


def execute_answer(task):
    """Answer an AskUserQuestion form the agent is BLOCKED on, then submit it —
    so the Boss can unblock a remote question. A bare `send` only piles text into
    the composer without selecting/submitting; this drives the actual widget.

    payload.answer:
      - an integer "N"  -> select option N of the (first) question. The widget
                           opens with option 1 highlighted; Down moves the
                           highlight, Enter confirms.
      - any other text  -> type a free-form custom answer and submit it.
    """
    aid = task.get("target_agent", "")
    parsed = parse_agent_id(aid)
    if not parsed:
        return False, "bad target_agent"
    _, sess, tab = parsed
    mc_sess = f"mc-{sess}"
    target = f"{mc_sess}:{tab}"
    if tmux_run("has-session", "-t", mc_sess).returncode != 0:
        return False, f"session {mc_sess} does not exist"
    answer = str(task.get("payload", {}).get("answer", "")).strip()
    if not answer:
        return False, "empty answer"

    # Same copy-mode defense as tmux_send_text: a pane stuck in view-mode would
    # eat the navigation keys.
    r = tmux_run("display-message", "-t", target, "-p", "#{pane_in_mode}")
    if r.returncode == 0 and r.stdout.strip() == "1":
        tmux_run("send-keys", "-t", target, "-X", "cancel")
        time.sleep(0.1)

    if answer.isdigit():
        n = int(answer)
        if n < 1:
            return False, "option number must be >= 1"
        # Down (N-1) times from the default top highlight, then Enter to confirm.
        for _ in range(n - 1):
            tmux_run("send-keys", "-t", target, "Down")
            time.sleep(0.08)
        time.sleep(0.12)
        r = tmux_run("send-keys", "-t", target, "Enter")
        if r.returncode != 0:
            return False, r.stderr.strip()
        return True, {"answered": target, "selected_option": n}

    # Free-form answer: type it literally and submit (custom-answer path).
    ok, err = tmux_send_text(target, answer, _agent_backend(aid))
    if not ok:
        return False, err
    return True, {"answered": target, "text": answer}


HANDLERS = {"spawn": execute_spawn, "send": execute_send, "peek": execute_peek,
            "kill": execute_kill, "answer": execute_answer}


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
    # 30s (was 10): tmux_send_text now patiently waits out a running turn so a queued
    # message is confirmed delivered (no false "Send FAILED" → no duplicate re-send).
    t = submit_and_wait(cfg, body, timeout=30)
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


def cmd_answer(cfg, args):
    # Answer an AskUserQuestion form the agent is blocked on (option number or
    # free text), actually selecting/submitting it so the agent proceeds.
    if len(args) < 2:
        print("Usage: mp answer <agent_id> <option-number | free text>", file=sys.stderr); sys.exit(2)
    aid = canonicalize_agent_id(args[0], cfg["HOST_ID"])
    answer = " ".join(args[1:])
    body = {"action": "answer", "target_agent": aid, "payload": {"answer": answer}}
    t = submit_and_wait(cfg, body, timeout=10)
    if t["status"] == "done":
        r = t.get("result") or {}
        if "selected_option" in r:
            print(f"Answered {aid}: selected option {r['selected_option']}")
        else:
            print(f"Answered {aid}: {r.get('text','submitted')}")
    else:
        print(f"Answer FAILED: {t.get('error', '?')}", file=sys.stderr); sys.exit(1)


COMMANDS = {"status": cmd_status, "spawn": cmd_spawn, "send": cmd_send, "peek": cmd_peek, "kill": cmd_kill, "answer": cmd_answer}


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
    "PreToolUse":   [{"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event", "timeout": 10}]}],
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

# Idempotency key for a notification: a stable digest of (event, session, agent,
# message). If the Stop hook ever fires twice for one turn-end — or a submit is
# retried — both carry the SAME key, so the queue-server dedups them inside its
# window and the Boss is notified exactly once. Portable across Debian (sha256sum)
# and macOS (shasum).
idem_key() {  # args: parts that uniquely identify this notification
  local s="$*"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$s" | sha256sum | cut -c1-32
  else
    printf '%s' "$s" | shasum -a 256 | cut -c1-32
  fi
}

# Append to local log
echo "{\"ts\":\"$TS\",\"event\":\"$EVENT\",\"agent_id\":\"$AGENT_ID\",\"session_id\":\"$SID\"}" >> "$LOG"

# Parse session+tab from AGENT_ID = host/session:tab (used by every branch).
HOST_PART="${AGENT_ID%%/*}"
REST="${AGENT_ID#*/}"
SESS_PART="${REST%%:*}"
TAB_PART="${REST#*:}"
STATUS_DIR="$INSTALL_DIR/status/mc-$SESS_PART"

# --- PreToolUse / AskUserQuestion: an agent calling AskUserQuestion is about to
# BLOCK on an interactive question form. The tool payload carries the question +
# the exact options, so detect it HERE (a question is a blocked turn, not a Stop
# — the Stop hook never fires for it, which is why a question used to hang
# silently). Notify the Boss with the question + numbered options + how to
# answer, so the Boss can unblock the agent remotely with `mp answer`. ---
if [ "$EVENT" = "PreToolUse" ]; then
  TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
  [ "$TOOL" != "AskUserQuestion" ] && exit 0

  # Render each question with NUMBERED options — the numbers are exactly what
  # `mp answer <agent> <N>` selects (option N of the first/only question).
  QBLOCK=$(echo "$INPUT" | jq -r '
    [ .tool_input.questions[]?
      | "Q: " + (.question // .header // "(question)")
        + "\n   Options: "
        + ([ (.options // [])
             | to_entries[]
             | "[\(.key + 1)] " + (.value.label // (.value | tostring)) ] | join("   ")) ]
    | join("\n")' 2>/dev/null || echo "")
  [ -z "$QBLOCK" ] && QBLOCK="(could not parse question payload)"

  # Record a blocked-state status file so peek / the HUD show "waiting on a
  # question" instead of looking idle.
  mkdir -p "$STATUS_DIR"
  jq -n --arg agent "$TAB_PART" --arg session "mc-$SESS_PART" --arg ts "$TS" \
        --arg session_id "$SID" --arg summary "[QUESTION] $QBLOCK" \
        --arg agent_id "$AGENT_ID" --arg boss_id "${BOSS_ID:-}" \
    '{agent:$agent, session:$session, status:"blocked", timestamp:$ts, session_id:$session_id, summary:$summary, agent_id:$agent_id, boss_id:$boss_id}' \
    > "$STATUS_DIR/$TAB_PART.json" 2>/dev/null || true

  [ -z "${BOSS_ID:-}" ] && exit 0   # no boss to notify

  NOTIF="[AGENT QUESTION] $AGENT_ID is BLOCKED on a question — answer to unblock:
$QBLOCK
Reply with:  mp answer $AGENT_ID <option-number | free text>"
  BOSS_HOST="${BOSS_ID%%/*}"
  IDEM=$(idem_key "question" "$SID" "$AGENT_ID" "$QBLOCK")
  PAYLOAD=$(jq -n --arg ta "$BOSS_ID" --arg th "$BOSS_HOST" --arg msg "$NOTIF" --arg idem "$IDEM" \
    '{action:"send", target_agent:$ta, target_host:$th, idempotency_key:$idem, payload:{message:$msg}}')
  curl -fsS --max-time 3 -X POST "$QUEUE_URL/task/submit" \
    -H "Content-Type: application/json" -H "X-Queue-Secret: $QUEUE_SECRET" \
    -d "$PAYLOAD" >/dev/null 2>&1 || true
  exit 0
fi

if [ "$EVENT" != "Stop" ]; then
  # SessionStart / SessionEnd: just log, no notification.
  exit 0
fi

# --- Stop event handling ---

# Truncate summary to 1000 chars, single-line. 200 was too tight — Boss
# onboarding summaries got cut off mid-word at "autonomo", barely failing
# the doctrine-keyword check in Verify.
SUMMARY=$(echo "$LAST_MSG" | tr '\n' ' ' | cut -c1-1000)

# Write status file
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
IDEM=$(idem_key "stop" "$SID" "$AGENT_ID" "$SUMMARY")
PAYLOAD=$(jq -n \
  --arg target_agent "$BOSS_ID" \
  --arg target_host "$BOSS_HOST" \
  --arg msg "$NOTIF" \
  --arg idem "$IDEM" \
  '{action: "send", target_agent: $target_agent, target_host: $target_host, idempotency_key: $idem, payload: {message: $msg}}')

curl -fsS -X POST "$QUEUE_URL/task/submit" \
  -H "Content-Type: application/json" \
  -H "X-Queue-Secret: $QUEUE_SECRET" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/emit-event"

# --- codex-notify: Codex turn-end -> the SAME Stop-hook contract as emit-event.
# Claude agents emit turn-end via the `Stop` hook above (JSON on stdin). Codex
# CLI has NO Stop hook; instead it fires its `notify` program on turn completion
# with the payload as argv[1] and type "agent-turn-complete". The codex exec
# branch in queue-client.py points codex at THIS script via `-c notify=[...]`,
# so a codex agent's turn-end posts a byte-identical "[AGENT NOTIFICATION] ...
# finished: ..." to the Boss. No queue-server / protocol / Boss-doctrine change.
cat > "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify" <<'EOF'
#!/bin/bash
# codex-notify — Codex turn-end -> mypeople Stop-hook contract.
# Codex passes the notification JSON as argv[1] (NOT stdin, unlike Claude hooks)
# and the keys are HYPHENATED ("last-assistant-message", "thread-id"). This is
# the Codex-side equivalent of emit-event's Stop branch: same status file, same
# /task/submit `send` payload, same idempotency scheme -> the Boss is notified
# identically regardless of backend. Gating + identity come from the SAME env
# vars mypeople exports at spawn: AGENT_ID, BOSS_ID, QUEUE_URL, QUEUE_SECRET,
# INSTALL_DIR.

set -e
[ -z "${AGENT_ID:-}" ] && exit 0   # not managed by mypeople

INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/run"
LOG="$INSTALL_DIR/run/hook-events.log"

INPUT="${1:-}"
[ -z "$INPUT" ] && exit 0

# Only act on turn completion; ignore any other notify types.
NTYPE=$(echo "$INPUT" | jq -r '.type // ""' 2>/dev/null || echo "")
[ "$NTYPE" != "agent-turn-complete" ] && exit 0

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LAST_MSG=$(echo "$INPUT" | jq -r '.["last-assistant-message"] // ""' 2>/dev/null || echo "")
THREAD_ID=$(echo "$INPUT" | jq -r '.["thread-id"] // ""' 2>/dev/null || echo "")

# Idempotency key (same scheme as emit-event) so the queue-server dedups a
# double-fired/retried notify inside its window. thread-id is Codex's session analog.
idem_key() {
  local s="$*"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$s" | sha256sum | cut -c1-32
  else
    printf '%s' "$s" | shasum -a 256 | cut -c1-32
  fi
}

echo "{\"ts\":\"$TS\",\"event\":\"agent-turn-complete\",\"agent_id\":\"$AGENT_ID\",\"thread_id\":\"$THREAD_ID\",\"backend\":\"codex\"}" >> "$LOG"

# Parse session+tab from AGENT_ID = host/session:tab (identical to emit-event).
HOST_PART="${AGENT_ID%%/*}"
REST="${AGENT_ID#*/}"
SESS_PART="${REST%%:*}"
TAB_PART="${REST#*:}"
STATUS_DIR="$INSTALL_DIR/status/mc-$SESS_PART"

# UTF-8-safe truncation: codex replies often contain multi-byte chars; `head -c`
# can split a codepoint and corrupt the JSON, so use a codepoint-safe Python slice.
SUMMARY=$(printf '%s' "$LAST_MSG" | tr '\n' ' ' | python3 -c "import sys; print(sys.stdin.read()[:1000], end='')" 2>/dev/null || printf '%s' "$LAST_MSG" | tr '\n' ' ' | cut -c1-1000)

# Write status file — SAME shape/location the /agents HUD reads.
mkdir -p "$STATUS_DIR"
jq -n \
  --arg agent "$TAB_PART" \
  --arg session "mc-$SESS_PART" \
  --arg ts "$TS" \
  --arg session_id "$THREAD_ID" \
  --arg summary "$SUMMARY" \
  --arg agent_id "$AGENT_ID" \
  --arg boss_id "${BOSS_ID:-}" \
  '{agent: $agent, session: $session, status: "idle", timestamp: $ts, session_id: $session_id, summary: $summary, agent_id: $agent_id, boss_id: $boss_id}' \
  > "$STATUS_DIR/$TAB_PART.json"

# If no boss, the status file is enough.
[ -z "${BOSS_ID:-}" ] && exit 0

# POST the SAME send task that emit-event's Stop branch posts.
NOTIF="[AGENT NOTIFICATION] $AGENT_ID finished: $SUMMARY"
BOSS_HOST="${BOSS_ID%%/*}"
IDEM=$(idem_key "stop" "$THREAD_ID" "$AGENT_ID" "$SUMMARY")
PAYLOAD=$(jq -n \
  --arg target_agent "$BOSS_ID" \
  --arg target_host "$BOSS_HOST" \
  --arg msg "$NOTIF" \
  --arg idem "$IDEM" \
  '{action: "send", target_agent: $target_agent, target_host: $target_host, idempotency_key: $idem, payload: {message: $msg}}')

curl -fsS -X POST "$QUEUE_URL/task/submit" \
  -H "Content-Type: application/json" \
  -H "X-Queue-Secret: $QUEUE_SECRET" \
  -d "$PAYLOAD" >/dev/null 2>&1 || true

exit 0
EOF
chmod +x "$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"
```

### 7.5. Write the HUD dashboard HTML

**Why**: queue-server's `/dashboard` route serves this file with `__INJECT_SECRET__` replaced by the live `QUEUE_SECRET`. The page then polls `/agents` + `/clients` every 3s and renders rows. Each row has a "attach" link to ttyd with the correct `mc-<sess>:<tab>` target.

```bash
# [self-contained only] — the HUD is served by the upstream queue-server in JOIN-mode.
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  echo "[JOIN] skipping local HUD dashboard (served by upstream $UPSTREAM_QUEUE_URL)"
else
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
fi
```

### 7.6. Codex backend support (optional — for `--backend codex` agents)

**Why**: `mp spawn ... --backend codex` launches an OpenAI Codex CLI agent instead of Claude. The wiring needed for this is ALREADY in the artifacts written above — nothing extra is required at install time:

- **Turn-end → Boss notification**: the queue-client's codex exec branch launches codex with `-c notify=["bash","$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"]`, so notify is wired **per-spawn** — no global `~/.codex/config.toml` edit, and no risk of clobbering an existing `notify` the host already uses. `codex-notify` (written in Step 7) maps Codex's `agent-turn-complete` to the same `[AGENT NOTIFICATION] … finished: …` the Claude Stop hook posts.
- **Autonomy**: codex is launched with `--dangerously-bypass-approvals-and-sandbox` (the analog of Claude's `--dangerously-skip-permissions`).
- **Startup gates**: a fresh codex shows an "Update available" prompt and a directory-trust prompt before its composer. The codex readiness probe in `execute_spawn` **auto-dismisses both** (Skip / Yes) and waits up to 60s for the composer footer — so spawns don't hang on a gate even with no pre-seeded config.
- **TUI markers**: spawn/peek/send key off the per-backend `MARKERS` table (Codex composer glyph `›` U+203A, busy `esc to interrupt`, footer `<model> · <cwd>`). The Claude path is byte-identical (`markers_for("claude")` equals the original hardcoded strings; unknown backends fall back to claude).

**The one external prerequisite (NOT installed by this seed)**: the `codex` CLI must be present on PATH **and logged in** before a `--backend codex` agent can complete a turn. This seed does not install or authenticate codex.

```bash
# Optional pre-flight: report codex availability/auth. Does NOT install or log in
# codex (that is a host-owner decision — ChatGPT re-login or an OpenAI API key).
if command -v codex >/dev/null 2>&1; then
  echo "[codex] CLI present: $(codex --version 2>/dev/null || echo '?')"
  # `login status` only checks token PRESENCE, not validity — a stale/rotated
  # ChatGPT refresh token still reports "Logged in" yet fails turns with 401
  # token_expired. Treat a real turn as the only proof of working auth.
  codex login status 2>&1 | sed 's/^/[codex] /' || true
  echo "[codex] NOTE: --backend codex needs a VALID login. If turns 401, re-auth with"
  echo "[codex]   'codex login' (ChatGPT, interactive)  OR  'printenv OPENAI_API_KEY | codex login --with-api-key'."
else
  echo "[codex] CLI not installed — --backend claude works; --backend codex unavailable until 'codex' is installed + logged in."
fi
```

> **Optional global config (only if you prefer it over per-spawn `-c notify`)**: you may instead set `notify = ["bash","$INSTALL_DIR/plugins/tmux-boss-hooks/hooks/codex-notify"]` in `~/.codex/config.toml`. `codex-notify` is gated on `$AGENT_ID`, so it is a harmless no-op for non-mypeople codex sessions. Do this only if the host has no other `notify` consumer to avoid clobbering it. The per-spawn wiring above is the default and needs no such edit.

### 8. Write `queue.env`

```bash
QUEUE_PORT="${QUEUE_PORT:-9900}"
HOST_ID="${HOST_ID:-$(hostname -s)}"
if [ -n "${UPSTREAM_QUEUE_URL:-}" ]; then
  # [JOIN] point QUEUE_URL at the upstream; reuse the upstream secret VERBATIM
  # (never auto-generate in JOIN-mode — a secret mismatch means every request
  # is 401). The secret is written only into this 0600 file, never echoed.
  if [ -z "${UPSTREAM_QUEUE_SECRET:-}" ]; then echo "BLOCKED_REASON=upstream_secret_not_set"; exit 1; fi
  QUEUE_URL_VAL="${UPSTREAM_QUEUE_URL%/}"
  SECRET="${UPSTREAM_QUEUE_SECRET}"
  TS_LINE=""
else
  # [self-contained] local central node; reuse existing local secret or auto-gen.
  if [ -s "$HOME/.config/mypeople/queue.env" ] && grep -q '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env"; then
    SECRET=$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | head -1 | cut -d= -f2-)
  else
    SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  fi
  QUEUE_URL_VAL="http://127.0.0.1:${QUEUE_PORT}"
  TS_HOSTNAME="${TS_HOSTNAME:-mypeople-$(hostname -s)}"
  TS_LINE="TS_HOSTNAME=${TS_HOSTNAME}"
fi
cat > "$HOME/.config/mypeople/queue.env" <<EOF
QUEUE_URL=${QUEUE_URL_VAL}
QUEUE_SECRET=${SECRET}
QUEUE_PORT=${QUEUE_PORT}
QUEUE_HEARTBEAT=30
QUEUE_POLL_INTERVAL=1.0
HOST_ID=${HOST_ID}
INSTALL_DIR=${INSTALL_DIR:-$HOME/mypeople}
TTYD_PORT=${TTYD_PORT:-7681}
${TS_LINE}
# UTF-8 locale is REQUIRED. Hosts that default to POSIX (many Linux
# containers, some bare-metal Linux installs) cause tmux to collapse
# multi-byte UTF-8 chars (every glyph claude TUI uses — ●, ⏺, ✻, ⏵, ⎿,
# ❯, box-drawing — gets stripped to an ASCII underscore in tmux's internal buffer
# and that's what reaches the browser via ttyd). macOS defaults to
# UTF-8 already; setting these explicitly is harmless and makes the
# behavior portable.
LANG=C.UTF-8
LC_ALL=C.UTF-8
EOF
chmod 600 "$HOME/.config/mypeople/queue.env"
```

### 8.5. Bring this host onto the tailnet

**[JOIN] first**: a JOIN node does NOT claim its own `$TS_HOSTNAME` identity — it only needs to *reach* the upstream. Test `curl -fsS "$UPSTREAM_QUEUE_URL/health"`. If it returns 200, this host is already on the right network (already on the tailnet, or the upstream is LAN-reachable) → **SKIP the rest of this Step entirely** (`TS_AUTHKEY`/`TS_HOSTNAME` not needed). If it does NOT return 200 and `TS_AUTHKEY` is set, run `tailscale up` as below (hostname `$HOST_ID` is fine) to join the tailnet, then re-test `curl "$UPSTREAM_QUEUE_URL/health"`. If still unreachable, stop with `BLOCKED_REASON=upstream_unreachable`. The rest of this Step ([self-contained]) does not apply to JOIN nodes.

**[self-contained] Intent**: this host gets its own tailnet identity (`$TS_HOSTNAME`) and a tailscale IP. After this Step, `http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard` will be reachable from any other tailnet node.

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

`$TS_AUTHKEY` is required **in self-contained mode**. If unset there, stop with `BLOCKED_REASON=ts_authkey_not_set`. (In JOIN-mode it's only consulted via the **[JOIN] first** path above.)

**Verify by intent**: `tailscale status --json` reports `.Self.Online == true` and `.Self.HostName == $TS_HOSTNAME`; `tailscale ip -4` returns a `100.x.x.x` address. Stop with `BLOCKED_REASON=tailscale_no_ipv4_assigned` if not.

### 9. Start daemons

```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a

# Determine the ttyd port and the tailnet-reachable attach URL BEFORE starting
# the queue-client, so the client advertises a WORKING attach_base in its very
# first heartbeat. The HUD builds each agent's attach link from the OWNING
# client's attach_base; without this a cross-host/JOIN node's link falls back to
# the HUD host's own localhost ttyd → dead link from any other machine.
TTYD_PORT="${TTYD_PORT:-7681}"
# A FOREIGN ttyd / web-terminal may already hold this port (common on shared
# hosts and multi-node JOIN setups). Binding a busy port makes ttyd exit
# immediately, and a port-only health check would be FOOLED by the foreign
# listener answering on it. Pick the first FREE port at/above the requested one.
port_busy() { python3 -c 'import socket,sys; s=socket.socket(); r=s.connect_ex(("127.0.0.1",int(sys.argv[1]))); s.close(); sys.exit(0 if r==0 else 1)' "$1"; }
while port_busy "$TTYD_PORT"; do
  echo "ttyd: port $TTYD_PORT already in use (foreign listener) — trying $((TTYD_PORT+1))"
  TTYD_PORT=$((TTYD_PORT+1))
done
if grep -q '^TTYD_PORT=' "$HOME/.config/mypeople/queue.env"; then
  sed -i.bak "s/^TTYD_PORT=.*/TTYD_PORT=${TTYD_PORT}/" "$HOME/.config/mypeople/queue.env" && rm -f "$HOME/.config/mypeople/queue.env.bak"
else
  echo "TTYD_PORT=${TTYD_PORT}" >> "$HOME/.config/mypeople/queue.env"
fi
# Advertise the node's TAILNET-reachable ttyd so the HUD emits an attach link
# that works from any tailnet browser (not localhost). If the node isn't on a
# tailnet, leave it empty (HUD falls back to the HUD-host localhost — fine for a
# single self-contained node).
TS_IP4="$(tailscale ip -4 2>/dev/null | head -1)"
# Prefer the tailnet IP (reachable from any tailnet browser). If this node is NOT
# on a tailnet (e.g. a JOIN node reaching the upstream over plain LAN — proven on
# a Raspberry Pi joined by LAN, no tailscale up), fall back to the node's LAN IP so
# the HUD still emits a WORKING attach link for browsers on the same LAN. Only an
# empty attach_base (the old behavior) makes the HUD fall back to the HUD-host's own
# localhost → a dead link for every agent that lives on a different host.
ATTACH_IP4="$TS_IP4"
if [ -z "$ATTACH_IP4" ]; then
  ATTACH_IP4="$( (hostname -I 2>/dev/null | awk '{print $1}') || true )"
  [ -z "$ATTACH_IP4" ] && ATTACH_IP4="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [ -n "$ATTACH_IP4" ]; then
  TTYD_PUBLIC_URL="http://${ATTACH_IP4}:${TTYD_PORT}"
  if grep -q '^TTYD_PUBLIC_URL=' "$HOME/.config/mypeople/queue.env"; then
    sed -i.bak "s#^TTYD_PUBLIC_URL=.*#TTYD_PUBLIC_URL=${TTYD_PUBLIC_URL}#" "$HOME/.config/mypeople/queue.env" && rm -f "$HOME/.config/mypeople/queue.env.bak"
  else
    echo "TTYD_PUBLIC_URL=${TTYD_PUBLIC_URL}" >> "$HOME/.config/mypeople/queue.env"
  fi
  echo "ttyd attach advertised at $TTYD_PUBLIC_URL${TS_IP4:+ (tailnet)}${TS_IP4:- (LAN fallback — no tailnet on this node)}"
fi
# Re-source so the queue-client inherits the final TTYD_PORT + TTYD_PUBLIC_URL.
set -a; . "$HOME/.config/mypeople/queue.env"; set +a

if [ -z "${UPSTREAM_QUEUE_URL:-}" ]; then
  # [self-contained] start the local queue-server and wait for its health.
  nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" > "$INSTALL_DIR/run/queue-server.log" 2>&1 &
  echo $! > "$INSTALL_DIR/run/queue-server.pid"
  for i in $(seq 1 25); do
    curl -fsS "http://127.0.0.1:${QUEUE_PORT}/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
else
  # [JOIN] no local queue-server — confirm the UPSTREAM is reachable AND accepts
  # our secret BEFORE starting the client (fail fast with a clear reason).
  curl -fsS "${QUEUE_URL}/health" | grep -q '"status"' || { echo "BLOCKED_REASON=upstream_unreachable"; exit 1; }
  curl -fsS -H "X-Queue-Secret: ${QUEUE_SECRET}" "${QUEUE_URL}/clients" >/dev/null 2>&1 || { echo "BLOCKED_REASON=upstream_secret_rejected"; exit 1; }
fi
# Both modes: queue-client heartbeats to QUEUE_URL (local in self-contained,
# upstream in JOIN), registering this host as a client.
nohup python3 -u "$INSTALL_DIR/bin/queue-client.py" > "$INSTALL_DIR/run/queue-client.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-client.pid"

# ttyd: per-tab browser-attach (port already chosen + advertised above).
#   -W = writable so the browser user can type.
#   -a = allow URL args (?arg=-t&arg=mc-X:Y) — MANDATORY for per-tab attach;
#        without it the link is ignored and the user lands in a default session.
#   -t fontFamily/fontSize = xterm.js glyph support (❯ ● ✻ …).
#   -t disableLeaveAlert=true = kill the browser tab-close prompt (the tmux
#        session persists across detach, so dropping the ttyd client loses no work).
nohup ttyd -W -a -p "$TTYD_PORT" \
  -t 'fontFamily=Menlo, Monaco, "Cascadia Mono", "Fira Code", "Courier New", monospace' \
  -t 'fontSize=13' \
  -t 'disableLeaveAlert=true' \
  tmux attach > "$INSTALL_DIR/run/ttyd.log" 2>&1 &
TTYD_PID=$!
echo "$TTYD_PID" > "$INSTALL_DIR/run/ttyd.pid"
for i in $(seq 1 25); do
  curl -fsS -o /dev/null "http://127.0.0.1:${TTYD_PORT}/" && break
  sleep 0.2
done
# Assert OUR ttyd actually bound (the PID we launched is still alive) — not a
# foreign listener masquerading on the port. Catches the silent bind failure.
sleep 0.3
ps -p "$TTYD_PID" >/dev/null 2>&1 || { echo "BLOCKED_REASON=ttyd_failed_to_bind (port ${TTYD_PORT}); check $INSTALL_DIR/run/ttyd.log"; exit 1; }
```

### 9.5. Install + start the TODO app (Priorities board) [self-contained]

The CEO's done-condition: a one-shot install brings up a COMPLETE self-contained
mypeople = comms + HUD + **TODO app**. The board (todo-server.py + todos.html) is
inlined here byte-exact (base64, identical bytes to `todo.seed.md`). It LISTENS on
its own port **9933** (the `todo-server.py` listen port env is the confusingly-named
`QUEUE_PORT`; do NOT give it 9900 or it collides with the queue-server) and TALKS to
the queue at `QUEUE_URL` (9900) using the same `QUEUE_SECRET`, so card comments route
to the Boss via `mp send` and `/todo/attach` resolves ttyd `attach_base`. The
WhatsApp/tailscale-serve digest (slice e) is intentionally NOT started here — it
needs a Hermes last-hop and must never break the clean one-shot; it is opt-in.

```bash
set -a; . "$HOME/.config/mypeople/queue.env"; set +a   # QUEUE_SECRET, QUEUE_PORT(9900), INSTALL_DIR
export INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
export TODO_DIR="$INSTALL_DIR/todos"
mkdir -p "$INSTALL_DIR/bin" "$TODO_DIR/proofs"
command -v python3 >/dev/null || { echo "BLOCKED_REASON=todo_needs_python3"; exit 1; }

# --- byte-exact app files (VERBATIM from todo.seed.md Step 1: base64 writes) ---
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvIHNlcnZlciDigJQgdGhlIENFTydzIHByaW9yaXR5IGJvYXJkIGFzIHRoZSBCb3NzJ3Mgc291cmNlIG9mIHRydXRoLgoKU2xpY2U6IEFQSSArIHNoYXJlZCBzdG9yZSArIFBJTkcgU1RBVEUgTUFDSElORS4gRGVzaWduZWQgdG8gYmUgaW5saW5lZCAoaGVyZWRvYykKaW50byBzZWVkcy90b2RvLnNlZWQubWQgYW5kIHRvIHJ1biBlaXRoZXI6CiAgLSBzdGFuZGFsb25lIGluIGEgY2xlYW4gY29udGFpbmVyIChib3NzIHBpbmdzIGdvIHRvIGEgZmlsZSBzaW5rOyBUT0RPX1RFU1RfU0lOSz0xKSwgb3IKICAtIG9uIHRvcCBvZiBhIGxpdmUgbXlwZW9wbGUgcnVudGltZSAoYm9zcyBwaW5ncyBnbyB0aHJvdWdoIGBtcCBzZW5kIG1haW46Qm9zc2ApLgoKU3RvcmUgOiAkVE9ET19ESVIvYm9hcmQudjIuanNvbiAgIHByb29mczogJFRPRE9fRElSL3Byb29mcy88dGFza19pZD4vCkVudiAgIDogUVVFVUVfUE9SVCg5OTAwKSBRVUVVRV9TRUNSRVQoJycpIFRPRE9fRElSKH4vbXlwZW9wbGUvdG9kb3MpCiAgICAgICAgUElOR19DUk9OX1NFQyg2MCkgSURMRV9HUkFDRV9TRUMoNjApIFRPRE9fSFRNTCg8ZGlyPi90b2Rvcy5odG1sKQogICAgICAgIFRPRE9fVEVTVF9TSU5LKDApICBCT1NTX0FHRU5UKG1haW46Qm9zcykgIFFVRVVFX1VSTChodHRwOi8vMTI3LjAuMC4xOjk5MDApCiAgICAgICAgKFFVRVVFX1VSTCA9IHRoZSBteXBlb3BsZSBxdWV1ZS1zZXJ2ZXIsIHF1ZXJpZWQgZm9yIHR0eWQgYXR0YWNoX2Jhc2UgaW4gL3RvZG8vYXR0YWNoKQogICAgICAgIFdoYXRzQXBwIGRyYWluIChzbGljZSBlKTogV0FfRFJBSU4oMSkgV0FfQ0hBVF9KSUQoQ0VPIEpJRCkgV0FfU0VORF9DTUQoSGVybWVzIGxhc3QgaG9wLAogICAgICAgIHJlYWRzIHtjaGF0SWQsbWVzc2FnZX0gb24gc3RkaW4pIFdBX0JPQVJEX1VSTCgnJykgV0FfV0FUQ0hET0dfU0VDKDE4MCkgV0FfRFJBSU5fU0VDKDEwKSBXQV9SRVBJTkdfU0VDKDkwMCkKIiIiCmltcG9ydCBodHRwLnNlcnZlciwganNvbiwgb3MsIHRocmVhZGluZywgdGltZSwgdXVpZCwgYmFzZTY0LCBzdWJwcm9jZXNzLCBzaHV0aWwsIGRhdGV0aW1lLCB1cmxsaWIucmVxdWVzdApmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHVybHBhcnNlLCBwYXJzZV9xcwoKUE9SVCAgICAgICAgPSBpbnQob3MuZW52aXJvbi5nZXQoIlFVRVVFX1BPUlQiLCAiOTkwMCIpKQpTRUNSRVQgICAgICA9IG9zLmVudmlyb24uZ2V0KCJRVUVVRV9TRUNSRVQiLCAiIikKVE9ET19ESVIgICAgPSBQYXRoKG9zLmVudmlyb24uZ2V0KCJUT0RPX0RJUiIsIHN0cihQYXRoKF9fZmlsZV9fKS5yZXNvbHZlKCkucGFyZW50IC8gImRhdGEiKSkpICAjIGR1cmFibGUsIGJlc2lkZSB0aGUgc2VydmVyIChOT1QgL3RtcCkKUFJPT0ZfRElSICAgPSBUT0RPX0RJUiAvICJwcm9vZnMiCkJPQVJEX1BBVEggID0gVE9ET19ESVIgLyAiYm9hcmQudjIuanNvbiIKSU5CT1hfTE9HICAgPSBUT0RPX0RJUiAvICJib3NzLWluYm94LmxvZyIKUElOR19DUk9OICAgPSBmbG9hdChvcy5lbnZpcm9uLmdldCgiUElOR19DUk9OX1NFQyIsICIxMjAiKSkgICAjIHVuYXNzaWduZWQtY2FyZCBjcm9uIChDRU86IDIgbWluKQpJRExFX0dSQUNFICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJJRExFX0dSQUNFX1NFQyIsICI2MCIpKSAgICAjIGFzc2lnbmVkIGlkbGUtcG9zdC1zdG9wLWhvb2sgKDEgbWluKQpJRExFX1NUQUxMICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJJRExFX1NUQUxMX1NFQyIsICIxODAiKSkgICAjIGFzc2lnbmVkLWJ1dC1pZGxlIFdBVENIRE9HIHRocmVzaG9sZCAoMyBtaW4pClNUQUxMX1JFUElORz0gZmxvYXQob3MuZW52aXJvbi5nZXQoIlNUQUxMX1JFUElOR19TRUMiLCAiMzAwIikpICMgcmUtcGluZyB0aHJvdHRsZSBwZXIgc3RhbGxlZCBjYXJkCldBVENIRE9HICAgID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIldBVENIRE9HX1NFQyIsICI2MCIpKSAgICAgICMgd2F0Y2hkb2cgc2NhbiBpbnRlcnZhbApTVEFUVVNfRElSICA9IFBhdGgob3MuZW52aXJvbi5nZXQoIlNUQVRVU19ESVIiLCBzdHIoUGF0aC5ob21lKCkgLyAibXlwZW9wbGUiIC8gInN0YXR1cyIpKSkKUFJPSkVDVFNfRElSPSBQYXRoKG9zLmVudmlyb24uZ2V0KCJQUk9KRUNUU19ESVIiLCBzdHIoUGF0aC5ob21lKCkgLyAiLmNsYXVkZSIgLyAicHJvamVjdHMiKSkpCkJVU1lfQ1BVICAgID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIkJVU1lfQ1BVX1BDVCIsICIyMCIpKSAgICAgICMgd2F0Y2hkb2c6IHByb2Nlc3MtdHJlZSBDUFUlIGFib3ZlIHRoaXMgPT0gYnVzeSAobG9uZyBqb2IpCkJVU1lfTkFNRVMgID0gc2V0KG4uc3RyaXAoKSBmb3IgbiBpbiBvcy5lbnZpcm9uLmdldCgiQlVTWV9OQU1FUyIsCiAgICAiZmZtcGVnLGRvY2tlcixidWlsZGtpdGQsY29udGFpbmVyZCxyc3luYyxzY3Asc3NoLHNmdHAsd2dldCxjdXJsLGdpdCxtYWtlLGNtYWtlLG5pbmphLGNhcmdvLHJ1c3RjLCIKICAgICJnY2MsY2MsY2xhbmcsbGQsY29sbGVjdDIsdHNjLHdlYnBhY2ssdml0ZSxlc2J1aWxkLHJvbGx1cCxuZXh0LHZlcmNlbCxidW4sc294LHdoaXNwZXIiKS5zcGxpdCgiLCIpIGlmIG4uc3RyaXAoKSkKVEVTVF9TSU5LICAgPSBvcy5lbnZpcm9uLmdldCgiVE9ET19URVNUX1NJTksiLCAiMCIpID09ICIxIgpCT1NTX0FHRU5UICA9IG9zLmVudmlyb24uZ2V0KCJCT1NTX0FHRU5UIiwgIm1haW46Qm9zcyIpCkhUTUxfUEFUSCAgID0gUGF0aChvcy5lbnZpcm9uLmdldCgiVE9ET19IVE1MIiwgc3RyKFBhdGgoX19maWxlX18pLnJlc29sdmUoKS5wYXJlbnQgLyAidG9kb3MuaHRtbCIpKSkKUVVFVUVfVVJMICAgPSBvcy5lbnZpcm9uLmdldCgiUVVFVUVfVVJMIiwgImh0dHA6Ly8xMjcuMC4wLjE6OTkwMCIpLnJzdHJpcCgiLyIpICAjIHRoZSBteXBlb3BsZSBxdWV1ZS1zZXJ2ZXIgKGZvciAvY2xpZW50cyBhdHRhY2hfYmFzZTsgc2xpY2UgYykKIyDilIDilIAgV2hhdHNBcHAgbGFzdC1ob3AgZHJhaW4gKyBDRU8td2F0Y2hkb2cgKHNsaWNlIGUpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAojIEEgJ3doYXRzYXBwJyBxdWV1ZSBwYXJ0aWNpcGFudC4gVGhlIENFTy13YXRjaGRvZyAoZXZlcnkgV0FfV0FUQ0hET0dfU0VDID0gNSBtaW4pIHNlbmRzIHRoZSBDRU8KIyBPTkUgY29uc29saWRhdGVkIERJR0VTVCBsaXN0aW5nIGV2ZXJ5IGNhcmQgYmxvY2tlZCBvbiBoaW0g4oCUIGdyb3VwZWQgcmV2aWV3LXBlbmRpbmcgLwojIGJyYWluc3Rvcm0tcGVuZGluZywgZWFjaCBsaW5lID0gY2FyZCB0aXRsZSArIGEgdGFwcGFibGUgZGVlcC1saW5rIHN0cmFpZ2h0IHRvIHRoYXQgY2FyZCDigJQgdmlhIHRoZQojIExBU1QgSE9QIChjb250YWluZXJpemVkIEhlcm1lcyAvc2VuZCB0byBoaXMgcGVyc29uYWwgSklEKS4gSXQgZmlyZXMgb25seSB3aGlsZSDiiaUxIGNhcmQgaXMgYmxvY2tlZCwKIyByZXBlYXRzIGV2ZXJ5IDUgbWluLCB1cGRhdGVzIGFzIGNhcmRzIGNsZWFyLCBhbmQgc3RvcHMgd2hlbiBub25lIHJlbWFpbi4gVGhlIHNlbmQgY29tbWFuZCBpcwojIGNvbmZpZ3VyYWJsZSBzbyB0aGUgc2VlZCB3b3JrcyB3aGVyZXZlciBIZXJtZXMgaXMgcmVhY2hhYmxlOyBXQV9EUkFJTj0wIGRpc2FibGVzIHRoZSBsYXN0IGhvcC4KV0FfT1VUQk9YICAgPSBUT0RPX0RJUiAvICJ3YS1vdXRib3guanNvbiIKV0FfQ0hBVF9KSUQgPSBvcy5lbnZpcm9uLmdldCgiV0FfQ0hBVF9KSUQiLCAiIikuc3RyaXAoKSAgICMgQ0VPIFdoYXRzQXBwIEpJRCDigJQgUkVRVUlSRUQgZm9yIHRoZSBkcmFpbjsgc2V0IHZpYSBlbnYvcGxpc3QuIE5FVkVSIGhhcmRjb2RlIGEgcGVyc29uYWwgbnVtYmVyIGluIHRoZSBwdWJsaXNoZWQgc2VlZCAocHJpdmFjeSkuIGUuZy4gPGRpZ2l0cz5Acy53aGF0c2FwcC5uZXQKV0FfRFJBSU5fT04gPSAob3MuZW52aXJvbi5nZXQoIldBX0RSQUlOIiwgIjEiKSA9PSAiMSIpIGFuZCBib29sKFdBX0NIQVRfSklEKSAgICMgbm8gdGFyZ2V0IEpJRCAtPiBkcmFpbiBzdGF5cyBvZmYKV0FfU0VORF9DTUQgPSBvcy5lbnZpcm9uLmdldCgiV0FfU0VORF9DTUQiLCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyByZWFkcyB7Y2hhdElkLG1lc3NhZ2V9IEpTT04gb24gc3RkaW4KICAgICdkb2NrZXIgZXhlYyAtaSBoZXJtZXMtd2EgY3VybCAtcyAtSCAiSG9zdDogMTI3LjAuMC4xIiAtSCAiQ29udGVudC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIiAnCiAgICAnLVggUE9TVCBodHRwOi8vMTI3LjAuMC4xOjMwMDAvc2VuZCAtZCBALScpCldBX0JPQVJEX1VSTD0gb3MuZW52aXJvbi5nZXQoIldBX0JPQVJEX1VSTCIsICIiKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBib2FyZCBwYWdlIFVSTDsgZWFjaCBjYXJkIGxpbmUgbGlua3MgdG8gPFdBX0JPQVJEX1VSTD4jY2FyZC88aWQ+CldBX1dBVENIRE9HID0gZmxvYXQob3MuZW52aXJvbi5nZXQoIldBX1dBVENIRE9HX1NFQyIsICIzMDAiKSkgICAgICAgICAgICAgICAgIyBDRU8td2F0Y2hkb2c6IHNlbmQgdGhlIGRpZ2VzdCBldmVyeSA1IG1pbiB3aGlsZSDiiaUxIGNhcmQgaXMgYmxvY2tlZApXQV9EUkFJTl9TRUM9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJXQV9EUkFJTl9TRUMiLCAiMTAiKSkgICAgICAgICAgICAgICAgICAgICMgZHJhaW4gdGljawpXQV9SRVBJTkcgICA9IGZsb2F0KG9zLmVudmlyb24uZ2V0KCJXQV9SRVBJTkdfU0VDIiwgIjI3MCIpKSAgICAgICAgICAgICAgICAgIyBtaW4gaW50ZXJ2YWwgKHMpIGJldHdlZW4gZGlnZXN0cyDigJQganVzdCB1bmRlciB0aGUgNS1taW4gdGljayBzbyBlYWNoIHRpY2sgc2VuZHMsIGJ1dCBhIG11dGF0aW9uIG1pZC1pbnRlcnZhbCBjYW4ndCBhZGQgYW4gZXh0cmEgZGlnZXN0Cl93YV9sb2NrID0gdGhyZWFkaW5nLlJMb2NrKCkKClZBTElEX1NUQVRFUyA9IHsibmVlZHNfYnJhaW5zdG9ybSIsICJ3b3JraW5nIiwgInJldmlldyIsICJibG9ja2VkIiwgImRvbmUiLCAiY2FuY2VsbGVkIn0gICAjIENFTyBtb2RlbDogaW4tcHJvZ3Jlc3MgaXMgJ3dvcmtpbmcnOyAncmV2aWV3JyA9IGVuZ2luZWVyIGRvbmUgKyBCb3NzLXZlcmlmaWVkLCBhd2FpdGluZyBDRU8gc2lnbi1vZmYgKFJ1bGUgMjE6IG9ubHkgdGhlIENFTyBtYXJrcyBkb25lKTsgJ2NhbmNlbGxlZCcgPSB0ZXJtaW5hbCBzaWRlLWV4aXQgKENFTyBhYmFuZG9ucyB0aGUgdGFzayDigJQgYWxvbmdzaWRlICdkb25lJywgbmV2ZXIgd29ya2VkL3BpbmdlZCBhZ2FpbikKVEVSTUlOQUxfU1RBVEVTID0geyJkb25lIiwgImNhbmNlbGxlZCJ9ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyB0ZXJtaW5hbDogbm90IEFDVElWRSwgbmV2ZXIgZGlzcGF0Y2hlZC9waW5nZWQvaW4gdGhlIFdoYXRzQXBwIGRpZ2VzdApBQ1RJVkUgPSBsYW1iZGEgdDogdC5nZXQoIndvcmtUb0RvbmUiKSBhbmQgdC5nZXQoInN0YXRlIikgbm90IGluIFRFUk1JTkFMX1NUQVRFUwpfbG9jayA9IHRocmVhZGluZy5STG9jaygpCiMgcGVyLWFnZW50IGxhc3Qgc3RvcC1ob29rIHN0YXRlOiBhZ2VudF9pZCAtPiAiaWRsZSIgfCAid29ya2luZyIKX2hvb2tfc3RhdGUgPSB7fQoKZGVmIG5vdygpOiByZXR1cm4gaW50KHRpbWUudGltZSgpICogMTAwMCkKZGVmIHVpZCgpOiByZXR1cm4gdXVpZC51dWlkNCgpLmhleFs6MTJdCmRlZiBfYnVpbGRfc3RhbXAoKToKICAgICIiIkEgc3RhYmxlIGJ1aWxkIGlkID0gbXRpbWUgb2YgdGhlIHNlcnZlZCBIVE1MLiBDaGFuZ2VzIGV4YWN0bHkgb25jZSBwZXIgZGVwbG95LCBzbyBhbiBvcGVuCiAgICBib2FyZCByZWxvYWRzIGl0c2VsZiB3aGVuIGEgbmV3IHRvZG9zLmh0bWwgc2hpcHMgKG5vIG1hbnVhbCBoYXJkLXJlZnJlc2ggLyBzdGFsZS1KUyBidWdzKS4iIiIKICAgIHRyeTogcmV0dXJuIHN0cihpbnQoSFRNTF9QQVRILnN0YXQoKS5zdF9tdGltZSkpCiAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gIjAiCgpkZWYgX2RlZmF1bHRfYm9hcmQoKTogcmV0dXJuIHsidmVyc2lvbiI6ICJ2MiIsICJvcmRlciI6IFtdLCAidGFza3MiOiB7fX0KCmRlZiBsb2FkKCk6CiAgICB0cnk6CiAgICAgICAgYiA9IGpzb24ubG9hZHMoQk9BUkRfUEFUSC5yZWFkX3RleHQoKSkKICAgICAgICBpZiBub3QgaXNpbnN0YW5jZShiLCBkaWN0KSBvciBiLmdldCgidmVyc2lvbiIpICE9ICJ2MiI6IHJldHVybiBfZGVmYXVsdF9ib2FyZCgpCiAgICAgICAgYi5zZXRkZWZhdWx0KCJvcmRlciIsIFtdKTsgYi5zZXRkZWZhdWx0KCJ0YXNrcyIsIHt9KQogICAgICAgIGZvciB0IGluIGJbInRhc2tzIl0udmFsdWVzKCk6CiAgICAgICAgICAgIHQuc2V0ZGVmYXVsdCgiY29tbWVudHMiLCBbXSkgICAgICAgICAgICAgICAgICMgaXNzdWUtc3R5bGUgdGhyZWFkIChzbGljZSBiKQogICAgICAgICAgICB0LnNldGRlZmF1bHQoInF1ZXN0aW9ucyIsIFtdKSAgICAgICAgICAgICAgICAjIGJyYWluc3Rvcm0gZ2F0ZSAoc2xpY2UgZCkKICAgICAgICAgICAgdC5zZXRkZWZhdWx0KCJicmFpbnN0b3JtQXNrZWQiLCBGYWxzZSkKICAgICAgICByZXR1cm4gYgogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gX2RlZmF1bHRfYm9hcmQoKQoKZGVmIHNhdmUoYik6CiAgICBUT0RPX0RJUi5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICB0bXAgPSBCT0FSRF9QQVRILndpdGhfc3VmZml4KCIudG1wIikKICAgIHRtcC53cml0ZV90ZXh0KGpzb24uZHVtcHMoYiwgaW5kZW50PTIpKTsgdG1wLnJlcGxhY2UoQk9BUkRfUEFUSCkKCmRlZiBfaW5nZXN0X2ZpbGUodGlkLCBwaWQsIHB0eXBlLCBzcmNwYXRoKToKICAgICIiIkNvcHkgYSByZWZlcmVuY2VkIGxvY2FsIGltYWdlL3ZpZGVvIGludG8gdGhlIHNlcnZlZCBwcm9vZiBzdG9yZTsgcmV0dXJuIGl0cyBVUkwgb3IgTm9uZS4iIiIKICAgIHNyYyA9IHNyY3BhdGhbNzpdIGlmIHNyY3BhdGguc3RhcnRzd2l0aCgiZmlsZTovLyIpIGVsc2Ugc3JjcGF0aAogICAgaWYgbm90IG9zLnBhdGguaXNmaWxlKHNyYyk6IHJldHVybiBOb25lCiAgICBiYXNlID0gb3MucGF0aC5iYXNlbmFtZShzcmMpCiAgICBleHQgPSBiYXNlLnJzcGxpdCgiLiIsIDEpWy0xXS5sb3dlcigpIGlmICIuIiBpbiBiYXNlIGVsc2UgKCJwbmciIGlmIHB0eXBlID09ICJpbWFnZSIgZWxzZSAibXA0IikKICAgIFBEID0gUFJPT0ZfRElSIC8gdGlkOyBQRC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICBkc3QgPSBQRCAvIGYie3BpZH0ue2V4dH0iCiAgICB0cnk6CiAgICAgICAgaWYgbm90IGRzdC5leGlzdHMoKTogc2h1dGlsLmNvcHlmaWxlKHNyYywgZHN0KQogICAgICAgIHJldHVybiBmIi90b2RvL3Byb29mL3t0aWR9L3twaWR9LntleHR9IgogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXR1cm4gTm9uZQoKZGVmIG1pZ3JhdGVfcHJvb2ZzKGIpOgogICAgIiIiSW1hZ2UvdmlkZW8gcHJvb2ZzIHN0b3JlZCBhcyBhIGxvY2FsIHBhdGgvZmlsZTovLyAtPiBjb3B5IGludG8gdGhlIHN0b3JlICsgcmV3cml0ZSB0byBhIHNlcnZlZCBVUkwuIiIiCiAgICBjaGFuZ2VkID0gRmFsc2UKICAgIGZvciB0aWQsIHQgaW4gYi5nZXQoInRhc2tzIiwge30pLml0ZW1zKCk6CiAgICAgICAgZm9yIHByIGluIHQuZ2V0KCJwcm9vZnMiLCBbXSk6CiAgICAgICAgICAgIGlmIHByLmdldCgidHlwZSIpIGluICgiaW1hZ2UiLCAidmlkZW8iKToKICAgICAgICAgICAgICAgIHJlZiA9IHByLmdldCgicmVmIiwgIiIpCiAgICAgICAgICAgICAgICBpZiByZWYgYW5kIG5vdCByZWYuc3RhcnRzd2l0aCgiL3RvZG8vcHJvb2YvIik6CiAgICAgICAgICAgICAgICAgICAgdXJsID0gX2luZ2VzdF9maWxlKHRpZCwgcHJbImlkIl0sIHByWyJ0eXBlIl0sIHJlZikKICAgICAgICAgICAgICAgICAgICBpZiB1cmw6IHByWyJyZWYiXSA9IHVybDsgY2hhbmdlZCA9IFRydWUKICAgIGlmIGNoYW5nZWQ6IHNhdmUoYikKICAgIHJldHVybiBiCgpkZWYgbmV3X3Rhc2sodGV4dCk6CiAgICByZXR1cm4geyJpZCI6IHVpZCgpLCAidGV4dCI6IHRleHQgb3IgIiIsICJkb25lQ29uZGl0aW9uIjogIiIsICJicmFpbnN0b3JtIjogIiIsCiAgICAgICAgICAgICJ3b3JrVG9Eb25lIjogRmFsc2UsICJhc3NpZ25lZSI6IE5vbmUsICJzdGF0ZSI6ICJuZWVkc19icmFpbnN0b3JtIiwKICAgICAgICAgICAgInZlcmlmaWVkIjogRmFsc2UsICJsYXN0U3RhdHVzIjogIiIsICJwcm9vZnMiOiBbXSwgInN1YnMiOiBbXSwgImNvbW1lbnRzIjogW10sCiAgICAgICAgICAgICJxdWVzdGlvbnMiOiBbXSwgImJyYWluc3Rvcm1Bc2tlZCI6IEZhbHNlLCAidGVzdCI6IEZhbHNlLAogICAgICAgICAgICAicGFyZW50IjogTm9uZSwgImRlcGVuZHNPbiI6IFtdLCAiaGFyZEdhdGUiOiBGYWxzZSwgICAjIGlzc3VlICMzOiBwYXJlbnQvY2hpbGQgaGllcmFyY2h5ICsgJ2Jsb2NrZWQgYnknIGRlcHMgKyBvcHRpb25hbCBwZXItY2FyZCBoYXJkIGdhdGUgKE9GRiBieSBkZWZhdWx0KQogICAgICAgICAgICAicGluZ3NUb0Jvc3MiOiAwLCAiYXNzaWduZWRBdCI6IE5vbmUsICJsYXN0U3RvcFRzIjogTm9uZSwKICAgICAgICAgICAgImNyZWF0ZWQiOiBub3coKSwgInVwZGF0ZWQiOiBub3coKX0KCiMg4pSA4pSAIHN1YnRhc2tzICsgZGVwZW5kZW5jaWVzIChpc3N1ZSAjMykg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmRlZiBfY2hpbGRyZW4oYiwgdGlkKTogICAgICAgICAgICAgICAgICAgICAgIyByZWFsIGNoaWxkIGNhcmRzIChwYXJlbnQgPT0gdGlkKQogICAgcmV0dXJuIFt4IGZvciB4IGluIGJbInRhc2tzIl0udmFsdWVzKCkgaWYgeC5nZXQoInBhcmVudCIpID09IHRpZF0KZGVmIF9pbmNvbXBsZXRlX2NoaWxkcmVuKGIsIHRpZCk6CiAgICByZXR1cm4gW2MgZm9yIGMgaW4gX2NoaWxkcmVuKGIsIHRpZCkgaWYgYy5nZXQoInN0YXRlIikgbm90IGluIFRFUk1JTkFMX1NUQVRFU10KZGVmIF91bm1ldF9kZXBzKGIsIHQpOiAgICAgICAgICAgICAgICAgICAgICAgIyAnYmxvY2tlZCBieScgY2FyZHMgbm90IHlldCBkb25lL2NhbmNlbGxlZAogICAgb3V0ID0gW10KICAgIGZvciBkZXAgaW4gKHQuZ2V0KCJkZXBlbmRzT24iKSBvciBbXSk6CiAgICAgICAgZDIgPSBiWyJ0YXNrcyJdLmdldChkZXApCiAgICAgICAgaWYgZDIgYW5kIGQyLmdldCgic3RhdGUiKSBub3QgaW4gVEVSTUlOQUxfU1RBVEVTOiBvdXQuYXBwZW5kKGRlcCkKICAgIHJldHVybiBvdXQKZGVmIF9jcmVhdGVzX2N5Y2xlKGIsIHRpZCwgcGFyZW50X2lkKTogICAgICAgIyB3b3VsZCBzZXR0aW5nIHRpZC5wYXJlbnQ9cGFyZW50X2lkIGNyZWF0ZSBhIGxvb3A/CiAgICBzZWVuLCBjdXIgPSBzZXQoKSwgcGFyZW50X2lkCiAgICB3aGlsZSBjdXI6CiAgICAgICAgaWYgY3VyID09IHRpZDogcmV0dXJuIFRydWUKICAgICAgICBpZiBjdXIgaW4gc2VlbjogYnJlYWsKICAgICAgICBzZWVuLmFkZChjdXIpOyBjdXIgPSAoYlsidGFza3MiXS5nZXQoY3VyKSBvciB7fSkuZ2V0KCJwYXJlbnQiKQogICAgcmV0dXJuIEZhbHNlCmRlZiBzdGF0ZV9nYXRlKGIsIHQsIG5ld3N0YXRlKToKICAgICIiIklzc3VlICMzIGdhdGVzLiBSZXR1cm5zIGFuIGVycm9yIHN0cmluZyB0byBibG9jayB0aGUgdHJhbnNpdGlvbiwgb3IgTm9uZSB0byBhbGxvdy4KICAgIC0gRE9ORSBpcyBibG9ja2VkIHdoaWxlIGFueSBzdWJ0YXNrL2RlcGVuZGVuY3kgaXMgc3RpbGwgaW5jb21wbGV0ZSAoQ0VPJ3MgcmVxdWVzdGVkIGd1YXJkcmFpbCkuCiAgICAtIFdPUktJTkcgaXMgYmxvY2tlZCBvbmx5IHdoZW4gdGhpcyBjYXJkJ3MgcGVyLWNhcmQgaGFyZCBnYXRlIGlzIE9OIGFuZCBhIHByZXJlcSBpcyB1bm1ldCAoT0ZGIGJ5IGRlZmF1bHQpLiIiIgogICAgaWYgbmV3c3RhdGUgPT0gImRvbmUiOgogICAgICAgIGluYywgdW4gPSBfaW5jb21wbGV0ZV9jaGlsZHJlbihiLCB0WyJpZCJdKSwgX3VubWV0X2RlcHMoYiwgdCkKICAgICAgICBpZiBpbmMgb3IgdW46CiAgICAgICAgICAgIHBhcnRzID0gW10KICAgICAgICAgICAgaWYgaW5jOiBwYXJ0cy5hcHBlbmQoZiJ7bGVuKGluYyl9IHN1YnRhc2socykgbm90IGRvbmUvY2FuY2VsbGVkIikKICAgICAgICAgICAgaWYgdW46ICBwYXJ0cy5hcHBlbmQoZiJ7bGVuKHVuKX0gZGVwZW5kZW5jeShpZXMpIG5vdCBkb25lL2NhbmNlbGxlZCIpCiAgICAgICAgICAgIHJldHVybiAiY2Fubm90IG1hcmsgRE9ORSDigJQgIiArICIgYW5kICIuam9pbihwYXJ0cykgKyAiIChmaW5pc2ggb3IgY2FuY2VsIHRoZW0gZmlyc3QpIgogICAgaWYgbmV3c3RhdGUgPT0gIndvcmtpbmciIGFuZCB0LmdldCgiaGFyZEdhdGUiKToKICAgICAgICB1biA9IF91bm1ldF9kZXBzKGIsIHQpCiAgICAgICAgaWYgdW46IHJldHVybiBmImhhcmQgZ2F0ZSBPTiDigJQgYmxvY2tlZCBieSB7bGVuKHVuKX0gdW5maW5pc2hlZCBwcmVyZXF1aXNpdGUocyk7IGZpbmlzaC9jYW5jZWwgdGhlbSBvciB0dXJuIHRoZSBoYXJkIGdhdGUgb2ZmIgogICAgcmV0dXJuIE5vbmUKCiMg4pSA4pSAIHRlc3QvZGVtby9wcm9vZiBjYXJkIEVYRU1QVElPTiDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKIyBBbiBlbmdpbmVlcidzIHRocm93YXdheSBmaXh0dXJlIG11c3QgTk9UIG51ZGdlIHRoZSBCb3NzL0NFTzogYSBjYXJkIGZsYWdnZWQgdGVzdDp0cnVlIE9SIHdob3NlIHRpdGxlCiMgc3RhcnRzIHdpdGggW2RlbW9dL1twcm9vZl0vW3Rlc3RdIGZpcmVzIE5PIGNyZWF0ZS1waW5nLCBpcyBza2lwcGVkIGJ5IHRoZSBjcm9uICsgYnJhaW5zdG9ybS10cmlhZ2UgKwojIHRoZSBhc3NpZ25lZC1pZGxlIHdhdGNoZG9nLCBhbmQgbmV2ZXIgYXBwZWFycyBpbiB0aGUgQ0VPIFdoYXRzQXBwIGRpZ2VzdC4gKFJlYWwgd29yayBpcyBuZXZlciBwcmVmaXhlZAojIHRoYXQgd2F5LCBzbyB0aGlzIGNhbid0IHNpbGVuY2UgYSBnZW51aW5lIHRhc2suKQpfVEVTVF9QUkVGSVhFUyA9ICgiW2RlbW9dIiwgIltwcm9vZl0iLCAiW3Rlc3RdIiwgIltkZW1vICIsICJbcHJvb2YgIiwgIlt0ZXN0ICIpCmRlZiBfaXNfdGVzdCh0KToKICAgIGlmIHQuZ2V0KCJ0ZXN0IikgaXMgVHJ1ZTogcmV0dXJuIFRydWUKICAgIHJldHVybiAodC5nZXQoInRleHQiKSBvciAiIikubHN0cmlwKCkubG93ZXIoKS5zdGFydHN3aXRoKF9URVNUX1BSRUZJWEVTKQoKIyDilIDilIAgQlJBSU5TVE9STSBHQVRFIChzbGljZSBkKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKIyBBbiB1bmRlci1zcGVjaWZpZWQgbmV3IHRhc2sgY2FuJ3QgYmUgd29ya2VkIHVudGlsIGl0J3MgYmVlbiBicmFpbnN0b3JtZWQ6IHRoZSBicmFpbnN0b3JtCiMgd29ya2VyIChiaW4vdG9kby1icmFpbnN0b3JtKSBnZW5lcmF0ZXMgY2xhcmlmeWluZyBRVUVTVElPTlMgKG9mZmljZS1ob3VycyBtZXRob2QsIHZpYSBoZWFkbGVzcwojIGNsYXVkZSkgYW5kIHBvc3RzIHRoZW0gaGVyZTsgdGhleSBzdXJmYWNlIGluIHRoZSBjYXJkIEFTIHF1ZXN0aW9ucyB0byB0aGUgQ0VPOyB0aGUgdGFzayBzdGF5cwojIG5lZWRzX2JyYWluc3Rvcm0gYW5kIG5vbi13b3JrYWJsZSB1bnRpbCBldmVyeSBxdWVzdGlvbiBpcyBhbnN3ZXJlZDsgdGhlIHJlc29sdmVkIFEmQSBpcyBmb2xkZWQKIyBpbnRvIHRoZSBkdXJhYmxlIGJyYWluc3Rvcm0gYXJ0aWZhY3QuIEEgdGFzayB0aGUgZ2VuZXJhdG9yIGp1ZGdlcyBhbHJlYWR5LWNsZWFyIGdldHMgWkVSTwojIHF1ZXN0aW9ucyArIGEgb25lLWxpbmUgYnJhaW5zdG9ybSDihpIgaW1tZWRpYXRlbHkgcHJvbW90YWJsZS4gKFNpbGVudC1uby1vcCBzdXJmYWNpbmcgYWxyZWFkeSBzaGlwcy4pCmRlZiBfdW5hbnN3ZXJlZCh0KToKICAgIHJldHVybiBbcSBmb3IgcSBpbiB0LmdldCgicXVlc3Rpb25zIiwgW10pIGlmIG5vdCAocS5nZXQoImFuc3dlciIpIG9yICIiKS5zdHJpcCgpXQoKZGVmIGJyYWluc3Rvcm1fcmVhZHkodCk6CiAgICAiIiJUcnVlIGlmZiB0aGUgdGFzayBoYXMgY2xlYXJlZCB0aGUgZ2F0ZSBhbmQgbWF5IGJlIHByb21vdGVkIHRvIHdvcmtpbmcuIiIiCiAgICBpZiBfdW5hbnN3ZXJlZCh0KTogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBvcGVuIHF1ZXN0aW9ucyBibG9jayB0aGUgZ2F0ZQogICAgICAgIHJldHVybiBGYWxzZQogICAgcmV0dXJuIGJvb2woKHQuZ2V0KCJicmFpbnN0b3JtIikgb3IgIiIpLnN0cmlwKCkpIG9yIGJvb2wodC5nZXQoInF1ZXN0aW9ucyIpKQoKZGVmIF9hc3NlbWJsZV9hcnRpZmFjdCh0KToKICAgICIiIkZvbGQgdGhlIGFuc3dlcmVkIFEmQSBpbnRvIHRoZSBkdXJhYmxlIGJyYWluc3Rvcm0gYXJ0aWZhY3QgKGlkZW1wb3RlbnQtaXNoKS4iIiIKICAgIHFzID0gdC5nZXQoInF1ZXN0aW9ucyIsIFtdKQogICAgaWYgbm90IHFzOiByZXR1cm4KICAgIGxpbmVzID0gWyIiLCAi4pSA4pSAIGNsYXJpZmljYXRpb25zIChDRU8pIOKUgOKUgCJdCiAgICBmb3IgcSBpbiBxczoKICAgICAgICBsaW5lcy5hcHBlbmQoZiJROiB7cS5nZXQoJ3EnLCcnKS5zdHJpcCgpfSIpCiAgICAgICAgbGluZXMuYXBwZW5kKGYiQTogeyhxLmdldCgnYW5zd2VyJykgb3IgJycpLnN0cmlwKCl9IikKICAgIGJsb2NrID0gIlxuIi5qb2luKGxpbmVzKQogICAgYmFzZSA9ICh0LmdldCgiYnJhaW5zdG9ybSIpIG9yICIiKS5zdHJpcCgpCiAgICBpZiAi4pSA4pSAIGNsYXJpZmljYXRpb25zIChDRU8pIOKUgOKUgCIgaW4gYmFzZTogICAgICAgICAgICAgIyByZWZyZXNoIHRoZSBibG9jayByYXRoZXIgdGhhbiBzdGFjayBjb3BpZXMKICAgICAgICBiYXNlID0gYmFzZS5zcGxpdCgi4pSA4pSAIGNsYXJpZmljYXRpb25zIChDRU8pIOKUgOKUgCIpWzBdLnJzdHJpcCgpCiAgICAgICAgYmxvY2sgPSAiXG4iICsgYmxvY2sKICAgIHRbImJyYWluc3Rvcm0iXSA9IChiYXNlICsgIlxuIiArIGJsb2NrKS5zdHJpcCgpIGlmIGJhc2UgZWxzZSBibG9jay5zdHJpcCgpCgojIOKUgOKUgCBpc3N1ZS1zdHlsZSB0aHJlYWQgKHNsaWNlIGIpOiBhIGR1cmFibGUgcGVyLXRhc2sgY29tbWVudC9ldmVudCB0aW1lbGluZS4g4pSA4pSACiMgRXZlcnkgbWVhbmluZ2Z1bCBzaWduYWwgKGVuZ2luZWVyIHN0YXR1cywgc3RhdGUgdHJhbnNpdGlvbiwgYnJhaW5zdG9ybSBzYXZlLCBDRU8vQUkgY29tbWVudCkKIyBpcyBhcHBlbmRlZCBhcyBhbiBpbW11dGFibGUgZXZlbnQgc28gdGhlIGNhcmQgc2hvd3MgdGhlIEZVTEwgaGlzdG9yeSwgR2l0SHViLWlzc3VlIHN0eWxlIOKAlAojIHVubGlrZSBsYXN0U3RhdHVzLCB3aGljaCBpcyBvdmVyd3JpdHRlbi4gVGhlIGNhcmQgVUkgbWVyZ2VzIHRoZXNlIHdpdGggcHJvb2ZzW10gYnkgdHMuCiMgICBraW5kOiAnY29tbWVudCcgKENFTy9lbmdpbmVlciBmcmVlIHRleHQpIHwgJ3N0YXR1cycgKGVuZ2luZWVyIGxhc3RTdGF0dXMpIHwKIyAgICAgICAgICdzdGF0ZScgKHN0YXRlIHRyYW5zaXRpb24pIHwgJ2JyYWluc3Rvcm0nIChhcnRpZmFjdCBzYXZlZC91cGRhdGVkKQpkZWYgYWRkX2NvbW1lbnQodCwgYm9keSwgYnksIGtpbmQ9ImNvbW1lbnQiKToKICAgIGJvZHkgPSAoYm9keSBvciAiIikuc3RyaXAoKQogICAgaWYgbm90IGJvZHk6IHJldHVybiBOb25lCiAgICBjID0geyJpZCI6IHVpZCgpLCAia2luZCI6IGtpbmQsICJib2R5IjogYm9keSwgImJ5IjogYnkgb3IgInN5c3RlbSIsICJ0cyI6IG5vdygpfQogICAgdC5zZXRkZWZhdWx0KCJjb21tZW50cyIsIFtdKS5hcHBlbmQoYykKICAgIHJldHVybiBjCgojIOKUgOKUgCBCb3NzIHBpbmc6IHRoZSBPTkxZIHRoaW5nIHRoZSBwaW5nIG1hY2hpbmUgZG9lcy4gQWx3YXlzIHRhcmdldHMgdGhlIEJvc3MuIOKUgOKUgApkZWYgYm9zc19waW5nKHRhc2tfaWQsIHJlYXNvbik6CiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCkKICAgICAgICB0ID0gYlsidGFza3MiXS5nZXQodGFza19pZCkKICAgICAgICBpZiBub3QgdDogcmV0dXJuCiAgICAgICAgdFsicGluZ3NUb0Jvc3MiXSA9IHQuZ2V0KCJwaW5nc1RvQm9zcyIsIDApICsgMQogICAgICAgIHRbInVwZGF0ZWQiXSA9IG5vdygpCiAgICAgICAgc2F2ZShiKQogICAgICAgICMgQ09NUEFDVCBlbnZlbG9wZSAo4omkfjIyMCBjaGFycykuIEVtYmVkZGluZyB0aGUgRlVMTCBjYXJkIHRleHQgaGVyZSAofjE1MDAgY2hhcnMpIG1hZGUgdGhlCiAgICAgICAgIyBicmFja2V0ZWQtcGFzdGUgbGFuZCBhcyBhIGxhcmdlIHN0dWNrIGRyYWZ0IGluIHRoZSBCb3NzJ3MgY29tcG9zZXI6IHdoZW4gdGhlIEJvc3Mgd2FzIG1pZC10dXJuCiAgICAgICAgIyB0aGUgZGVsYXllZC1FbnRlciB3YXMgYWJzb3JiZWQgYW5kIHRtdXhfc2VuZF90ZXh0J3MgOC1yZXRyeSByZWNvdmVyeSBjb3VsZCBub3Qgc3VibWl0IGl0LCBzbwogICAgICAgICMgdGhlIHBpbmcgd2FzIGEgUkVBTCBub24tZGVsaXZlcnkgKHJjPTEgImNvbXBvc2VyIHN0aWxsIGhlbGQgYSBkcmFmdCIpLiBBIHNob3J0IG1lc3NhZ2Ugc3VibWl0cy8KICAgICAgICAjIHF1ZXVlcyBjbGVhbmx5LiBUaGUgY2FyZCBpZCBpcyB0aGUgbG9va3VwIGtleTsgdGhlIHRpdGxlJ3MgZmlyc3QgbGluZSBpcyBlbm91Z2ggY29udGV4dC4KICAgICAgICB0aXRsZSA9ICh0LmdldCgidGV4dCIsICIiKS5zcGxpdGxpbmVzKClbMF0gaWYgdC5nZXQoInRleHQiKSBlbHNlICIiKVs6ODBdCiAgICAgICAgbXNnID0gZiJbdG9kb10gdGFzayB7dGFza19pZH0gXCJ7dGl0bGV9XCI6IHtyZWFzb259LiBzdGF0ZT17dFsnc3RhdGUnXX0gYXNzaWduZWU9e3RbJ2Fzc2lnbmVlJ119IgogICAgdHJ5OgogICAgICAgIElOQk9YX0xPRy5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgICAgIHdpdGggSU5CT1hfTE9HLm9wZW4oImEiKSBhcyBmOiBmLndyaXRlKGYie25vdygpfSB7bXNnfVxuIikKICAgIGV4Y2VwdCBFeGNlcHRpb246IHBhc3MKICAgIGlmIG5vdCBURVNUX1NJTksgYW5kIHNodXRpbC53aGljaCgibXAiKToKICAgICAgICB0cnk6CiAgICAgICAgICAgIHIgPSBzdWJwcm9jZXNzLnJ1bihbIm1wIiwgInNlbmQiLCBCT1NTX0FHRU5ULCBtc2ddLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9MzApCiAgICAgICAgICAgIHdpdGggSU5CT1hfTE9HLm9wZW4oImEiKSBhcyBmOgogICAgICAgICAgICAgICAgZi53cml0ZShmIntub3coKX0gTVBfU0VORCAtPiB7Qk9TU19BR0VOVH0gcmM9e3IucmV0dXJuY29kZX0gOjogeyhyLnN0ZG91dCBvciByLnN0ZGVycikuc3RyaXAoKVs6MTQwXX1cbiIpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgICAgICB3aXRoIElOQk9YX0xPRy5vcGVuKCJhIikgYXMgZjogZi53cml0ZShmIntub3coKX0gTVBfU0VORCBFUlJPUiB7ZX1cbiIpCgojIOKUgOKUgCBwaW5nIG1hY2hpbmUgKGEpOiBjcm9uIOKAlCBhY3RpdmUgKyBVTkFTU0lHTkVEIHRhc2tzIHBpbmcgdGhlIEJvc3MgZXZlcnkgUElOR19DUk9OIOKUgOKUgApkZWYgY3Jvbl9sb29wKCk6CiAgICB3aGlsZSBUcnVlOgogICAgICAgIHRpbWUuc2xlZXAoUElOR19DUk9OKQogICAgICAgIGZvciB0aWQgaW4gbGlzdChsb2FkKClbInRhc2tzIl0ua2V5cygpKToKICAgICAgICAgICAgdCA9IGxvYWQoKVsidGFza3MiXS5nZXQodGlkKQogICAgICAgICAgICBpZiBub3QgdCBvciBfaXNfdGVzdCh0KTogY29udGludWUgICAgICAgICAgIyB0ZXN0L2RlbW8vcHJvb2YgZml4dHVyZXMgbmV2ZXIgbnVkZ2UgdGhlIEJvc3MKICAgICAgICAgICAgIyBUaGUgQm9zcyBjcm9uIG9ubHkgY2hhc2VzIEFDVElWRSAod29yay10by1kb25lKSArIHVuYXNzaWduZWQgV09SSyB0byBhc3NpZ24rZGlzcGF0Y2guCiAgICAgICAgICAgICMgQnJhaW5zdG9ybS10cmlhZ2UgaXMgTk9UIGEgcmVwZWF0ZWQgQm9zcyBudWRnZTogYSBjYXJkIGJsb2NrZWQgb24gdGhlIENFTyAocmV2aWV3IC8gYmxvY2tlZCAvCiAgICAgICAgICAgICMgbmVlZHNfYnJhaW5zdG9ybS13aXRoLXF1ZXN0aW9ucykgaXMgcGluZ2VkIHRvIHRoZSBDRU8ncyBXaGF0c0FwcCBieSB0aGUgQ0VPLXdhdGNoZG9nIChzbGljZSBlKSwKICAgICAgICAgICAgIyBhbmQgYSBmcmVzaGx5LWNyZWF0ZWQgY2FyZCBnZXRzIE9ORSBjcmVhdGUtcGluZy4gU28gdGhlcmUncyBubyByZXBlYXRlZCBpbi1hcHAgYnJhaW5zdG9ybSBjcm9uLgogICAgICAgICAgICBpZiBBQ1RJVkUodCkgYW5kIG5vdCB0LmdldCgiYXNzaWduZWUiKSBhbmQgdFsic3RhdGUiXSBub3QgaW4gKCJibG9ja2VkIiwgInJldmlldyIpOgogICAgICAgICAgICAgICAgcmVhc29uID0gIm5lZWRzIGJyYWluc3Rvcm0iIGlmIHRbInN0YXRlIl0gPT0gIm5lZWRzX2JyYWluc3Rvcm0iIGVsc2UgIndvcmtpbmcgJiB1bmFzc2lnbmVkIOKAlCBhc3NpZ24rZGlzcGF0Y2giCiAgICAgICAgICAgICAgICBib3NzX3BpbmcodGlkLCBmImNyb24odW5hc3NpZ25lZCk6IHtyZWFzb259IikKCiMg4pSA4pSAIHBpbmcgbWFjaGluZSAoYik6IGlkbGUtZHJpdmVuIOKAlCBmaXJlZCBieSB0aGUgQVNTSUdORUQgZW5naW5lZXIncyBzdG9wIGhvb2sg4pSA4pSACmRlZiBvbl9zdG9wX2hvb2soYWdlbnRfaWQsIGhvb2tfc3RhdGUpOgogICAgX2hvb2tfc3RhdGVbYWdlbnRfaWRdID0gaG9va19zdGF0ZSAgICAgICAgICAgIyBsYXRlc3Qgc3RhdGUgd2lucwogICAgdF9hdF9maXJlID0gaG9va19zdGF0ZQogICAgZGVmIGNoZWNrKCk6CiAgICAgICAgaWYgX2hvb2tfc3RhdGUuZ2V0KGFnZW50X2lkKSAhPSAiaWRsZSI6ICAjIHBpY2tlZCB1cCB3b3JrIHdpdGhpbiB0aGUgZ3JhY2Ugd2luZG93CiAgICAgICAgICAgIHJldHVybgogICAgICAgIGZvciB0aWQgaW4gbGlzdChsb2FkKClbInRhc2tzIl0ua2V5cygpKToKICAgICAgICAgICAgdCA9IGxvYWQoKVsidGFza3MiXS5nZXQodGlkKQogICAgICAgICAgICBpZiB0IGFuZCBBQ1RJVkUodCkgYW5kIHQuZ2V0KCJhc3NpZ25lZSIpID09IGFnZW50X2lkOgogICAgICAgICAgICAgICAgYm9zc19waW5nKHRpZCwgZiJpZGxlIHtJRExFX0dSQUNFfXMgYWZ0ZXIge2FnZW50X2lkfSBzdG9wLWhvb2sg4oCUIG5vdCBkb25lIikKICAgIHdpdGggX2xvY2s6CiAgICAgICAgYiA9IGxvYWQoKQogICAgICAgIGZvciB0IGluIGJbInRhc2tzIl0udmFsdWVzKCk6CiAgICAgICAgICAgIGlmIHQuZ2V0KCJhc3NpZ25lZSIpID09IGFnZW50X2lkOiB0WyJsYXN0U3RvcFRzIl0gPSBub3coKQogICAgICAgIHNhdmUoYikKICAgIGlmIGhvb2tfc3RhdGUgPT0gImlkbGUiOgogICAgICAgIHRocmVhZGluZy5UaW1lcihJRExFX0dSQUNFLCBjaGVjaykuc3RhcnQoKQoKIyDilIDilIAgcGluZyBtYWNoaW5lIChjKTogQVNTSUdORUQtQlVULUlETEUgV0FUQ0hET0cg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACiMgUmVhbCBlbmdpbmVlcnMgZG9uJ3QgUE9TVCAvaG9vay9zdG9wLCBzbyBtYWNoaW5lIChiKSBvZnRlbiBuZXZlciBmaXJlcy4gVGhpcwojIHdhdGNoZG9nIGFjdGl2ZWx5IGRldGVjdHMgYW4gYXNzaWduZWQgZW5naW5lZXIgdGhhdCBoYXMgZ29uZSBpZGxlL3N0YWxsZWQgYXQKIyBpdHMgcHJvbXB0IGFuZCBwaW5ncyB0aGUgQm9zcy4gU2lnbmFsIChteXBlb3BsZS1uYXRpdmUpOgojICAgKiB0aGUgYWdlbnQncyBzdGF0dXMuanNvbiAoc3RhdHVzPSdpZGxlJyArICd0aW1lc3RhbXAnID0gd2hlbiBpdCBsYXN0IFNUT1BQRUQpCiMgICAqIGl0cyBDbGF1ZGUgc2Vzc2lvbiB0cmFuc2NyaXB0IG10aW1lIChzdGlsbCBiZWluZyB3cml0dGVuID09IGJ1c3kgaW4gYSB0dXJuKQojIFN0YWxsZWQgIDo9IHN0b3BwZWQgPiBJRExFX1NUQUxMIGFnbyAgQU5EICB0cmFuc2NyaXB0IG5vdCB3cml0dGVuIGluIElETEVfU1RBTEwKIyAgICAgICAgICAgICAoc28gYSBsb25nIHNpbGVudCByZW5kZXIgcmVhZHMgYXMgYnVzeSwgbm90IGlkbGUg4oCUIG5vIGZhbHNlIHN0YWxsKS4KIyBVbmtub3duIGFnZW50IChubyBzdGF0dXMgZmlsZSkgLT4gdHJlYXQgYXMgc3RhbGxlZCAoZXJyIHRvd2FyZCBwaW5naW5nLCBwZXIgQ0VPKS4KZGVmIF9pc29fZXBvY2godHMpOgogICAgdHJ5OiByZXR1cm4gZGF0ZXRpbWUuZGF0ZXRpbWUuZnJvbWlzb2Zvcm1hdCh0cy5yZXBsYWNlKCJaIiwgIiswMDowMCIpKS50aW1lc3RhbXAoKQogICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIE5vbmUKCmRlZiBfc3RhdHVzX2ZvcihhZ2VudF9pZCk6CiAgICB0cnk6CiAgICAgICAgZm9yIHAgaW4gU1RBVFVTX0RJUi5nbG9iKCIqLyouanNvbiIpOgogICAgICAgICAgICB0cnk6IGQgPSBqc29uLmxvYWRzKHAucmVhZF90ZXh0KCkpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IGNvbnRpbnVlCiAgICAgICAgICAgIGlmIGQuZ2V0KCJhZ2VudF9pZCIpID09IGFnZW50X2lkOiByZXR1cm4gZAogICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwogICAgcmV0dXJuIE5vbmUKCmRlZiBfc2Vzc2lvbl9hY3RpdmVfd2l0aGluKHNlc3Npb25faWQsIHdpbmRvdyk6CiAgICBpZiBub3Qgc2Vzc2lvbl9pZDogcmV0dXJuIEZhbHNlCiAgICBub3d0ID0gdGltZS50aW1lKCkKICAgIHRyeToKICAgICAgICBmb3IgcCBpbiBQUk9KRUNUU19ESVIuZ2xvYihmIiove3Nlc3Npb25faWR9Lmpzb25sIik6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGlmIG5vd3QgLSBwLnN0YXQoKS5zdF9tdGltZSA8IHdpbmRvdzogcmV0dXJuIFRydWUKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogY29udGludWUKICAgIGV4Y2VwdCBFeGNlcHRpb246IHBhc3MKICAgIHJldHVybiBGYWxzZQoKIyBQcm9jZXNzLWxldmVsICJpcyB0aGUgZW5naW5lZXIgYWN0dWFsbHkgcnVubmluZyBhIGxvbmcgam9iPyIg4oCUIGNvdmVycyB0aGUgY2FzZSB3aGVyZSBhIGxvbmcKIyBiYXNoL3Rvb2wgY2FsbCAoZmZtcGVnIHJlbmRlciwgZG9ja2VyIGJ1aWxkLCBucG0gYnVpbGQpIG1ha2VzIHRoZSB0cmFuc2NyaXB0IGdvIHF1aWV0IGZvciBtaW51dGVzLgpkZWYgX3Byb2NfdGFibGUoKToKICAgICMgcGlkIC0+IChwcGlkLCBwY3B1LCBjb21tKQogICAgdHJ5OgogICAgICAgIG91dCA9IHN1YnByb2Nlc3MucnVuKFsicHMiLCAiLWF4byIsICJwaWQ9LHBwaWQ9LHBjcHU9LGNvbW09Il0sIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD01KS5zdGRvdXQKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIHt9CiAgICB0YWIgPSB7fQogICAgZm9yIGxuIGluIG91dC5zcGxpdGxpbmVzKCk6CiAgICAgICAgcCA9IGxuLnNwbGl0KE5vbmUsIDMpCiAgICAgICAgaWYgbGVuKHApIDwgNDogY29udGludWUKICAgICAgICB0cnk6IHRhYltpbnQocFswXSldID0gKGludChwWzFdKSwgZmxvYXQocFsyXSksIG9zLnBhdGguYmFzZW5hbWUocFszXS5zdHJpcCgpKSkKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiBjb250aW51ZQogICAgcmV0dXJuIHRhYgoKZGVmIF9ldGltZV9zZWNzKHBpZCk6CiAgICAjIHBvcnRhYmxlIChtYWNPUyArIExpbnV4KTogZWxhcHNlZCBzZWNvbmRzIHNpbmNlIGBwaWRgIHN0YXJ0ZWQsIGZyb20gcHMgZXRpbWUgKFtbREQtXUhIOl1NTTpTUykKICAgIHRyeToKICAgICAgICBvdXQgPSBzdWJwcm9jZXNzLnJ1bihbInBzIiwgIi1vIiwgImV0aW1lPSIsICItcCIsIHN0cihwaWQpXSwgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTUpLnN0ZG91dC5zdHJpcCgpCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHJldHVybiBOb25lCiAgICBpZiBub3Qgb3V0OiByZXR1cm4gTm9uZQogICAgZGF5cyA9IDAKICAgIGlmICItIiBpbiBvdXQ6CiAgICAgICAgZCwgb3V0ID0gb3V0LnNwbGl0KCItIiwgMSkKICAgICAgICB0cnk6IGRheXMgPSBpbnQoZCkKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gTm9uZQogICAgdHJ5OiBwYXJ0cyA9IFtpbnQoeCkgZm9yIHggaW4gb3V0LnNwbGl0KCI6IildCiAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gTm9uZQogICAgaWYgbGVuKHBhcnRzKSA9PSAzOiAgIGgsIG0sIHMgPSBwYXJ0cwogICAgZWxpZiBsZW4ocGFydHMpID09IDI6IGgsIG0sIHMgPSAwLCBwYXJ0c1swXSwgcGFydHNbMV0KICAgIGVsc2U6IHJldHVybiBOb25lCiAgICByZXR1cm4gZGF5cyAqIDg2NDAwICsgaCAqIDM2MDAgKyBtICogNjAgKyBzCgpkZWYgX2Rlc2NlbmRhbnRzKHBwLCB0YWIpOgogICAga2lkcyA9IHt9CiAgICBmb3IgcGlkLCB2IGluIHRhYi5pdGVtcygpOiBraWRzLnNldGRlZmF1bHQodlswXSwgW10pLmFwcGVuZChwaWQpCiAgICBzZWVuLCBzdGFjayA9IHNldCgpLCBbcHBdCiAgICB3aGlsZSBzdGFjazoKICAgICAgICB4ID0gc3RhY2sucG9wKCkKICAgICAgICBmb3IgYyBpbiBraWRzLmdldCh4LCBbXSk6CiAgICAgICAgICAgIGlmIGMgbm90IGluIHNlZW46IHNlZW4uYWRkKGMpOyBzdGFjay5hcHBlbmQoYykKICAgIHJldHVybiBbcCBmb3IgcCBpbiAoc2VlbiB8IHtwcH0pIGlmIHAgaW4gdGFiXQoKZGVmIF9zZXNzaW9uX2FnZShhZ2VudF9pZCk6CiAgICAiIiJTZWNvbmRzIHNpbmNlIHRoZSBhZ2VudCdzIENVUlJFTlQgbGl2ZSBzZXNzaW9uIHN0YXJ0ZWQgKGl0cyBjbGF1ZGUgcHJvY2VzcyBhZ2UpLCBzbyBhCiAgICByZXNwYXduZWQgYWdlbnQgcmV1c2luZyBhIG5hbWUgaXNuJ3QganVkZ2VkIGJ5IHRoZSBkZWFkIHNlc3Npb24ncyBzdGFsZSBzdG9wLXRpbWVzdGFtcC4iIiIKICAgIHBwID0gX3BhbmVfcGlkKGFnZW50X2lkKQogICAgaWYgbm90IHBwOiByZXR1cm4gTm9uZQogICAgdGFiID0gX3Byb2NfdGFibGUoKQogICAgY2xhdWRlX3BpZHMgPSBbcCBmb3IgcCBpbiBfZGVzY2VuZGFudHMocHAsIHRhYikgaWYgdGFiLmdldChwLCAoMCwgMCwgIiIpKVsyXSA9PSAiY2xhdWRlIl0gaWYgcHAgaW4gdGFiIGVsc2UgW10KICAgIGFnZXMgPSBbYSBmb3IgYSBpbiAoX2V0aW1lX3NlY3MocCkgZm9yIHAgaW4gKGNsYXVkZV9waWRzIG9yIFtwcF0pKSBpZiBhIGlzIG5vdCBOb25lXQogICAgcmV0dXJuIG1pbihhZ2VzKSBpZiBhZ2VzIGVsc2UgTm9uZSAgICAgICAgICAgICAgIyB5b3VuZ2VzdCBjbGF1ZGUgPSBjdXJyZW50IHNlc3Npb247IGVsc2UgcGFuZSBzaGVsbCBhZ2UKCmRlZiBfcGFuZV9waWQoYWdlbnRfaWQpOgogICAgIiIidG11eCBwYW5lIHBpZCBmb3IgYWdlbnQgaG9zdC9zZXNzaW9uOnRhYiAtPiB0bXV4IHNlc3Npb24gJ21jLTxzZXNzaW9uPicsIHdpbmRvdyAnPHRhYj4nLiIiIgogICAgdHJ5OiBzZXNzLCB0YWIgPSBhZ2VudF9pZC5zcGxpdCgiLyIsIDEpWzFdLnNwbGl0KCI6IiwgMSkKICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBOb25lCiAgICB0cnk6CiAgICAgICAgciA9IHN1YnByb2Nlc3MucnVuKFsidG11eCIsICJsaXN0LXBhbmVzIiwgIi1zIiwgIi10IiwgIm1jLSIgKyBzZXNzLCAiLUYiLCAiI3t3aW5kb3dfbmFtZX1cdCN7cGFuZV9waWR9Il0sCiAgICAgICAgICAgICAgICAgICAgICAgICAgIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD01KQogICAgICAgIGlmIHIucmV0dXJuY29kZSAhPSAwOiByZXR1cm4gTm9uZQogICAgICAgIGZvciBsbiBpbiByLnN0ZG91dC5zcGxpdGxpbmVzKCk6CiAgICAgICAgICAgIHcsIF8sIHBwID0gbG4ucGFydGl0aW9uKCJcdCIpCiAgICAgICAgICAgIGlmIHcgPT0gdGFiOgogICAgICAgICAgICAgICAgdHJ5OiByZXR1cm4gaW50KHBwKQogICAgICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIE5vbmUKICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBOb25lCiAgICByZXR1cm4gTm9uZQoKZGVmIF9pZ25vcmVkX2Zvcl9jcHUoY29tbSk6CiAgICAjIHRoZSBwZXJzaXN0ZW50IE1DUC9icm93c2VyIHN0YWNrIGJ1cm5zIENQVSByZWdhcmRsZXNzIG9mIHdoZXRoZXIgdGhlIGFnZW50IGlzIHdvcmtpbmc7CiAgICAjIGl0IG11c3QgTk9UIGNvdW50IGFzICJidXN5Iiwgb3IgYSBwYXJrZWQgYWdlbnQgd2l0aCBhbiBvcGVuIGJyb3dzZXIgd291bGQgbmV2ZXIgYmUgZmxhZ2dlZC4KICAgIGMgPSBjb21tLmxvd2VyKCkKICAgIHJldHVybiBhbnkoayBpbiBjIGZvciBrIGluICgiY2hyb21lIiwgIm5vZGUiLCAiY2FmZmVpbmF0ZSIsICJtY3AiLCAiOTIyMiIsICJnb29nbGUiKSkKCmRlZiBhZ2VudF9idXN5KGFnZW50X2lkKToKICAgICIiIlRydWUgaWYgdGhlIGFzc2lnbmVkIGVuZ2luZWVyIGhhcyBhbiBBQ1RJVkUgbG9uZy1ydW5uaW5nIGpvYiBpbiBpdHMgcHJvY2VzcyB0cmVlLgogICAgVHdvIHNpZ25hbHM6ICgxKSBhIGhlYXZ5IGNvbW1hbmQgYnkgTkFNRSAoZmZtcGVnL2RvY2tlci9idWlsZCB0b29scyDigJQgdGhlIGRvY2tlci9mZm1wZWcgQ0xJCiAgICBjbGllbnQgc3RheXMgYSBwYW5lIGNoaWxkIGZvciB0aGUgd2hvbGUgam9iLCBNQ1AtaW1tdW5lKTsgKDIpIENQVSBidXJuIEVYQ0xVRElORyB0aGUgcGVyc2lzdGVudAogICAgTUNQL2Jyb3dzZXIgc3RhY2suIFJldHVybnMgRmFsc2UgaWYgdGhlIHBhbmUgY2FuJ3QgYmUgbG9jYXRlZCAobm8gdG11eCkgLT4gdHJhbnNjcmlwdC90aW1lc3RhbXAgZGVjaWRlLiIiIgogICAgcHAgPSBfcGFuZV9waWQoYWdlbnRfaWQpCiAgICBpZiBub3QgcHA6IHJldHVybiBGYWxzZQogICAgdGFiID0gX3Byb2NfdGFibGUoKQogICAgbm9kZXMgPSBfZGVzY2VuZGFudHMocHAsIHRhYikKICAgIGJ5X25hbWUgPSBhbnkodGFiW3BdWzJdIGluIEJVU1lfTkFNRVMgZm9yIHAgaW4gbm9kZXMpCiAgICBjcHUgPSBzdW0odGFiW3BdWzFdIGZvciBwIGluIG5vZGVzIGlmIG5vdCBfaWdub3JlZF9mb3JfY3B1KHRhYltwXVsyXSkpCiAgICBidXN5ID0gYnlfbmFtZSBvciBjcHUgPj0gQlVTWV9DUFUKICAgIGlmIG9zLmVudmlyb24uZ2V0KCJERUJVR19CVVNZIikgPT0gIjEiOgogICAgICAgIG5hbWVzID0gc29ydGVkKHt0YWJbcF1bMl0gZm9yIHAgaW4gbm9kZXN9KQogICAgICAgIHByaW50KGYiW2J1c3ldIHthZ2VudF9pZH0gcGFuZT17cHB9IGNwdShleGNsLW1jcCk9e2NwdTouMWZ9IGJ5X25hbWU9e2J5X25hbWV9IC0+IHtidXN5fSA6OiB7bmFtZXN9IiwgZmx1c2g9VHJ1ZSkKICAgIHJldHVybiBidXN5CgojIEdyb3VuZC10cnV0aCBCVVNZIHNpZ25hbCDigJQgdGhlIFNBTUUgbWFya2VyIGBtcCBwZWVrYCB1c2VzLiBDbGF1ZGUgQ29kZSBBTkQgQ29kZXggcHJpbnQKIyAiZXNjIHRvIGludGVycnVwdCIgaW4gdGhlIFRVSSBmb290ZXIgT05MWSB3aGlsZSBhIHR1cm4gaXMgYWN0aXZlbHkgcnVubmluZyAoQ29kZXggd3JhcHMgaXQKIyBhcyAiKiBXb3JraW5nIChOcyAqIGVzYyB0byBpbnRlcnJ1cHQpIikuIEEgZGVlcC10aGlua2luZyAvIGxvbmctdHVybiBhZ2VudCBidXJucyB+bm8gQ1BVIGFuZAojIHdyaXRlcyB+bm8gdHJhbnNjcmlwdCBtaWQtdHVybiwgc28gdGhlIENQVS90cmFuc2NyaXB0IHNpZ25hbHMgbWlzcyBpdCBhbmQgdGhlIHdhdGNoZG9nIHdvdWxkCiMgZmFsc2VseSBudWRnZSBpdC4gVGhpcyBwYW5lIHJlYWQgaXMgdGhlIGF1dGhvcml0YXRpdmUgImlzIGEgdHVybiBydW5uaW5nIFJJR0hUIE5PVz8iIGNoZWNrLgpQRUVLX0JVU1lfTUFSS0VSID0gImVzYyB0byBpbnRlcnJ1cHQiCgpkZWYgYWdlbnRfcGFuZV9idXN5KGFnZW50X2lkKToKICAgICIiIlRydWUgaWYgdGhlIGFnZW50J3MgbGl2ZSB0bXV4IHBhbmUgc2hvd3MgdGhlIGJ1c3kgbWFya2VyIChhIHR1cm4gaXMgYWN0aXZlbHkgcnVubmluZyksCiAgICBjbGFzc2lmaWVkIGV4YWN0bHkgbGlrZSBgbXAgcGVla2AvcGVla19zdGF0ZTogbGFzdCAxNSBOT04tQkxBTksgbGluZXMgb2YgdGhlIGZyYW1lIGNvbnRhaW4KICAgICdlc2MgdG8gaW50ZXJydXB0Jy4gUmV0dXJucyBGYWxzZSBpZiB0aGUgcGFuZSBjYW4ndCBiZSByZWFkIChubyB0bXV4KSAtPiBvdGhlciBzaWduYWxzIGRlY2lkZS4iIiIKICAgIHRyeToKICAgICAgICBzZXNzLCB0YWIgPSBhZ2VudF9pZC5zcGxpdCgiLyIsIDEpWzFdLnNwbGl0KCI6IiwgMSkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIEZhbHNlCiAgICB0cnk6CiAgICAgICAgciA9IHN1YnByb2Nlc3MucnVuKFsidG11eCIsICJjYXB0dXJlLXBhbmUiLCAiLXQiLCBmIm1jLXtzZXNzfTp7dGFifSIsICItcCIsICItUyIsICItMjAwIl0sCiAgICAgICAgICAgICAgICAgICAgICAgICAgIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD01KQogICAgICAgIGlmIHIucmV0dXJuY29kZSAhPSAwOiByZXR1cm4gRmFsc2UKICAgICAgICB0YWlsID0gIlxuIi5qb2luKFtsIGZvciBsIGluIHIuc3Rkb3V0LnNwbGl0bGluZXMoKSBpZiBsLnN0cmlwKCldWy0xNTpdKS5sb3dlcigpCiAgICAgICAgYnVzeSA9IFBFRUtfQlVTWV9NQVJLRVIgaW4gdGFpbAogICAgICAgIGlmIG9zLmVudmlyb24uZ2V0KCJERUJVR19CVVNZIikgPT0gIjEiOgogICAgICAgICAgICBwcmludChmIltwYW5lLWJ1c3ldIHthZ2VudF9pZH0gbWMte3Nlc3N9Ont0YWJ9IG1hcmtlcj17YnVzeX0iLCBmbHVzaD1UcnVlKQogICAgICAgIHJldHVybiBidXN5CiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHJldHVybiBGYWxzZQoKZGVmIGFzc2lnbmVlX2lkbGVfc2VjcyhhZ2VudF9pZCk6CiAgICAiIiJJZGxlIHNlY29uZHMgaWYgdGhlIGFzc2lnbmVkIGFnZW50IGxvb2tzIHBhcmtlZC9zdGFsbGVkLCBlbHNlIE5vbmUgKGFjdGl2ZS9ncmFjZS9idXN5LWpvYikuCgogICAgVGhlIG51ZGdlIGlzIGdhdGVkIG9uIHRoZSBhZ2VudCdzIEFDVFVBTCBzdGF0ZSwgbmV2ZXIganVzdCBlbGFwc2VkLXRpbWU6IGEgdHVybiBydW5uaW5nIFJJR0hUCiAgICBOT1cgKFRVSSBidXN5IG1hcmtlciwgdGhlIG1wLXBlZWsgZ3JvdW5kIHRydXRoKSBpcyBCVVNZIGFuZCBpcyBuZXZlciBudWRnZWQsIGV2ZW4gaWYgdGhlCiAgICBzdG9wLWhvb2sgdGltZXN0YW1wIGlzIHN0YWxlIGFuZCB0aGUgdHJhbnNjcmlwdCBpcyBxdWlldCAoZGVlcC10aGlua2luZyBsb25nIHR1cm4pLiBPbmx5IGEKICAgIGdlbnVpbmVseSBJRExFLWF0LXByb21wdCBhZ2VudCBwYXN0IHRoZSB0aHJlc2hvbGQgaXMgcmVwb3J0ZWQgYXMgc3RhbGxlZC4iIiIKICAgIGlmIGFnZW50X3BhbmVfYnVzeShhZ2VudF9pZCk6IHJldHVybiBOb25lICAgICAgICAgICAgICAjIGEgdHVybiBpcyBhY3RpdmVseSBydW5uaW5nIE5PVyAtPiBCVVNZIC0+IG5ldmVyIGEgZmFsc2UgbnVkZ2UKICAgIGQgPSBfc3RhdHVzX2ZvcihhZ2VudF9pZCkKICAgIGlmIG5vdCBkOiByZXR1cm4gSURMRV9TVEFMTCArIDEgICAgICAgICAgICAgICAgICAgICAgICAgIyBubyBzdGF0dXMgLT4gY2FuJ3QgY29uZmlybSBhY3RpdmUgLT4gc3RhbGxlZAogICAgaWYgZC5nZXQoInN0YXR1cyIpICE9ICJpZGxlIjogcmV0dXJuIE5vbmUgICAgICAgICAgICAgICMgZXhwbGljaXRseSBidXN5CiAgICB0ID0gX2lzb19lcG9jaChkLmdldCgidGltZXN0YW1wIiwgIiIpKQogICAgaWRsZV9mb3IgPSAodGltZS50aW1lKCkgLSB0KSBpZiB0IGVsc2UgSURMRV9TVEFMTCArIDEKICAgIGFnZSA9IF9zZXNzaW9uX2FnZShhZ2VudF9pZCkgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHJlc3Bhd24tYXdhcmU6IGEgZnJlc2hseSByZS1zcGF3bmVkIGFnZW50CiAgICBpZiBhZ2UgaXMgbm90IE5vbmU6IGlkbGVfZm9yID0gbWluKGlkbGVfZm9yLCBhZ2UpICAgICAgIyBjYW4ndCBoYXZlIGJlZW4gaWRsZSBsb25nZXIgdGhhbiBpdHMgbGl2ZSBzZXNzaW9uIGV4aXN0cwogICAgaWYgaWRsZV9mb3IgPCBJRExFX1NUQUxMOiByZXR1cm4gTm9uZSAgICAgICAgICAgICAgICAgICMgcmVjZW50bHkgc3RvcHBlZC9yZXNwYXduZWQgLT4gZ3JhY2UKICAgIGlmIF9zZXNzaW9uX2FjdGl2ZV93aXRoaW4oZC5nZXQoInNlc3Npb25faWQiKSwgSURMRV9TVEFMTCk6IHJldHVybiBOb25lICAjIHRyYW5zY3JpcHQgbW92aW5nIC0+IGJ1c3kgdHVybgogICAgaWYgYWdlbnRfYnVzeShhZ2VudF9pZCk6IHJldHVybiBOb25lICAgICAgICAgICAgICAgICAgICMgbG9uZy1ydW5uaW5nIGpvYiBpbiBpdHMgcHJvY2VzcyB0cmVlIC0+IGJ1c3kKICAgIHJldHVybiBpZGxlX2ZvcgoKZGVmIHdhdGNoZG9nX2xvb3AoKToKICAgIHdoaWxlIFRydWU6CiAgICAgICAgdGltZS5zbGVlcChXQVRDSERPRykKICAgICAgICBmb3IgdGlkIGluIGxpc3QobG9hZCgpLmdldCgidGFza3MiLCB7fSkua2V5cygpKToKICAgICAgICAgICAgcGluZyA9IE5vbmUKICAgICAgICAgICAgd2l0aCBfbG9jazoKICAgICAgICAgICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldCh0aWQpCiAgICAgICAgICAgICAgICBpZiBub3QgdCBvciBfaXNfdGVzdCh0KSBvciBub3QgKHQuZ2V0KCJ3b3JrVG9Eb25lIikgYW5kIHQuZ2V0KCJzdGF0ZSIpID09ICJ3b3JraW5nIiBhbmQgdC5nZXQoImFzc2lnbmVlIikpOgogICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlICAgICAgICAgICMgdGVzdC9kZW1vIGZpeHR1cmVzIG5ldmVyIHRyaWdnZXIgdGhlIHN0YWxsIHdhdGNoZG9nCiAgICAgICAgICAgICAgICBpZGxlID0gYXNzaWduZWVfaWRsZV9zZWNzKHRbImFzc2lnbmVlIl0pCiAgICAgICAgICAgICAgICBpZiBpZGxlIGlzIE5vbmU6CiAgICAgICAgICAgICAgICAgICAgaWYgdC5nZXQoInN0YWxsUGluZ1RzIik6ICAgICAgICAgICAgICAgICMgYWdlbnQgcmVjb3ZlcmVkIC0+IHJlc2V0IHNvIG5leHQgc3RhbGwgcmUtcGluZ3MKICAgICAgICAgICAgICAgICAgICAgICAgdFsic3RhbGxQaW5nVHMiXSA9IDA7IHNhdmUoYikKICAgICAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICAgICAgaWYgKHRpbWUudGltZSgpIC0gKHQuZ2V0KCJzdGFsbFBpbmdUcyIpIG9yIDApKSA+PSBTVEFMTF9SRVBJTkc6CiAgICAgICAgICAgICAgICAgICAgdFsic3RhbGxQaW5nVHMiXSA9IHRpbWUudGltZSgpOyBzYXZlKGIpCiAgICAgICAgICAgICAgICAgICAgcGluZyA9ICh0WyJhc3NpZ25lZSJdLCBpbnQoaWRsZSAvLyA2MCkpCiAgICAgICAgICAgIGlmIHBpbmc6CiAgICAgICAgICAgICAgICBib3NzX3BpbmcodGlkLCBmIldBVENIRE9HOiBhc3NpZ25lZSB7cGluZ1swXX0gSURMRS9zdGFsbGVkIH57cGluZ1sxXX1tIGF0IHByb21wdCAiCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBmIihubyBhY3Rpdml0eSkg4oCUIHJlLWVuZ2FnZSBvciByZWFzc2lnbiIpCgojIOKUgOKUgCBtdXRhdGlvbnMg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmRlZiBhcHBseV91cGRhdGUoZCk6CiAgICBvcCA9IGQuZ2V0KCJvcCIpCiAgICByZXRpcmUgPSBOb25lICAgICAgICAgICAgICAgICAgICAgICAjIChwcmV2X3N0YXRlLCB0YXNrX3NuYXBzaG90KSBzZXQgb24gYSBnZW51aW5lIOKGkmRvbmUgdHJhbnNpdGlvbjsgcnVuIGFmdGVyIHRoZSBsb2NrCiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCkKICAgICAgICBpZiBvcCA9PSAiYWRkIjoKICAgICAgICAgICAgdCA9IG5ld190YXNrKGQuZ2V0KCJ0ZXh0IiwgIiIpKTsgdFsidGVzdCJdID0gYm9vbChkLmdldCgidGVzdCIpKSBvciBfaXNfdGVzdCh0KQogICAgICAgICAgICBpZiBkLmdldCgicGFyZW50IikgYW5kIGRbInBhcmVudCJdIGluIGJbInRhc2tzIl06ICAgIyBpc3N1ZSAjMzogY3JlYXRlIGRpcmVjdGx5IGFzIGEgc3VidGFzayBvZiBhbiBleGlzdGluZyBjYXJkCiAgICAgICAgICAgICAgICB0WyJwYXJlbnQiXSA9IGRbInBhcmVudCJdCiAgICAgICAgICAgIGJbInRhc2tzIl1bdFsiaWQiXV0gPSB0OyBiWyJvcmRlciJdLmluc2VydCgwLCB0WyJpZCJdKQogICAgICAgICAgICBzYXZlKGIpCiAgICAgICAgICAgICMgYSBjcmVhdGVkIHRhc2sgbXVzdCBORVZFUiBzaWxlbnRseSBkaWU6IHBpbmcgdGhlIEJvc3Mgb24gY3JlYXRlIHNvIGl0J3MgdHJpYWdlZC9icmFpbnN0b3JtZWQKICAgICAgICAgICAgIyDigJQgVU5MRVNTIGl0J3MgYSB0ZXN0L2RlbW8vcHJvb2YgZml4dHVyZSAoZXhlbXB0OiBubyBCb3NzIG51ZGdlKS4KICAgICAgICAgICAgaWYgbm90IF9pc190ZXN0KHQpOgogICAgICAgICAgICAgICAgYm9zc19waW5nKHRbImlkIl0sICJuZXcgdGFzayBjcmVhdGVkIOKAlCBicmFpbnN0b3JtICsgdHJpYWdlIGl0IChubyB3b3JrLXRvLWRvbmUgdG9nZ2xlIG5lZWRlZCBmb3IgaXQgdG8gYmUgc2VlbikiKQogICAgICAgICAgICByZXR1cm4geyJvayI6IFRydWUsICJpZCI6IHRbImlkIl19CiAgICAgICAgdGlkID0gZC5nZXQoImlkIik7IHQgPSBiWyJ0YXNrcyJdLmdldCh0aWQpCiAgICAgICAgaWYgbm90IHQ6IHJldHVybiB7ImVycm9yIjogIm5vIHN1Y2ggdGFzayJ9CiAgICAgICAgaWYgb3AgPT0gImRlbCI6CiAgICAgICAgICAgIGJbInRhc2tzIl0ucG9wKHRpZCwgTm9uZSk7IGJbIm9yZGVyIl0gPSBbeCBmb3IgeCBpbiBiWyJvcmRlciJdIGlmIHggIT0gdGlkXQogICAgICAgICAgICBzYXZlKGIpOyByZXR1cm4geyJvayI6IFRydWV9CiAgICAgICAgaWYgb3AgPT0gInJlb3JkZXIiOgogICAgICAgICAgICBiWyJvcmRlciJdID0gW3ggZm9yIHggaW4gZC5nZXQoIm9yZGVyIiwgW10pIGlmIHggaW4gYlsidGFza3MiXV0KICAgICAgICAgICAgc2F2ZShiKTsgcmV0dXJuIHsib2siOiBUcnVlfQogICAgICAgIGlmIG9wID09ICJhZGRzdWIiOgogICAgICAgICAgICB0WyJzdWJzIl0uYXBwZW5kKHsiaWQiOiB1aWQoKSwgInRleHQiOiBkLmdldCgidGV4dCIsICIiKSwgImRvbmUiOiBGYWxzZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgImRvbmVDb25kaXRpb24iOiBkLmdldCgiZG9uZUNvbmRpdGlvbiIsICIiKSwgImNyZWF0ZWQiOiBub3coKX0pCiAgICAgICAgICAgIHRbInVwZGF0ZWQiXSA9IG5vdygpOyBzYXZlKGIpOyByZXR1cm4geyJvayI6IFRydWV9CiAgICAgICAgaWYgb3AgPT0gInNldCI6CiAgICAgICAgICAgIGJvc3NfZW5xdWV1ZWQgPSBGYWxzZQogICAgICAgICAgICBpZiAiZG9uZUNvbmRpdGlvbiIgaW4gZDogdFsiZG9uZUNvbmRpdGlvbiJdID0gZFsiZG9uZUNvbmRpdGlvbiJdCiAgICAgICAgICAgIGlmICJ0ZXh0IiBpbiBkOiB0WyJ0ZXh0Il0gPSBkWyJ0ZXh0Il0KICAgICAgICAgICAgaWYgImFzc2lnbmVlIiBpbiBkOgogICAgICAgICAgICAgICAgdFsiYXNzaWduZWUiXSA9IGRbImFzc2lnbmVlIl07IHRbImFzc2lnbmVkQXQiXSA9IG5vdygpIGlmIGRbImFzc2lnbmVlIl0gZWxzZSBOb25lCiAgICAgICAgICAgIGlmICJwYXJlbnQiIGluIGQ6ICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgaXNzdWUgIzM6IHBhcmVudC9jaGlsZCBoaWVyYXJjaHkKICAgICAgICAgICAgICAgIHBpZCA9IGRbInBhcmVudCJdIG9yIE5vbmUKICAgICAgICAgICAgICAgIGlmIHBpZCBhbmQgKHBpZCBub3QgaW4gYlsidGFza3MiXSBvciBwaWQgPT0gdGlkIG9yIF9jcmVhdGVzX2N5Y2xlKGIsIHRpZCwgcGlkKSk6CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiAiaW52YWxpZCBwYXJlbnQgKG1pc3NpbmcsIHNlbGYsIG9yIHdvdWxkIGNyZWF0ZSBhIGN5Y2xlKSJ9CiAgICAgICAgICAgICAgICB0WyJwYXJlbnQiXSA9IHBpZAogICAgICAgICAgICBpZiAiZGVwZW5kc09uIiBpbiBkOiAgICAgICAgICAgICAgICAgICAgICAgICAjIGlzc3VlICMzOiAnYmxvY2tlZCBieScgbGlua3MgKGV4aXN0aW5nIGNhcmRzLCBuZXZlciBzZWxmKQogICAgICAgICAgICAgICAgdFsiZGVwZW5kc09uIl0gPSBbeCBmb3IgeCBpbiAoZFsiZGVwZW5kc09uIl0gb3IgW10pIGlmIHggaW4gYlsidGFza3MiXSBhbmQgeCAhPSB0aWRdCiAgICAgICAgICAgIGlmICJoYXJkR2F0ZSIgaW4gZDogICAgICAgICAgICAgICAgICAgICAgICAgICMgaXNzdWUgIzM6IHBlci1jYXJkIGhhcmQgZ2F0ZSAoT0ZGIGJ5IGRlZmF1bHQpCiAgICAgICAgICAgICAgICB0WyJoYXJkR2F0ZSJdID0gYm9vbChkWyJoYXJkR2F0ZSJdKQogICAgICAgICAgICBpZiBkLmdldCgid29ya1RvRG9uZSIpIGlzIFRydWU6CiAgICAgICAgICAgICAgICBpZiBub3QgKHQuZ2V0KCJkb25lQ29uZGl0aW9uIikgb3IgIiIpLnN0cmlwKCk6CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiAiZG9uZUNvbmRpdGlvbiByZXF1aXJlZCBiZWZvcmUgd29ya1RvRG9uZSJ9CiAgICAgICAgICAgICAgICB3YXNfb24gPSBib29sKHQuZ2V0KCJ3b3JrVG9Eb25lIikpICAgICAgICAgIyBvbmx5IHBpbmcgb24gYSByZWFsIE9GRi0+T04gdHJhbnNpdGlvbiAoaWRlbXBvdGVudCBPTiA9IG5vIGR1cGxpY2F0ZSBwaW5nOyBjb21wbGVtZW50cyB0aGUgY2xpZW50IDUwMG1zIGRlYm91bmNlKQogICAgICAgICAgICAgICAgdFsid29ya1RvRG9uZSJdID0gVHJ1ZQogICAgICAgICAgICAgICAgIyBTSUxFTlQtTk8tT1AgRklYIChzbGljZSBkKTogdGhlIGRpc3BhdGNoZXIgb25seSBhY3RzIG9uIHN0YXRlPT0nd29ya2luZycuIEEKICAgICAgICAgICAgICAgICMgbmVlZHNfYnJhaW5zdG9ybSBjYXJkIHdpdGggd29yay10by1kb25lIE9OIHdvdWxkIG90aGVyd2lzZSBzaXQgc2lsZW50LiBTdXJmYWNlIGl0CiAgICAgICAgICAgICAgICAjICh2aXNpYmxlIGxhc3RTdGF0dXMgKyBhIGRpc3RpbmN0IEJvc3MgcGluZykgaW5zdGVhZCBvZiBkb2luZyBub3RoaW5nLgogICAgICAgICAgICAgICAgaWYgdFsic3RhdGUiXSA9PSAibmVlZHNfYnJhaW5zdG9ybSI6CiAgICAgICAgICAgICAgICAgICAgdFsibGFzdFN0YXR1cyJdID0gIm5lZWRzIGJyYWluc3Rvcm0gZmlyc3Qg4oCUIHdvcmstdG8tZG9uZSBpcyBPTiBidXQgdGhpcyB0YXNrIHdvbid0IGJlIHdvcmtlZCB1bnRpbCBpdCdzIGJyYWluc3Rvcm1lZC9hbnN3ZXJlZCBhbmQgcHJvbW90ZWQgdG8gd29ya2luZyIKICAgICAgICAgICAgICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgICAgICAgICAgICAgIGlmIG5vdCB3YXNfb246IGJvc3NfcGluZyh0aWQsICJ3b3JrLXRvLWRvbmUgT04gYnV0IHRhc2sgTkVFRFMgQlJBSU5TVE9STSDigJQgbm90IHdvcmthYmxlIHlldDsgc3VyZmFjZSBxdWVzdGlvbnMgdG8gdGhlIENFTyIpOyBib3NzX2VucXVldWVkID0gbm90IHdhc19vbgogICAgICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgICAgICAgICAgICAgIGlmIG5vdCB3YXNfb246IGJvc3NfcGluZyh0aWQsICJ3b3JrLXRvLWRvbmUgdG9nZ2xlZCBPTiDigJQgZHJpdmUgdG8gZG9uZSIpOyBib3NzX2VucXVldWVkID0gbm90IHdhc19vbgogICAgICAgICAgICAgICAgYiA9IGxvYWQoKTsgdCA9IGJbInRhc2tzIl1bdGlkXQogICAgICAgICAgICBlbGlmIGQuZ2V0KCJ3b3JrVG9Eb25lIikgaXMgRmFsc2U6CiAgICAgICAgICAgICAgICB0WyJ3b3JrVG9Eb25lIl0gPSBGYWxzZQogICAgICAgICAgICBpZiAic3RhdGUiIGluIGQ6CiAgICAgICAgICAgICAgICBpZiBkWyJzdGF0ZSJdIG5vdCBpbiBWQUxJRF9TVEFURVM6CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiBmImludmFsaWQgc3RhdGUge2RbJ3N0YXRlJ10hcn0gKGFsbG93ZWQ6IHtzb3J0ZWQoVkFMSURfU1RBVEVTKX0pIn0KICAgICAgICAgICAgICAgIGlmIGRbInN0YXRlIl0gPT0gImRvbmUiOiAgICAgICAgICAgICAgICAgIyBSdWxlIDIxOiBvbmx5IHRoZSBDRU8gbWFya3MgZG9uZSAob25lIGNsaWNrLCBhbnkgc3RhdGUpOyBBSSAtPiByZXZpZXcgbWF4CiAgICAgICAgICAgICAgICAgICAgaWYgc3RyKGQuZ2V0KCJieSIsICIiKSkuc3RyaXAoKS51cHBlcigpID09ICJDRU8iOgogICAgICAgICAgICAgICAgICAgICAgICB0WyJ2ZXJpZmllZCJdID0gVHJ1ZQogICAgICAgICAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogIm9ubHkgdGhlIENFTyBtYXJrcyBkb25lIChBSS9lbmdpbmVlciBjYW4gbW92ZSB1cCB0byAncmV2aWV3JywgbmV2ZXIgJ2RvbmUnKSJ9CiAgICAgICAgICAgICAgICBpZiBkWyJzdGF0ZSJdID09ICJ3b3JraW5nIiBhbmQgdFsic3RhdGUiXSA9PSAibmVlZHNfYnJhaW5zdG9ybSI6CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiAibm90IHdvcmthYmxlIGJlZm9yZSBicmFpbnN0b3JtIChicmFpbnN0b3JtIGdhdGUpIn0KICAgICAgICAgICAgICAgIF9nID0gc3RhdGVfZ2F0ZShiLCB0LCBkWyJzdGF0ZSJdKSAgICAgICAgIyBpc3N1ZSAjMzogc3VidGFzay9kZXBlbmRlbmN5ICsgaGFyZC1nYXRlIGd1YXJkcmFpbHMKICAgICAgICAgICAgICAgIGlmIF9nOiByZXR1cm4geyJlcnJvciI6IF9nfQogICAgICAgICAgICAgICAgaWYgZFsic3RhdGUiXSAhPSB0WyJzdGF0ZSJdOgogICAgICAgICAgICAgICAgICAgIGFkZF9jb21tZW50KHQsIGYic3RhdGU6IHt0WydzdGF0ZSddfSDihpIge2RbJ3N0YXRlJ119IiwgZC5nZXQoImJ5Iikgb3IgInN5c3RlbSIsICJzdGF0ZSIpCiAgICAgICAgICAgICAgICBfcHJldl9zdGF0ZSA9IHRbInN0YXRlIl0KICAgICAgICAgICAgICAgIHRbInN0YXRlIl0gPSBkWyJzdGF0ZSJdCiAgICAgICAgICAgICAgICBpZiBkWyJzdGF0ZSJdID09ICJkb25lIiBhbmQgX3ByZXZfc3RhdGUgIT0gImRvbmUiOiAgICMgZ2VudWluZSBDRU8g4oaSZG9uZSB0cmFuc2l0aW9uIOKGkiByZXRpcmUgdGhlIGFzc2lnbmVlIGFmdGVyIHRoZSBsb2NrCiAgICAgICAgICAgICAgICAgICAgcmV0aXJlID0gKF9wcmV2X3N0YXRlLCBkaWN0KHQpKQogICAgICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgICAgICByZXMgPSB7Im9rIjogVHJ1ZSwgImJvc3NFbnF1ZXVlZCI6IGJvc3NfZW5xdWV1ZWR9CiAgICAgICAgZWxzZToKICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiBmInVua25vd24gb3Age29wIXJ9In0KICAgIGlmIHJldGlyZTogcmV0aXJlX29uX2RvbmUocmV0aXJlWzBdLCByZXRpcmVbMV0pICAgIyBPVVRTSURFIF9sb2NrOiBydW5zIGBtcCBraWxsYCwgZXZlbnRzIHRoZSBCb3NzLCB0aHJlYWRzIHRoZSBjYXJkCiAgICByZXR1cm4gcmVzCgpkZWYgX21wX3NlbmQoYWdlbnQsIG1zZyk6CiAgICAiIiJSZWxheSBhIG1lc3NhZ2UgdG8gYW4gYWdlbnQgdmlhIGBtcCBzZW5kYCAoY2hhaW4gb2YgY29tbWFuZCkuIEFsd2F5cyBhdWRpdC1sb2dzIHRvIHRoZSBib3NzCiAgICBpbmJveDsgZG9lcyB0aGUgcmVhbCBzZW5kIHdoZW4gbGl2ZSAobm90IFRFU1RfU0lOSyArIG1wIG9uIFBBVEgpLiBSZXR1cm5zIFRydWUgaWYgc2VudCBsaXZlLiIiIgogICAgdHJ5OgogICAgICAgIElOQk9YX0xPRy5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgICAgIHdpdGggSU5CT1hfTE9HLm9wZW4oImEiKSBhcyBmOiBmLndyaXRlKGYie25vdygpfSBNUF9TRU5EIC0+IHthZ2VudH0gOjoge21zZ1s6MjAwXX1cbiIpCiAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXNzCiAgICBpZiBub3QgVEVTVF9TSU5LIGFuZCBzaHV0aWwud2hpY2goIm1wIik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oWyJtcCIsICJzZW5kIiwgYWdlbnQsIG1zZ10sIGNhcHR1cmVfb3V0cHV0PVRydWUsIHRleHQ9VHJ1ZSwgdGltZW91dD0zMCkKICAgICAgICAgICAgcmV0dXJuIHIucmV0dXJuY29kZSA9PSAwCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIEZhbHNlCiAgICByZXR1cm4gRmFsc2UKCiMg4pSA4pSAIEFVVE8tUkVUSVJFIChjYXJkIDY5MzRlNTIwYjc5MSk6IHdoZW4gdGhlIENFTyBtYXJrcyBhIHRhc2sgRE9ORSwgdGhlIGVuZ2luZWVyIHRoYXQgd2FzCiMgYXNzaWduZWQgdG8gaXQgaGFzIGZpbmlzaGVkIGl0cyBqb2Ig4oCUIHJldGlyZSBpdCAobXAga2lsbCkgc28gaXQgc3RvcHMgY2h1cm5pbmcuIFRoaXMgaXMgdGhlCiMgcmV0aXJlbWVudCBUUklHR0VSLCBmaXJlZCBPTkxZIG9uIGEgZ2VudWluZSB0cmFuc2l0aW9uIElOVE8gJ2RvbmUnIChSdWxlIDIxOiBDRU8tb25seSkuCiMgU2VydmVyLWRpcmVjdCBraWxsIChkZXRlcm1pbmlzdGljICsgZGlyZWN0bHkgdmVyaWZpYWJsZSwgc2FtZSBtZWNoYW5pc20gYXMgYm9zc19waW5nL19tcF9zZW5kKSwKIyBQTFVTIGEgc3RydWN0dXJlZCBldmVudCB0byB0aGUgQm9zcyBzbyB0aGUgQm9zcyBrbm93cyB0aGUgdGFzayBmaW5pc2hlZCArIHdobyB3YXMgcmV0aXJlZC4KIyBFZGdlIGNhc2VzOiBvbmx5IG9uIOKGkmRvbmUgKGNhbGxlciBwYXNzZXMgcHJldl9zdGF0ZSk7IG5vIGFzc2lnbmVlIOKGkiBuby1vcDsgbmV2ZXIgdGFyZ2V0cyBhCiMgbm9uLWFzc2lnbmVlICh3ZSBvbmx5IGV2ZXIgcGFzcyB0Wydhc3NpZ25lZSddKTsgYWxyZWFkeS1kZWFkIGVuZ2luZWVyIOKGkiBtcCBraWxsIGZhaWxzL3RpbWVvdXRzLAojIHdlIGNhdGNoICsgbG9nICJhbHJlYWR5IHJldGlyZWQgKG5vLW9wKSIgYW5kIE5FVkVSIGZhaWwgdGhlIERPTkUgd3JpdGUuCmRlZiByZXRpcmVfb25fZG9uZShwcmV2X3N0YXRlLCB0KToKICAgICMgTXVzdCBiZSBjYWxsZWQgT1VUU0lERSBfbG9jayAoaXQgcnVucyBzbG93IGBtcGAgc3VicHJvY2Vzc2VzIGFuZCByZWxvYWRzL3NhdmVzIG9uIGl0cyBvd24pLgogICAgaWYgcHJldl9zdGF0ZSA9PSAiZG9uZSI6ICAgICAgICAgICAgIyBub3QgYSByZWFsIHRyYW5zaXRpb24gKHJlLXNhdmUgb2YgYW4gYWxyZWFkeS1kb25lIGNhcmQpCiAgICAgICAgcmV0dXJuCiAgICBhc3NpZ25lZSA9ICh0LmdldCgiYXNzaWduZWUiKSBvciAiIikuc3RyaXAoKQogICAgdGlkID0gdC5nZXQoImlkIiwgIj8iKQogICAgZGVmIF9sb2cobGluZSk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBJTkJPWF9MT0cucGFyZW50Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgICAgICAgICAgd2l0aCBJTkJPWF9MT0cub3BlbigiYSIpIGFzIGY6IGYud3JpdGUoZiJ7bm93KCl9IHtsaW5lfVxuIikKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXNzCiAgICBpZiBub3QgYXNzaWduZWU6ICAgICAgICAgICAgICAgICAgICAjIG5vdGhpbmcgYXNzaWduZWQg4oaSIG5vdGhpbmcgdG8gcmV0aXJlIChjbGVhbiBuby1vcCkKICAgICAgICBfbG9nKGYiUkVUSVJFIHRhc2sge3RpZH0gbWFya2VkIERPTkUgYnV0IGhhZCBubyBhc3NpZ25lZSDigJQgbm8tb3AiKQogICAgICAgIHJldHVybgogICAga2lsbGVkID0gRmFsc2U7IGRldGFpbCA9ICIiCiAgICBpZiBub3QgVEVTVF9TSU5LIGFuZCBzaHV0aWwud2hpY2goIm1wIik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICByID0gc3VicHJvY2Vzcy5ydW4oWyJtcCIsICJraWxsIiwgYXNzaWduZWVdLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9MTUpCiAgICAgICAgICAgIGtpbGxlZCA9IChyLnJldHVybmNvZGUgPT0gMCkKICAgICAgICAgICAgZGV0YWlsID0gKHIuc3Rkb3V0IG9yIHIuc3RkZXJyIG9yICIiKS5zdHJpcCgpWzoxNjBdCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgICAgICBkZXRhaWwgPSBmImV4Y2VwdGlvbiB7ZX0iICAgICAgICAgICMgYWxyZWFkeS1kZWFkIGhvc3QvYWdlbnQg4oaSIHRpbWVvdXQvZXJyOiBjbGVhbiBuby1vcAogICAgZWxzZToKICAgICAgICBkZXRhaWwgPSAiVEVTVF9TSU5LL25vLW1wIOKAlCBraWxsIHNraXBwZWQgKGF1ZGl0IG9ubHkpIgogICAgbm90ZSA9ICJyZXRpcmVkIiBpZiBraWxsZWQgZWxzZSAia2lsbCBuby1vcCAoYWxyZWFkeSBkZWFkIC8gdW5yZWFjaGFibGUpIgogICAgX2xvZyhmIlJFVElSRSB0YXNrIHt0aWR9IERPTkUgLT4gbXAga2lsbCB7YXNzaWduZWV9IDo6IHtub3RlfSA6OiB7ZGV0YWlsfSIpCiAgICAjIHRlbGwgdGhlIEJvc3MgdGhlIHRhc2sgZmluaXNoZWQgKyB3aG8gd2FzIHJldGlyZWQgKHRoZSBDRU8ncyAic2VuZCBhbiBldmVudCB0byB0aGUgYm9zcyIgaW50ZW50KQogICAgX21wX3NlbmQoQk9TU19BR0VOVCwgZiJbdG9kb10gdGFzayB7dGlkfSBtYXJrZWQgRE9ORSBieSBDRU8g4oCUIGF1dG8tcmV0aXJlZCBhc3NpZ25lZSB7YXNzaWduZWV9ICh7bm90ZX0pLiIpCiAgICAjIHRocmVhZCB0aGUgcmV0aXJlbWVudCBpbnRvIHRoZSBjYXJkJ3MgZHVyYWJsZSBoaXN0b3J5IGZvciB0aGUgQ0VPJ3MgdmlzaWJpbGl0eSAob3duIHNob3J0IGxvY2spCiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCk7IGN0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIGN0OgogICAgICAgICAgICBhZGRfY29tbWVudChjdCwgZiJhdXRvLXJldGlyZTogZW5naW5lZXIge2Fzc2lnbmVlfSB7bm90ZX0gKHRhc2sgbWFya2VkIERPTkUpIiwgInN5c3RlbSIsICJzdGF0dXMiKQogICAgICAgICAgICBjdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikKCmRlZiBhcHBseV9jb21tZW50KGQpOgogICAgIiIiQXBwZW5kIGEgY29tbWVudCB0byBhIHRhc2sncyB0aHJlYWQgKHNsaWNlIGIpIEFORCBtYWtlIGl0IGEgdHdvLXdheSBjaGFubmVsLgogICAgQ0hBSU4gT0YgQ09NTUFORDogYSBDRU8gY29tbWVudCBpcyByZWxheWVkIHRvIHRoZSBCT1NTICh3aG8gcmVkaXJlY3RzIHRvIHRoZSByaWdodCBlbmdpbmVlcikg4oCUCiAgICBuZXZlciBDRU/ihpJlbmdpbmVlciBkaXJlY3RseS4gRW5naW5lZXIvQUkgcmVwbGllcyAoYnk9PGFnZW50IGlkPikgdGhyZWFkIGJhY2sgaW50byB0aGUgY2FyZCBmb3IKICAgIHRoZSBDRU8ncyB2aXNpYmlsaXR5IChhIHJlYWwgdHdvLXdheSBHaXRIdWItaXNzdWUgY29udmVyc2F0aW9uKSBBTkQgbm93IEFMU08gcGluZyB0aGUgQm9zcywgc28KICAgIHRoZSBCb3NzIHNlZXMgY2FyZCBhY3Rpdml0eSBpbiByZWFsIHRpbWUgaW5zdGVhZCBvZiBzdXBlcnZpc2luZyBibGluZCBvZmYgbXAgcmVwb3J0cy4gR3VhcmRlZAogICAgYWdhaW5zdCBub2lzZTogdGhlIEJvc3MncyBPV04gY29tbWVudHMgYXJlIE5PVCByZWxheWVkIGJhY2sgdG8gaXRzZWxmIChubyBsb29wKSwgYW5kICdzeXN0ZW0nCiAgICBhdXRvLXBvc3RzIGRvbid0IHBpbmcuIENFTyBjb21tZW50cyBrZWVwIHRoZWlyIGV4aXN0aW5nIGNoYWluLW9mLWNvbW1hbmQgcmVsYXkgKG5vIGRvdWJsZS1waW5nKS4iIiIKICAgIHdpdGggX2xvY2s6CiAgICAgICAgYiA9IGxvYWQoKTsgdCA9IGJbInRhc2tzIl0uZ2V0KGQuZ2V0KCJ0YXNrX2lkIikgb3IgZC5nZXQoImlkIikpCiAgICAgICAgaWYgbm90IHQ6IHJldHVybiB7ImVycm9yIjogIm5vIHN1Y2ggdGFzayJ9CiAgICAgICAgYnkgPSBkLmdldCgiYnkiLCAiQ0VPIik7IGlzX2NlbyA9IHN0cihieSkudXBwZXIoKSA9PSAiQ0VPIgogICAgICAgIGMgPSBhZGRfY29tbWVudCh0LCBkLmdldCgiYm9keSIsICIiKSwgYnksICJjb21tZW50IikKICAgICAgICBpZiBub3QgYzogcmV0dXJuIHsiZXJyb3IiOiAiZW1wdHkgY29tbWVudCJ9CiAgICAgICAgIyBDT01NRU5ULU9OLVJFVklFVyA9IE1PUkUgV09SSzogYSBDRU8gY29tbWVudCBvbiBhICdyZXZpZXcnIGNhcmQgbWVhbnMgd29yayByZW1haW5zLCBzbyBpdAogICAgICAgICMgYXV0by1raWNrcyBiYWNrIHJldmlldyAtPiB3b3JraW5nLiBFZGdlLWNhc2UgcG9saWN5OgogICAgICAgICMgIChhKSBPTkxZICdyZXZpZXcnIGF1dG8ta2lja3MuIHdvcmtpbmcgc3RheXMgd29ya2luZyAvIG5lZWRzX2JyYWluc3Rvcm0gc3RheXMgZ2F0ZWQgLwogICAgICAgICMgICAgICBibG9ja2VkIHN0YXlzIGJsb2NrZWQgLyBkb25lIHN0YXlzIGRvbmUg4oCUIGJ1dCB0aGUgY29tbWVudCBTVElMTCByZWxheXMgdG8gdGhlIEJvc3MgaW4KICAgICAgICAjICAgICAgZXZlcnkgY2FzZSAod2UgbmV2ZXIgbG9zZSB0aGUgcmVsYXkpLiBOb24tcmV2aWV3IHN0YXRlcyBhcmVuJ3QgZm9yY2UtbW92ZWQgKGF2b2lkCiAgICAgICAgIyAgICAgIGJ5cGFzc2luZyB0aGUgYnJhaW5zdG9ybSBnYXRlIG9yIHNpbGVudGx5IHJlb3BlbmluZyBhIGRvbmUgY2FyZDsgdXNlIHRoZSBzdGF0dXMgY29udHJvbCkuCiAgICAgICAgIyAgKGIpIE9OTFkgdGhlIENFTydzIGNvbW1lbnQga2lja3Mg4oCUIGFuIGVuZ2luZWVyL0FJIHN0YXR1cyBwb3N0IChieSAhPSBDRU8pIG5ldmVyIGNoYW5nZXMgc3RhdGUuCiAgICAgICAgIyAgKGMpIHRoZSByZWxheSB0byB0aGUgQm9zcyBoYXBwZW5zIHdoZXRoZXIgb3Igbm90IGl0IGtpY2tlZCAoc2VlIGJlbG93KS4KICAgICAgICAjICAoZCkgbm8gdGhyYXNoOiBvbmNlIGtpY2tlZCBpdCdzICd3b3JraW5nJyAobm90ICdyZXZpZXcnKSwgc28gZnVydGhlciBjb21tZW50cyBkb24ndCByZS1raWNrLgogICAgICAgIGtpY2tlZCA9IGlzX2NlbyBhbmQgdC5nZXQoInN0YXRlIikgPT0gInJldmlldyIKICAgICAgICBpZiBraWNrZWQ6CiAgICAgICAgICAgIGFkZF9jb21tZW50KHQsICJzdGF0ZTogcmV2aWV3IOKGkiB3b3JraW5nIiwgYnksICJzdGF0ZSIpCiAgICAgICAgICAgIHRbInN0YXRlIl0gPSAid29ya2luZyIKICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgIHRpZCA9IHRbImlkIl07IHRpdGxlID0gKHQuZ2V0KCJ0ZXh0Iikgb3IgIiIpWzo3MF07IGFzc2lnbmVlID0gdC5nZXQoImFzc2lnbmVlIik7IGJvZHkgPSBjWyJib2R5Il0KICAgIHJvdXRlZCA9IE5vbmUKICAgIHdoZXJlID0gZiJhc3NpZ25lZDoge2Fzc2lnbmVlfSIgaWYgYXNzaWduZWUgZWxzZSAiVU5BU1NJR05FRCDigJQgYXNzaWduICsgcmVsYXkiCiAgICBpZiBpc19jZW86ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgcmVsYXkgdG8gdGhlIEJvc3MgKG91dHNpZGUgdGhlIGxvY2spCiAgICAgICAga2ljayA9ICIgW2NhcmQga2lja2VkIHJldmlld+KGkndvcmtpbmcg4oCUIG1vcmUgd29yayBuZWVkZWRdIiBpZiBraWNrZWQgZWxzZSAiIgogICAgICAgIHNlbnQgPSBfbXBfc2VuZChCT1NTX0FHRU5ULCBmIltDRU8gY29tbWVudCBvbiBjYXJkIHt0aWR9IOKAnHt0aXRsZX3igJ0gKHt3aGVyZX0pXXtraWNrfToge2JvZHl9XG4iCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGYi4oaSIGNoYWluIG9mIGNvbW1hbmQ6IHJlbGF5IHRvIHRoZSByaWdodCBlbmdpbmVlciAoZG8gbm90IGV4cGVjdCB0aGUgQ0VPIHRvIHBpbmcgdGhlbSBkaXJlY3RseSkuIikKICAgICAgICByb3V0ZWQgPSBmImJvc3M6eydzZW50JyBpZiBzZW50IGVsc2UgJ2xvZ2dlZCd9IgogICAgZWxzZToKICAgICAgICAjIEVuZ2luZWVyL0FJIGNhcmQtY29tbWVudCDihpIgcGluZyB0aGUgQm9zcyBmb3IgcmVhbC10aW1lIHZpc2liaWxpdHkuIFNraXAgdGhlIEJvc3MncyBPV04KICAgICAgICAjIGNvbW1lbnRzICh0aGUgYXV0aG9yJ3MgdGFiIGlzICdCb3NzJywgb3IgaXQgZXF1YWxzIEJPU1NfQUdFTlQsIG9yIHRoZSBib2R5IGlzIGEgW0JPU1NdIG5vdGUpCiAgICAgICAgIyBzbyB3ZSBuZXZlciBsb29wIGEgQm9zcyBwb3N0IGJhY2sgdG8gaXRzZWxmOyBza2lwICdzeXN0ZW0nIGF1dG8tcG9zdHMgKGF1dG8tcmV0aXJlLCBldGMuKS4KICAgICAgICBfYnkgPSBzdHIoYnkpCiAgICAgICAgYXV0aG9yX2lzX2Jvc3MgPSAoX2J5ID09IEJPU1NfQUdFTlQpIG9yIChfYnkucnNwbGl0KCI6IiwgMSlbLTFdID09ICJCb3NzIikgb3IgYm9keS5sc3RyaXAoKS51cHBlcigpLnN0YXJ0c3dpdGgoIltCT1NTXSIpCiAgICAgICAgaWYgKG5vdCBhdXRob3JfaXNfYm9zcykgYW5kIF9ieS5sb3dlcigpICE9ICJzeXN0ZW0iOgogICAgICAgICAgICBzbmlwcGV0ID0gYm9keSBpZiBsZW4oYm9keSkgPD0gMzAwIGVsc2UgYm9keVs6Mjk5XSArICLigKYiCiAgICAgICAgICAgIHNlbnQgPSBfbXBfc2VuZChCT1NTX0FHRU5ULCBmIltjYXJkIHVwZGF0ZSBvbiB7dGlkfSDigJx7dGl0bGV94oCdIGJ5IHtfYnl9ICh7d2hlcmV9KV06IHtzbmlwcGV0fVxuIgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgZiLihpIgZW5naW5lZXIvQUkgcG9zdGVkIHRoaXMgb24gdGhlIGNhcmQgKENFTyBjYW4gc2VlIGl0KS4gU3VwZXJ2aXNlIOKAlCBmb2xsb3cgdXAgaWYgaXQgbmVlZHMgYWN0aW9uLiIpCiAgICAgICAgICAgIHJvdXRlZCA9IGYiYm9zczp7J3NlbnQnIGlmIHNlbnQgZWxzZSAnbG9nZ2VkJ30iCiAgICB3YV9yZWNvbmNpbGUoKSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgaWYgaXQgbGVmdCAncmV2aWV3JywgZHJvcCBpdCBmcm9tIHRoZSBDRU8gV2hhdHNBcHAgZGlnZXN0IChzbGljZSBlKQogICAgcmV0dXJuIHsib2siOiBUcnVlLCAiY29tbWVudF9pZCI6IGNbImlkIl0sICJyb3V0ZWQiOiByb3V0ZWQsICJraWNrZWQiOiBraWNrZWR9CgojIOKUgOKUgCBDTElDSy1USEUtTElOS0VELUVOR0lORUVSIOKGkiBBVFRBQ0ggKHNsaWNlIGMpIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAojIE1pcnJvciB0aGUgSFVEJ3MgYXR0YWNoIGV4YWN0bHk6IHRoZSBsaXZlIHRtdXggc2Vzc2lvbiBpcyBgbWMtPHNlc3Npb24+YCB3aW5kb3cgYDx0YWI+YCwgYW5kCiMgdGhlIGJyb3dzZXIgcmVhY2hlcyBpdCB2aWEgdHR5ZCBhdCBgPGF0dGFjaF9iYXNlPi8/YXJnPS10JmFyZz1tYy08c2Vzc2lvbj46PHRhYj5gLiBUaGUgcGVyLWhvc3QKIyB0dHlkIGBhdHRhY2hfYmFzZWAgaXMgYWR2ZXJ0aXNlZCBieSBlYWNoIHF1ZXVlLWNsaWVudCBhbmQgZXhwb3NlZCBvbiB0aGUgcXVldWUtc2VydmVyJ3MgL2NsaWVudHMKIyAoYSByZW1vdGUvSk9JTiBob3N0IGFkdmVydGlzZXMgaXRzIG93biB0YWlsbmV0IHR0eWQ7IHRoZSBsb2NhbCBIVUQgaG9zdCBoYXMgbm9uZSDihpIgdGhlIGNsaWVudAojIGZhbGxzIGJhY2sgdG8gaXRzIG93biBgPGxvY2F0aW9uLmhvc3RuYW1lPjo3NjgxYCkuIFdlIHJlc29sdmUgdGhlIGJhc2UgaGVyZSAoc2VydmVyLXNpZGUsIHNvIHRoZQojIHF1ZXVlIHNlY3JldCBuZXZlciByZWFjaGVzIHRoZSBicm93c2VyIGFuZCB0aGVyZSdzIG5vIGNyb3NzLW9yaWdpbiBmZXRjaCkgYW5kIGhhbmQgdGhlIGNsaWVudCB0aGUKIyB0bXV4IHRhcmdldCArIGJhc2U7IHRoZSBjbGllbnQgYXNzZW1ibGVzIHRoZSBmaW5hbCBVUkwgd2l0aCB0aGUgU0FNRSBsb2NhbGhvc3QgZmFsbGJhY2sgdGhlIEhVRCB1c2VzLgpfY2xpZW50c19jYWNoZSA9IHsidHMiOiAwLjAsICJkYXRhIjogW119CmRlZiBfcXVldWVfY2xpZW50cygpOgogICAgbm93dCA9IHRpbWUudGltZSgpCiAgICBpZiBub3d0IC0gX2NsaWVudHNfY2FjaGVbInRzIl0gPCA1IGFuZCBfY2xpZW50c19jYWNoZVsiZGF0YSJdOgogICAgICAgIHJldHVybiBfY2xpZW50c19jYWNoZVsiZGF0YSJdCiAgICB0cnk6CiAgICAgICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChRVUVVRV9VUkwgKyAiL2NsaWVudHMiLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgaGVhZGVycz17IlgtUXVldWUtU2VjcmV0IjogU0VDUkVUfSBpZiBTRUNSRVQgZWxzZSB7fSkKICAgICAgICB3aXRoIHVybGxpYi5yZXF1ZXN0LnVybG9wZW4ocmVxLCB0aW1lb3V0PTMpIGFzIHI6CiAgICAgICAgICAgIGRhdGEgPSBqc29uLmxvYWRzKHIucmVhZCgpIG9yIGIiW10iKQogICAgICAgIGlmIGlzaW5zdGFuY2UoZGF0YSwgbGlzdCk6CiAgICAgICAgICAgIF9jbGllbnRzX2NhY2hlWyJ0cyJdID0gbm93dDsgX2NsaWVudHNfY2FjaGVbImRhdGEiXSA9IGRhdGEKICAgICAgICAgICAgcmV0dXJuIGRhdGEKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwogICAgcmV0dXJuIF9jbGllbnRzX2NhY2hlWyJkYXRhIl0gb3IgW10KCmRlZiByZXNvbHZlX2F0dGFjaChhZ2VudF9pZCk6CiAgICAiIiJSZXNvbHZlIGFuIGFzc2lnbmVlIChgaG9zdC9zZXNzaW9uOnRhYmAgb3IgYHNlc3Npb246dGFiYCkgdG8ge3RhcmdldCwgYmFzZX0gZm9yIHR0eWQgYXR0YWNoLiIiIgogICAgYWdlbnRfaWQgPSAoYWdlbnRfaWQgb3IgIiIpLnN0cmlwKCkKICAgIGhvc3QsIHJlc3QgPSAoYWdlbnRfaWQuc3BsaXQoIi8iLCAxKSArIFsiIl0pWzoyXSBpZiAiLyIgaW4gYWdlbnRfaWQgZWxzZSAoTm9uZSwgYWdlbnRfaWQpCiAgICBpZiBub3QgcmVzdCBvciAiOiIgbm90IGluIHJlc3Q6CiAgICAgICAgcmV0dXJuIHsib2siOiBGYWxzZSwgImVycm9yIjogZiJ7YWdlbnRfaWQhcn0gaXMgbm90IGFuIGF0dGFjaGFibGUgYWdlbnQgKG5lZWQgaG9zdC9zZXNzaW9uOnRhYikifQogICAgc2Vzc2lvbiwgdGFiID0gcmVzdC5zcGxpdCgiOiIsIDEpCiAgICBpZiBub3Qgc2Vzc2lvbi5zdHJpcCgpIG9yIG5vdCB0YWIuc3RyaXAoKToKICAgICAgICByZXR1cm4geyJvayI6IEZhbHNlLCAiZXJyb3IiOiBmInthZ2VudF9pZCFyfSBpcyBub3QgYW4gYXR0YWNoYWJsZSBhZ2VudCAobmVlZCBob3N0L3Nlc3Npb246dGFiKSJ9CiAgICBiYXNlID0gIiIKICAgIGlmIGhvc3Q6CiAgICAgICAgZm9yIGMgaW4gX3F1ZXVlX2NsaWVudHMoKToKICAgICAgICAgICAgaWYgYy5nZXQoImhvc3RuYW1lIikgPT0gaG9zdDoKICAgICAgICAgICAgICAgIGJhc2UgPSAoYy5nZXQoImF0dGFjaF9iYXNlIikgb3IgIiIpLnN0cmlwKCk7IGJyZWFrCiAgICByZXR1cm4geyJvayI6IFRydWUsICJhZ2VudCI6IGFnZW50X2lkLCAiaG9zdCI6IGhvc3QsICJ0YXJnZXQiOiBmIm1jLXtzZXNzaW9ufTp7dGFifSIsICJiYXNlIjogYmFzZX0KCiMg4pSA4pSAIFdoYXRzQXBwIGxhc3QtaG9wIGRyYWluIChzbGljZSBlKTogb3V0Ym94ICsgcmVjb25jaWxlICsgZHJhaW4gcGFydGljaXBhbnQg4pSA4pSACmRlZiB3YV9sb2FkKCk6CiAgICB0cnk6CiAgICAgICAgZCA9IGpzb24ubG9hZHMoV0FfT1VUQk9YLnJlYWRfdGV4dCgpKQogICAgICAgIGlmIGlzaW5zdGFuY2UoZCwgZGljdCk6IGQuc2V0ZGVmYXVsdCgicXVldWUiLCBbXSk7IHJldHVybiBkCiAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXNzCiAgICByZXR1cm4geyJxdWV1ZSI6IFtdfQoKZGVmIHdhX3NhdmUoZCk6CiAgICBUT0RPX0RJUi5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICB0bXAgPSBXQV9PVVRCT1gud2l0aF9zdWZmaXgoIi50bXAiKTsgdG1wLndyaXRlX3RleHQoanNvbi5kdW1wcyhkLCBpbmRlbnQ9MikpOyB0bXAucmVwbGFjZShXQV9PVVRCT1gpCgpkZWYgX2Jsb2NrZWRfaXRlbXMoYik6CiAgICAiIiJDYXJkcyBibG9ja2VkIE9OIFRIRSBDRU8g4oaSIFsodGlkLCBraW5kLCB0aXRsZSwgZGV0YWlsKV0uIEJsb2NrZWQtb24tQ0VPIChhbGwg4oaSIFdoYXRzQXBwIHBpbmcpOgogICAgc3RhdGU9PXJldmlldyAoYXdhaXRpbmcgaGlzIERPTkUpIE9SIHN0YXRlPT1ibG9ja2VkIChjZW9HYXRlZCDigJQgYXdhaXRpbmcgYSBDRU8gZGVjaXNpb24vYW5zd2VycykgT1IKICAgIGEgbmVlZHNfYnJhaW5zdG9ybSBjYXJkIHdpdGggdW5hbnN3ZXJlZCBxdWVzdGlvbnMgKGF3YWl0aW5nIHRoZSBDRU8ncyBhbnN3ZXJzKS4iIiIKICAgIG91dCA9IFtdCiAgICBmb3IgdGlkIGluIGIuZ2V0KCJvcmRlciIsIGxpc3QoYlsidGFza3MiXS5rZXlzKCkpKToKICAgICAgICB0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIG5vdCB0IG9yIF9pc190ZXN0KHQpOiBjb250aW51ZSAgICAgICAgICAgICAgIyB0ZXN0L2RlbW8gZml4dHVyZXMgbmV2ZXIgZW50ZXIgdGhlIENFTyBXaGF0c0FwcCBkaWdlc3QKICAgICAgICB0aXRsZSA9ICh0LmdldCgidGV4dCIpIG9yICIiKS5zdHJpcCgpWzo4MF0gb3IgIih1bnRpdGxlZCkiCiAgICAgICAgc3QgPSB0LmdldCgic3RhdGUiKQogICAgICAgIHVhID0gWyhxLmdldCgicSIpIG9yICIiKS5zdHJpcCgpIGZvciBxIGluIHQuZ2V0KCJxdWVzdGlvbnMiLCBbXSkgaWYgbm90IChxLmdldCgiYW5zd2VyIikgb3IgIiIpLnN0cmlwKCldCiAgICAgICAgaWYgc3QgPT0gInJldmlldyI6CiAgICAgICAgICAgIG91dC5hcHBlbmQoKHRpZCwgInJldmlldyIsIHRpdGxlLCAiIikpCiAgICAgICAgZWxpZiBzdCA9PSAibmVlZHNfYnJhaW5zdG9ybSIgYW5kIHVhOgogICAgICAgICAgICBvdXQuYXBwZW5kKCh0aWQsICJicmFpbnN0b3JtIiwgdGl0bGUsICJcbiIuam9pbihmIiAgIHtpKzF9KSB7cX0iIGZvciBpLCBxIGluIGVudW1lcmF0ZSh1YSkpKSkKICAgICAgICBlbGlmIHN0ID09ICJibG9ja2VkIjogICAgICAgICAgICAgICAgICAgICAgICAgICAjIGNlb0dhdGVkIC0+IGF3YWl0aW5nIHRoZSBDRU8gKGUuZy4gYnJhaW5zdG9ybSBhbnN3ZXJzIC8gYSBkZWNpc2lvbikKICAgICAgICAgICAgb3V0LmFwcGVuZCgodGlkLCAiYmxvY2tlZCIsIHRpdGxlLCAodC5nZXQoImxhc3RTdGF0dXMiKSBvciAiIikuc3RyaXAoKVs6MjQwXSkpCiAgICByZXR1cm4gb3V0CgpkZWYgX2RlZXBsaW5rKHRpZCk6CiAgICByZXR1cm4gZiJ7V0FfQk9BUkRfVVJMfSNjYXJkL3t0aWR9IiBpZiBXQV9CT0FSRF9VUkwgZWxzZSBmIihjYXJkIHt0aWR9KSIKCmRlZiBfYnVpbGRfZGlnZXN0KGl0ZW1zKToKICAgICIiIk9ORSBjb25zb2xpZGF0ZWQgbWVzc2FnZSBsaXN0aW5nIGV2ZXJ5IGJsb2NrZWQtb24tQ0VPIGNhcmQsIGdyb3VwZWQsIGVhY2ggd2l0aCBpdHMgZGVlcC1saW5rLgogICAgQnJhaW5zdG9ybSBjYXJkcyBsaXN0IHRoZWlyIG9wZW4gcXVlc3Rpb25zIGlubGluZSBzbyB0aGUgQ0VPIGNhbiBhbnN3ZXIgc3RyYWlnaHQgZnJvbSB0aGUgcGluZy4iIiIKICAgIHJldiA9IFt4IGZvciB4IGluIGl0ZW1zIGlmIHhbMV0gPT0gInJldmlldyJdOyBicyA9IFt4IGZvciB4IGluIGl0ZW1zIGlmIHhbMV0gPT0gImJyYWluc3Rvcm0iXTsgYmwgPSBbeCBmb3IgeCBpbiBpdGVtcyBpZiB4WzFdID09ICJibG9ja2VkIl0KICAgIG4gPSBsZW4oaXRlbXMpCiAgICBsaW5lcyA9IFtmIvCflJQge259IGl0ZW17J3MnIGlmIG4gIT0gMSBlbHNlICcnfSBuZWVkIHlvdToiXQogICAgaWYgcmV2OgogICAgICAgIGxpbmVzLmFwcGVuZCgiXG5SZXZpZXcg4oCUIG5lZWRzIHlvdXIgRE9ORToiKQogICAgICAgIGZvciB0aWQsIF8sIHRpdGxlLCBfZCBpbiByZXY6IGxpbmVzLmFwcGVuZChmIuKAoiB7dGl0bGV9XG4gIHtfZGVlcGxpbmsodGlkKX0iKQogICAgaWYgYnM6CiAgICAgICAgbGluZXMuYXBwZW5kKCJcbkJyYWluc3Rvcm0g4oCUIG5lZWRzIHlvdXIgYW5zd2VyczoiKQogICAgICAgIGZvciB0aWQsIF8sIHRpdGxlLCBkZXRhaWwgaW4gYnM6IGxpbmVzLmFwcGVuZChmIuKAoiB7dGl0bGV9XG57ZGV0YWlsfVxuICB7X2RlZXBsaW5rKHRpZCl9IikKICAgIGlmIGJsOgogICAgICAgIGxpbmVzLmFwcGVuZCgiXG5CbG9ja2VkIG9uIHlvdToiKQogICAgICAgIGZvciB0aWQsIF8sIHRpdGxlLCBkZXRhaWwgaW4gYmw6IGxpbmVzLmFwcGVuZChmIuKAoiB7dGl0bGV9IiArIChmIiDigJQge2RldGFpbH0iIGlmIGRldGFpbCBlbHNlICIiKSArIGYiXG4gIHtfZGVlcGxpbmsodGlkKX0iKQogICAgcmV0dXJuICJcbiIuam9pbihsaW5lcykKCmRlZiB3YV9yZWNvbmNpbGUoKToKICAgICIiIkNFTy13YXRjaGRvZyBwYXNzOiBpZiDiiaUxIGNhcmQgaXMgYmxvY2tlZCBvbiB0aGUgQ0VPLCBlbnF1ZXVlIE9ORSBjb25zb2xpZGF0ZWQgZGlnZXN0ICh0aHJvdHRsZWQKICAgIHRvIH5vbmUgcGVyIFdBX1dBVENIRE9HIHRpY2spOyBpZiBub25lIGFyZSBibG9ja2VkLCBjYW5jZWwgYW55IHBlbmRpbmcgZGlnZXN0LiBJZGVtcG90ZW50LiIiIgogICAgaWYgbm90IFdBX0RSQUlOX09OOiByZXR1cm4KICAgIGl0ZW1zID0gX2Jsb2NrZWRfaXRlbXMobG9hZCgpKTsgbm93dCA9IG5vdygpCiAgICB3aXRoIF93YV9sb2NrOgogICAgICAgIG8gPSB3YV9sb2FkKCk7IHEgPSBvWyJxdWV1ZSJdCiAgICAgICAgaWYgbm90IGl0ZW1zOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBub3RoaW5nIGJsb2NrZWQgLT4gY2FuY2VsIGFueSB1bnNlbnQgZGlnZXN0LCBzdG9wCiAgICAgICAgICAgIGNoID0gRmFsc2UKICAgICAgICAgICAgZm9yIGUgaW4gcToKICAgICAgICAgICAgICAgIGlmIGUuZ2V0KCJzZW50QXQiKSBpcyBOb25lIGFuZCBub3QgZS5nZXQoImNhbmNlbGVkIik6IGVbImNhbmNlbGVkIl0gPSBUcnVlOyBjaCA9IFRydWUKICAgICAgICAgICAgaWYgY2g6IHdhX3NhdmUobykKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgaWYgYW55KGUuZ2V0KCJzZW50QXQiKSBpcyBOb25lIGFuZCBub3QgZS5nZXQoImNhbmNlbGVkIikgZm9yIGUgaW4gcSk6CiAgICAgICAgICAgIHJldHVybiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBhIGRpZ2VzdCBpcyBhbHJlYWR5IHBlbmRpbmcgKGRvbid0IHBpbGUgdXApCiAgICAgICAgbGFzdCA9IG1heChbZS5nZXQoInNlbnRBdCIpIG9yIDAgZm9yIGUgaW4gcV0gb3IgWzBdKQogICAgICAgIGlmIGxhc3QgYW5kIChub3d0IC0gbGFzdCkgPCBXQV9SRVBJTkcgKiAxMDAwOiAgICAgICMgc2VudCBvbmUgcmVjZW50bHkgLT4gbmV4dCB0aWNrCiAgICAgICAgICAgIHJldHVybgogICAgICAgIHEuYXBwZW5kKHsiaWQiOiB1aWQoKSwgImtpbmQiOiAiZGlnZXN0IiwgImRlZHVwS2V5IjogImRpZ2VzdCIsICJ0ZXh0IjogX2J1aWxkX2RpZ2VzdChpdGVtcyksCiAgICAgICAgICAgICAgICAgICJjb3VudCI6IGxlbihpdGVtcyksICJjcmVhdGVkIjogbm93dCwgInNlbnRBdCI6IE5vbmUsICJhdHRlbXB0cyI6IDAsICJsYXN0RXJyb3IiOiAiIiwgImNhbmNlbGVkIjogRmFsc2V9KQogICAgICAgIG9bInF1ZXVlIl0gPSBxWy01MDA6XTsgd2Ffc2F2ZShvKQoKZGVmIHdhX3NlbmQodGV4dCk6CiAgICAiIiJUSEUgTEFTVCBIT1Ag4oCUIGhhbmQgdGhlIG1lc3NhZ2UgdG8gdGhlIGNvbnRhaW5lcml6ZWQgSGVybWVzIGJyaWRnZSDihpIgQ0VPIFdoYXRzQXBwLgogICAgQnVpbGRzIHtjaGF0SWQsIG1lc3NhZ2V9IEpTT04gYW5kIHBpcGVzIGl0IHRvIFdBX1NFTkRfQ01EIG9uIHN0ZGluLiBSZXR1cm5zIChvaywgaW5mbykuIiIiCiAgICBwYXlsb2FkID0ganNvbi5kdW1wcyh7ImNoYXRJZCI6IFdBX0NIQVRfSklELCAibWVzc2FnZSI6IHRleHR9KQogICAgdHJ5OgogICAgICAgIHIgPSBzdWJwcm9jZXNzLnJ1bihXQV9TRU5EX0NNRCwgc2hlbGw9VHJ1ZSwgaW5wdXQ9cGF5bG9hZCwgY2FwdHVyZV9vdXRwdXQ9VHJ1ZSwgdGV4dD1UcnVlLCB0aW1lb3V0PTMwKQogICAgICAgIG91dCA9ICgoci5zdGRvdXQgb3IgIiIpICsgKHIuc3RkZXJyIG9yICIiKSkuc3RyaXAoKQogICAgICAgIG9rID0gJyJzdWNjZXNzIjp0cnVlJyBpbiBvdXQucmVwbGFjZSgiICIsICIiKSBvciAnIm1lc3NhZ2VpZCInIGluIG91dC5sb3dlcigpCiAgICAgICAgcmV0dXJuIG9rLCBvdXRbOjIwMF0KICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICByZXR1cm4gRmFsc2UsIHN0cihlKVs6MjAwXQoKZGVmIHdhX2RyYWluX29uY2UoKToKICAgIHdpdGggX3dhX2xvY2s6CiAgICAgICAgcGVuZCA9IFtkaWN0KGUpIGZvciBlIGluIHdhX2xvYWQoKVsicXVldWUiXSBpZiBlLmdldCgic2VudEF0IikgaXMgTm9uZSBhbmQgbm90IGUuZ2V0KCJjYW5jZWxlZCIpXQogICAgZm9yIGUgaW4gcGVuZDoKICAgICAgICB3aXRoIF93YV9sb2NrOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHJlLWNoZWNrOiBhIHJlY29uY2lsZSBtYXkgaGF2ZSBjYW5jZWxlZCBpdCAoYmxvY2sgY2xlYXJlZCkgc2luY2UgdGhlIHNuYXBzaG90CiAgICAgICAgICAgIGN1ciA9IG5leHQoKHggZm9yIHggaW4gd2FfbG9hZCgpWyJxdWV1ZSJdIGlmIHhbImlkIl0gPT0gZVsiaWQiXSksIE5vbmUpCiAgICAgICAgICAgIGlmIG5vdCBjdXIgb3IgY3VyLmdldCgic2VudEF0Iikgb3IgY3VyLmdldCgiY2FuY2VsZWQiKTogY29udGludWUKICAgICAgICBvaywgaW5mbyA9IHdhX3NlbmQoZVsidGV4dCJdKQogICAgICAgIHdpdGggX3dhX2xvY2s6CiAgICAgICAgICAgIG8gPSB3YV9sb2FkKCk7IGN1ciA9IG5leHQoKHggZm9yIHggaW4gb1sicXVldWUiXSBpZiB4WyJpZCJdID09IGVbImlkIl0pLCBOb25lKQogICAgICAgICAgICBpZiBub3QgY3VyIG9yIGN1ci5nZXQoImNhbmNlbGVkIik6IGNvbnRpbnVlICAgICMgY2FuY2VsZWQgbWlkLXNlbmQgLT4gZG9uJ3QgcmVjb3JkIGFzIHNlbnQKICAgICAgICAgICAgY3VyWyJhdHRlbXB0cyJdID0gY3VyLmdldCgiYXR0ZW1wdHMiLCAwKSArIDEKICAgICAgICAgICAgaWYgb2s6IGN1clsic2VudEF0Il0gPSBub3coKTsgY3VyWyJpbmZvIl0gPSBpbmZvCiAgICAgICAgICAgIGVsc2U6ICBjdXJbImxhc3RFcnJvciJdID0gaW5mbwogICAgICAgICAgICB3YV9zYXZlKG8pCgpkZWYgd2FfZHJhaW5fbG9vcCgpOgogICAgd2hpbGUgVHJ1ZToKICAgICAgICB0aW1lLnNsZWVwKFdBX0RSQUlOX1NFQykKICAgICAgICBpZiBXQV9EUkFJTl9PTjoKICAgICAgICAgICAgdHJ5OiB3YV9kcmFpbl9vbmNlKCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwoKZGVmIHdhX3dhdGNoZG9nX2xvb3AoKToKICAgIHdoaWxlIFRydWU6CiAgICAgICAgdGltZS5zbGVlcChXQV9XQVRDSERPRykKICAgICAgICB0cnk6IHdhX3JlY29uY2lsZSgpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcGFzcwoKZGVmIGFwcGx5X2JyYWluc3Rvcm0oZCk6CiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldChkLmdldCgiaWQiKSkKICAgICAgICBpZiBub3QgdDogcmV0dXJuIHsiZXJyb3IiOiAibm8gc3VjaCB0YXNrIn0KICAgICAgICBwcmV2X2JzLCBwcmV2X3N0YXRlID0gdC5nZXQoImJyYWluc3Rvcm0iLCAiIiksIHRbInN0YXRlIl0KICAgICAgICB3aG8gPSBkLmdldCgiYnkiKSBvciAiYnJhaW5zdG9ybSIKICAgICAgICAjIHRoZSB3b3JrZXIgcG9zdHMgZ2VuZXJhdGVkIGNsYXJpZnlpbmcgcXVlc3Rpb25zIChzdGF0ZSBzdGF5cyBuZWVkc19icmFpbnN0b3JtKQogICAgICAgIGlmICJxdWVzdGlvbnMiIGluIGQgYW5kIGlzaW5zdGFuY2UoZFsicXVlc3Rpb25zIl0sIGxpc3QpOgogICAgICAgICAgICB0WyJxdWVzdGlvbnMiXSA9IFt7ImlkIjogdWlkKCksICJxIjogc3RyKHEpLnN0cmlwKCksICJhbnN3ZXIiOiAiIiwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICJhc2tlZEF0Ijogbm93KCksICJhbnN3ZXJlZEF0IjogTm9uZX0KICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgZm9yIHEgaW4gZFsicXVlc3Rpb25zIl0gaWYgc3RyKHEpLnN0cmlwKCldCiAgICAgICAgICAgIHRbImJyYWluc3Rvcm1Bc2tlZCJdID0gVHJ1ZQogICAgICAgICAgICBuID0gbGVuKHRbInF1ZXN0aW9ucyJdKQogICAgICAgICAgICBhZGRfY29tbWVudCh0LCAoZiJicmFpbnN0b3JtIGdlbmVyYXRlZCB7bn0gY2xhcmlmeWluZyBxdWVzdGlvbihzKSDigJQgYW5zd2VyIHRoZW0gaW4gdGhlIGNhcmQgdG8gdW5ibG9jayB0aGlzIHRhc2suIgogICAgICAgICAgICAgICAgICAgICAgICAgICAgaWYgbiBlbHNlICJicmFpbnN0b3JtOiB0YXNrIGlzIGNsZWFyIGVub3VnaCB0byB3b3JrIOKAlCBubyBvcGVuIHF1ZXN0aW9ucy4iKSwgd2hvLCAiYnJhaW5zdG9ybSIpCiAgICAgICAgICAgIGlmIG46CiAgICAgICAgICAgICAgICB0WyJsYXN0U3RhdHVzIl0gPSBmIm5lZWRzIGJyYWluc3Rvcm0g4oCUIHtufSBxdWVzdGlvbihzKSBhd2FpdGluZyB0aGUgQ0VPIgogICAgICAgIGlmICJicmFpbnN0b3JtIiBpbiBkOgogICAgICAgICAgICB0WyJicmFpbnN0b3JtIl0gPSBkLmdldCgiYnJhaW5zdG9ybSIsIHQuZ2V0KCJicmFpbnN0b3JtIiwgIiIpKQogICAgICAgICAgICBpZiB0WyJicmFpbnN0b3JtIl0uc3RyaXAoKSBhbmQgdFsiYnJhaW5zdG9ybSJdICE9IHByZXZfYnM6CiAgICAgICAgICAgICAgICBhZGRfY29tbWVudCh0LCB0WyJicmFpbnN0b3JtIl0sIHdobywgImJyYWluc3Rvcm0iKQogICAgICAgIGlmIGQuZ2V0KCJwcm9tb3RlIikgYW5kIHRbInN0YXRlIl0gPT0gIm5lZWRzX2JyYWluc3Rvcm0iOgogICAgICAgICAgICBpZiBub3QgYnJhaW5zdG9ybV9yZWFkeSh0KToKICAgICAgICAgICAgICAgIHVhID0gbGVuKF91bmFuc3dlcmVkKHQpKQogICAgICAgICAgICAgICAgcmV0dXJuIHsiZXJyb3IiOiBmImJyYWluc3Rvcm0gZ2F0ZToge3VhfSB1bmFuc3dlcmVkIHF1ZXN0aW9uKHMpIOKAlCBhbnN3ZXIgdGhlbSBiZWZvcmUgcHJvbW90aW5nIgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBpZiB1YSBlbHNlICJicmFpbnN0b3JtIGdhdGU6IG5vIGJyYWluc3Rvcm0gYXJ0aWZhY3QgeWV0In0KICAgICAgICAgICAgX2cgPSBzdGF0ZV9nYXRlKGIsIHQsICJ3b3JraW5nIikgICAgICAgICAgICAgIyBpc3N1ZSAjMzogcmVzcGVjdCB0aGUgaGFyZCBnYXRlIG9uIHByb21vdGXihpJ3b3JraW5nCiAgICAgICAgICAgIGlmIF9nOiByZXR1cm4geyJlcnJvciI6IF9nfQogICAgICAgICAgICBfYXNzZW1ibGVfYXJ0aWZhY3QodCkKICAgICAgICAgICAgdFsic3RhdGUiXSA9ICJ3b3JraW5nIjsgdFsibGFzdFN0YXR1cyJdID0gIiIKICAgICAgICBpZiB0WyJzdGF0ZSJdICE9IHByZXZfc3RhdGU6CiAgICAgICAgICAgIGFkZF9jb21tZW50KHQsIGYic3RhdGU6IHtwcmV2X3N0YXRlfSDihpIge3RbJ3N0YXRlJ119Iiwgd2hvLCAic3RhdGUiKQogICAgICAgIHRbInVwZGF0ZWQiXSA9IG5vdygpOyBzYXZlKGIpCiAgICAgICAgcmVzID0geyJvayI6IFRydWUsICJzdGF0ZSI6IHRbInN0YXRlIl0sICJyZWFkeSI6IGJyYWluc3Rvcm1fcmVhZHkodCksICJ1bmFuc3dlcmVkIjogbGVuKF91bmFuc3dlcmVkKHQpKX0KICAgIHdhX3JlY29uY2lsZSgpICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHF1ZXN0aW9ucyBwb3N0ZWQgKGJyYWluc3Rvcm0tcGVuZGluZykgLT4gZW5xdWV1ZSBXaGF0c0FwcCAoc2xpY2UgZSkKICAgIHJldHVybiByZXMKCmRlZiBhcHBseV9hbnN3ZXIoZCk6CiAgICAiIiJDRU8gYW5zd2VycyBhIGdlbmVyYXRlZCBicmFpbnN0b3JtIHF1ZXN0aW9uIGluIHRoZSBjYXJkLiBXaGVuIHRoZSBsYXN0IG9uZSBpcyBhbnN3ZXJlZCwKICAgIHRoZSBhcnRpZmFjdCBpcyBhc3NlbWJsZWQgYW5kIHRoZSB0YXNrIGJlY29tZXMgcHJvbW90YWJsZSAoc3RpbGwgbmVlZHNfYnJhaW5zdG9ybSB1bnRpbCBwcm9tb3RlZCkuIiIiCiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldChkLmdldCgidGFza19pZCIpIG9yIGQuZ2V0KCJpZCIpKQogICAgICAgIGlmIG5vdCB0OiByZXR1cm4geyJlcnJvciI6ICJubyBzdWNoIHRhc2sifQogICAgICAgIHFpZCwgYW5zID0gZC5nZXQoInFpZCIpLCAoZC5nZXQoImFuc3dlciIpIG9yICIiKS5zdHJpcCgpCiAgICAgICAgcSA9IG5leHQoKHggZm9yIHggaW4gdC5nZXQoInF1ZXN0aW9ucyIsIFtdKSBpZiB4LmdldCgiaWQiKSA9PSBxaWQpLCBOb25lKQogICAgICAgIGlmIG5vdCBxOiByZXR1cm4geyJlcnJvciI6ICJubyBzdWNoIHF1ZXN0aW9uIn0KICAgICAgICBpZiBub3QgYW5zOiByZXR1cm4geyJlcnJvciI6ICJlbXB0eSBhbnN3ZXIifQogICAgICAgIHFbImFuc3dlciJdID0gYW5zOyBxWyJhbnN3ZXJlZEF0Il0gPSBub3coKQogICAgICAgIGFkZF9jb21tZW50KHQsIGYiUToge3EuZ2V0KCdxJywnJykuc3RyaXAoKX1cbkE6IHthbnN9IiwgZC5nZXQoImJ5IiwgIkNFTyIpLCAiY29tbWVudCIpCiAgICAgICAgdWEgPSBsZW4oX3VuYW5zd2VyZWQodCkpCiAgICAgICAgaWYgdWEgPT0gMDoKICAgICAgICAgICAgX2Fzc2VtYmxlX2FydGlmYWN0KHQpCiAgICAgICAgICAgIHRbImxhc3RTdGF0dXMiXSA9ICJicmFpbnN0b3JtIGFuc3dlcmVkIOKAlCByZWFkeSB0byBwcm9tb3RlIHRvIHdvcmtpbmciCiAgICAgICAgZWxzZToKICAgICAgICAgICAgdFsibGFzdFN0YXR1cyJdID0gZiJuZWVkcyBicmFpbnN0b3JtIOKAlCB7dWF9IHF1ZXN0aW9uKHMpIHN0aWxsIGF3YWl0aW5nIHRoZSBDRU8iCiAgICAgICAgdFsidXBkYXRlZCJdID0gbm93KCk7IHNhdmUoYikgICAgICAgICAgICAgICAjIHBlcnNpc3QgdGhlIGFuc3dlciBCRUZPUkUgcGluZ2luZyAoYm9zc19waW5nIHJlbG9hZHMgZnJvbSBkaXNrKQogICAgd2FfcmVjb25jaWxlKCkgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgYW4gYW5zd2VyIG1heSBjbGVhciB0aGUgYnJhaW5zdG9ybSBibG9jayAtPiBjYW5jZWwgaXRzIFdoYXRzQXBwIHBpbmcgKHNsaWNlIGUpCiAgICBpZiB1YSA9PSAwOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyBwaW5nIG91dHNpZGUgdGhlIGxvY2s7IGl0IHJlbG9hZHMgdGhlIGp1c3Qtc2F2ZWQgc3RhdGUKICAgICAgICBib3NzX3BpbmcoZC5nZXQoInRhc2tfaWQiKSBvciBkLmdldCgiaWQiKSwgImJyYWluc3Rvcm0gZ2F0ZSBjbGVhcmVkIOKAlCBhbGwgcXVlc3Rpb25zIGFuc3dlcmVkOyBwcm9tb3RlIHRvIHdvcmtpbmciKQogICAgcmV0dXJuIHsib2siOiBUcnVlLCAidW5hbnN3ZXJlZCI6IHVhLCAicmVhZHkiOiBUcnVlIGlmIHVhID09IDAgZWxzZSBGYWxzZX0KCmRlZiBhcHBseV9zdGF0dXMoZCk6CiAgICB3aXRoIF9sb2NrOgogICAgICAgIGIgPSBsb2FkKCk7IHQgPSBiWyJ0YXNrcyJdLmdldChkLmdldCgiaWQiKSkKICAgICAgICBpZiBub3QgdDogcmV0dXJuIHsiZXJyb3IiOiAibm8gc3VjaCB0YXNrIn0KICAgICAgICB3aG8gPSBkLmdldCgiYnkiKSBvciB0LmdldCgiYXNzaWduZWUiKSBvciAiZW5naW5lZXIiCiAgICAgICAgcHJldl9zdGF0ZSA9IHRbInN0YXRlIl0KICAgICAgICBpZiAibGFzdFN0YXR1cyIgaW4gZDoKICAgICAgICAgICAgdFsibGFzdFN0YXR1cyJdID0gZFsibGFzdFN0YXR1cyJdCiAgICAgICAgICAgIGFkZF9jb21tZW50KHQsIGRbImxhc3RTdGF0dXMiXSwgd2hvLCAic3RhdHVzIikgICAjIGVuZ2luZWVyJ3Mgdm9pY2UgLT4gZHVyYWJsZSB0aHJlYWQgZXZlbnQKICAgICAgICBpZiAidmVyaWZpZWQiIGluIGQ6IHRbInZlcmlmaWVkIl0gPSBib29sKGRbInZlcmlmaWVkIl0pCiAgICAgICAgaWYgInN0YXRlIiBpbiBkOgogICAgICAgICAgICBpZiBkWyJzdGF0ZSJdIG5vdCBpbiBWQUxJRF9TVEFURVM6CiAgICAgICAgICAgICAgICByZXR1cm4geyJlcnJvciI6IGYiaW52YWxpZCBzdGF0ZSB7ZFsnc3RhdGUnXSFyfSAoYWxsb3dlZDoge3NvcnRlZChWQUxJRF9TVEFURVMpfSkifQogICAgICAgICAgICBpZiBkWyJzdGF0ZSJdID09ICJkb25lIjoKICAgICAgICAgICAgICAgICMgUnVsZSAyMTogT05MWSB0aGUgQ0VPIG1hcmtzIGRvbmUg4oCUIGhpcyBhY3Rpb24gSVMgdGhlIHNpZ24tb2ZmICsgdmVyaWZpY2F0aW9uLCBpbiBPTkUKICAgICAgICAgICAgICAgICMgc3RlcCBmcm9tIEFOWSBzdGF0ZSAod29ya2luZyAvIG5lZWRzX2JyYWluc3Rvcm0gLyBibG9ja2VkIC8gcmV2aWV3KS4gVGhlIEFJL2VuZ2luZWVyCiAgICAgICAgICAgICAgICAjIGNhbiBtb3ZlIGEgY2FyZCBVUCBUTyAncmV2aWV3JyBmb3IgQ0VPIHNpZ24tb2ZmIGJ1dCBjYW4gTkVWRVIgc2V0ICdkb25lJyAodGhlIGdhdGUKICAgICAgICAgICAgICAgICMgZXhpc3RzIHNvbGVseSB0byBzdG9wIHRoZSBBSSBhdXRvLWNsb3NpbmcgdW5yZWFkeSB3b3JrIOKAlCBpdCBtdXN0IG5vdCBnYXRlIHRoZSBDRU8pLgogICAgICAgICAgICAgICAgaWYgc3RyKGQuZ2V0KCJieSIsICIiKSkuc3RyaXAoKS51cHBlcigpID09ICJDRU8iOgogICAgICAgICAgICAgICAgICAgIHRbInZlcmlmaWVkIl0gPSBUcnVlCiAgICAgICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgICAgIHJldHVybiB7ImVycm9yIjogIm9ubHkgdGhlIENFTyBtYXJrcyBkb25lIOKAlCBBSS9lbmdpbmVlciBjYW4gbW92ZSBhIGNhcmQgdXAgdG8gJ3JldmlldycgZm9yIENFTyBzaWduLW9mZiwgbmV2ZXIgdG8gJ2RvbmUnIn0KICAgICAgICAgICAgX2cgPSBzdGF0ZV9nYXRlKGIsIHQsIGRbInN0YXRlIl0pICAgICAgICAgICAgIyBpc3N1ZSAjMzogc3VidGFzay9kZXBlbmRlbmN5ICsgaGFyZC1nYXRlIGd1YXJkcmFpbHMKICAgICAgICAgICAgaWYgX2c6IHJldHVybiB7ImVycm9yIjogX2d9CiAgICAgICAgICAgIHRbInN0YXRlIl0gPSBkWyJzdGF0ZSJdCiAgICAgICAgaWYgZC5nZXQoImNlb0dhdGVkIik6ICAgICAgICAgICAjIGVuZ2luZWVyIHNpZ25hbHMgZG9uZS1wZW5kaW5nLUNFTyAtPiBibG9ja2VkIChDRU8gd2luZG93L2RlY2lzaW9uIGdhdGVzIGl0KQogICAgICAgICAgICB0WyJzdGF0ZSJdID0gImJsb2NrZWQiICAgICAgIyB0aGUgd2F0Y2hkb2cgKyB1bmFzc2lnbmVkIGNyb24gc2tpcCAnYmxvY2tlZCcgLT4gbm8gZmFsc2Ugc3RhbGwtbmFnCiAgICAgICAgaWYgdFsic3RhdGUiXSAhPSBwcmV2X3N0YXRlOgogICAgICAgICAgICBhZGRfY29tbWVudCh0LCBmInN0YXRlOiB7cHJldl9zdGF0ZX0g4oaSIHt0WydzdGF0ZSddfSIsIHdobywgInN0YXRlIikKICAgICAgICB0WyJ1cGRhdGVkIl0gPSBub3coKTsgc2F2ZShiKQogICAgICAgIHJldGlyZSA9IChwcmV2X3N0YXRlLCBkaWN0KHQpKSBpZiAodFsic3RhdGUiXSA9PSAiZG9uZSIgYW5kIHByZXZfc3RhdGUgIT0gImRvbmUiKSBlbHNlIE5vbmUKICAgIHdhX3JlY29uY2lsZSgpICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIENFTy1ibG9ja2VkPyAocmV2aWV3L2Jsb2NrZWQpIC0+IGVucXVldWUgV2hhdHNBcHAgKHNsaWNlIGUpCiAgICBpZiByZXRpcmU6IHJldGlyZV9vbl9kb25lKHJldGlyZVswXSwgcmV0aXJlWzFdKSAgIyBPVVRTSURFIF9sb2NrOiBDRU8g4oaSZG9uZSDihpIgcmV0aXJlIHRoZSBhc3NpZ25lZSAobXAga2lsbCkgKyBldmVudCB0aGUgQm9zcwogICAgcmV0dXJuIHsib2siOiBUcnVlLCAic3RhdGUiOiB0WyJzdGF0ZSJdfQoKZGVmIGFwcGx5X3Byb29mKGQpOgogICAgd2l0aCBfbG9jazoKICAgICAgICBiID0gbG9hZCgpOyB0aWQgPSBkLmdldCgidGFza19pZCIpOyB0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIG5vdCB0OiByZXR1cm4geyJlcnJvciI6ICJubyBzdWNoIHRhc2sifQogICAgICAgIHB0eXBlID0gZC5nZXQoInR5cGUiLCAidGV4dCIpOyByZWYgPSBkLmdldCgicmVmIiwgIiIpOyBwaWQgPSB1aWQoKQogICAgICAgIGlmIHB0eXBlIGluICgiaW1hZ2UiLCAidmlkZW8iKSBhbmQgZC5nZXQoImRhdGFfYjY0Iik6CiAgICAgICAgICAgIFBEID0gUFJPT0ZfRElSIC8gdGlkOyBQRC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICAgICAgICAgIGV4dCA9IChkLmdldCgiZXh0Iikgb3IgKCJwbmciIGlmIHB0eXBlID09ICJpbWFnZSIgZWxzZSAibXA0IikpLmxzdHJpcCgiLiIpCiAgICAgICAgICAgIHJhdyA9IGRbImRhdGFfYjY0Il0KICAgICAgICAgICAgaWYgcmF3LnN0YXJ0c3dpdGgoImRhdGE6Iik6IHJhdyA9IHJhdy5zcGxpdCgiLCIsIDEpWzFdICAgIyBzdHJpcCBkYXRhLVVSTCBwcmVmaXgKICAgICAgICAgICAgZnAgPSBQRCAvIGYie3BpZH0ue2V4dH0iOyBmcC53cml0ZV9ieXRlcyhiYXNlNjQuYjY0ZGVjb2RlKHJhdykpCiAgICAgICAgICAgIHJlZiA9IGYiL3RvZG8vcHJvb2Yve3RpZH0ve3BpZH0ue2V4dH0iICAgIyBhIFNFUlZFRCB1cmwsIG5vdCBhIGZpbGVzeXN0ZW0gcGF0aAogICAgICAgIGVsaWYgcHR5cGUgaW4gKCJpbWFnZSIsICJ2aWRlbyIpIGFuZCByZWYgYW5kIG5vdCByZWYuc3RhcnRzd2l0aCgiL3RvZG8vcHJvb2YvIik6CiAgICAgICAgICAgIHVybCA9IF9pbmdlc3RfZmlsZSh0aWQsIHBpZCwgcHR5cGUsIHJlZikgICAjIGF0dGFjaGVkIGJ5IHBhdGgvZmlsZTovLyAtPiBjb3B5IGluICsgc2VydmUKICAgICAgICAgICAgaWYgdXJsOiByZWYgPSB1cmwKICAgICAgICBwcm9vZiA9IHsiaWQiOiBwaWQsICJ0eXBlIjogcHR5cGUsICJyZWYiOiByZWYsICJjYXB0aW9uIjogZC5nZXQoImNhcHRpb24iLCAiIiksCiAgICAgICAgICAgICAgICAgImJ5IjogZC5nZXQoImJ5IiwgImVuZ2luZWVyIiksICJ0cyI6IG5vdygpfQogICAgICAgIHRbInByb29mcyJdLmFwcGVuZChwcm9vZik7IHRbInVwZGF0ZWQiXSA9IG5vdygpOyBzYXZlKGIpCiAgICAgICAgcmV0dXJuIHsib2siOiBUcnVlLCAicHJvb2ZfaWQiOiBwaWR9CgojIOKUgOKUgCBIVFRQIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgApjbGFzcyBIKGh0dHAuc2VydmVyLkJhc2VIVFRQUmVxdWVzdEhhbmRsZXIpOgogICAgZGVmIGxvZ19tZXNzYWdlKHNlbGYsICphKTogcGFzcwogICAgZGVmIF9zZW5kKHNlbGYsIGNvZGUsIGJvZHksIGN0eXBlPSJhcHBsaWNhdGlvbi9qc29uIik6CiAgICAgICAgaWYgaXNpbnN0YW5jZShib2R5LCAoZGljdCwgbGlzdCkpOiBib2R5ID0ganNvbi5kdW1wcyhib2R5KS5lbmNvZGUoKQogICAgICAgIGVsaWYgaXNpbnN0YW5jZShib2R5LCBzdHIpOiBib2R5ID0gYm9keS5lbmNvZGUoKQogICAgICAgIHNlbGYuc2VuZF9yZXNwb25zZShjb2RlKTsgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1UeXBlIiwgY3R5cGUpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1MZW5ndGgiLCBzdHIobGVuKGJvZHkpKSkKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJDYWNoZS1Db250cm9sIiwgIm5vLWNhY2hlLCBuby1zdG9yZSwgbXVzdC1yZXZhbGlkYXRlIikgICMgbmV2ZXIgY2FjaGUgdGhlIGJvYXJkIEhUTUwvSlNPTiDigJQgdGhlIENFTyBtdXN0IGFsd2F5cyBnZXQgdGhlIGxhdGVzdCBib2FyZCBKUyAoc3RhbGUgSlMgPSB0aGUgbW9kYWwgYnVnIGhlIGtlcHQgaGl0dGluZykKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJBY2Nlc3MtQ29udHJvbC1BbGxvdy1PcmlnaW4iLCAiKiIpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQWNjZXNzLUNvbnRyb2wtQWxsb3ctSGVhZGVycyIsICJDb250ZW50LVR5cGUsWC1RdWV1ZS1TZWNyZXQiKQogICAgICAgIHNlbGYuZW5kX2hlYWRlcnMoKTsgc2VsZi53ZmlsZS53cml0ZShib2R5KQogICAgZGVmIF9zZXJ2ZV9ieXRlcyhzZWxmLCBkYXRhLCBjdHlwZSk6CiAgICAgICAgIiIiU2VydmUgYSBiaW5hcnkgd2l0aCBIVFRQIFJhbmdlIHN1cHBvcnQgc28gPHZpZGVvPiBjYW4gc2VlayAoQ0VPOiB3YXRjaCBwcm9vZiBvbiB0aGUgYm9hcmQpLiIiIgogICAgICAgIHRvdGFsID0gbGVuKGRhdGEpOyBybmcgPSBzZWxmLmhlYWRlcnMuZ2V0KCJSYW5nZSIsICIiKTsgcGFydGlhbCA9IEZhbHNlOyBzdGFydCwgZW5kID0gMCwgdG90YWwgLSAxCiAgICAgICAgaWYgcm5nLnN0YXJ0c3dpdGgoImJ5dGVzPSIpOgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBzLCBfLCBlID0gcm5nWzY6XS5wYXJ0aXRpb24oIi0iKQogICAgICAgICAgICAgICAgc3RhcnQgPSBpbnQocykgaWYgcyBlbHNlIDAKICAgICAgICAgICAgICAgIGVuZCA9IGludChlKSBpZiBlIGVsc2UgdG90YWwgLSAxCiAgICAgICAgICAgICAgICBpZiAwIDw9IHN0YXJ0IDw9IGVuZCA8IHRvdGFsOiBwYXJ0aWFsID0gVHJ1ZQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiBwYXJ0aWFsID0gRmFsc2UKICAgICAgICBjaHVuayA9IGRhdGFbc3RhcnQ6ZW5kICsgMV0gaWYgcGFydGlhbCBlbHNlIGRhdGEKICAgICAgICBzZWxmLnNlbmRfcmVzcG9uc2UoMjA2IGlmIHBhcnRpYWwgZWxzZSAyMDApCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1UeXBlIiwgY3R5cGUpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQWNjZXB0LVJhbmdlcyIsICJieXRlcyIpCiAgICAgICAgaWYgcGFydGlhbDogc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1SYW5nZSIsIGYiYnl0ZXMge3N0YXJ0fS17ZW5kfS97dG90YWx9IikKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJDb250ZW50LUxlbmd0aCIsIHN0cihsZW4oY2h1bmspKSkKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJBY2Nlc3MtQ29udHJvbC1BbGxvdy1PcmlnaW4iLCAiKiIpCiAgICAgICAgc2VsZi5lbmRfaGVhZGVycygpCiAgICAgICAgdHJ5OiBzZWxmLndmaWxlLndyaXRlKGNodW5rKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHBhc3MKICAgIGRlZiBfYXV0aChzZWxmKToKICAgICAgICByZXR1cm4gKG5vdCBTRUNSRVQpIG9yIHNlbGYuaGVhZGVycy5nZXQoIlgtUXVldWUtU2VjcmV0IiwgIiIpID09IFNFQ1JFVAogICAgZGVmIF9ib2R5KHNlbGYpOgogICAgICAgIG4gPSBpbnQoc2VsZi5oZWFkZXJzLmdldCgiQ29udGVudC1MZW5ndGgiLCAiMCIpIG9yIDApCiAgICAgICAgdHJ5OiByZXR1cm4ganNvbi5sb2FkcyhzZWxmLnJmaWxlLnJlYWQobikgb3IgYiJ7fSIpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogcmV0dXJuIHt9CiAgICBkZWYgZG9fT1BUSU9OUyhzZWxmKTogc2VsZi5fc2VuZCgyMDQsIGIiIiwgInRleHQvcGxhaW4iKQogICAgZGVmIGRvX0dFVChzZWxmKToKICAgICAgICBwID0gc2VsZi5wYXRoLnNwbGl0KCI/IiwgMSlbMF0KICAgICAgICBpZiBwID09ICIvaGVhbHRoIjogcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCB7InN0YXR1cyI6ICJvayIsICJzZXJ2aWNlIjogInRvZG8iLCAiYnVpbGQiOiBfYnVpbGRfc3RhbXAoKX0pCiAgICAgICAgaWYgcCBpbiAoIi90b2RvcyIsICIvdG9kb3MvIiwgIi8iKToKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgaHRtbCA9IEhUTUxfUEFUSC5yZWFkX3RleHQoKS5yZXBsYWNlKCJfX1FVRVVFX1NFQ1JFVF9fIiwgU0VDUkVUKS5yZXBsYWNlKCJfX0JVSUxEX18iLCBfYnVpbGRfc3RhbXAoKSkKICAgICAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgaHRtbCwgInRleHQvaHRtbDsgY2hhcnNldD11dGYtOCIpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZTogcmV0dXJuIHNlbGYuX3NlbmQoNTAwLCB7ImVycm9yIjogZiJodG1sOiB7ZX0ifSkKICAgICAgICBpZiBwLnN0YXJ0c3dpdGgoIi90b2RvL3Byb29mLyIpOiAgICAgIyBzZXJ2ZSBwcm9vZiBiaW5hcmllcyAocHVibGljLCBzbyA8aW1nIHNyYz4gd29ya3MpCiAgICAgICAgICAgIHNlZyA9IHBbbGVuKCIvdG9kby9wcm9vZi8iKTpdLnN0cmlwKCIvIikuc3BsaXQoIi8iKQogICAgICAgICAgICBpZiBsZW4oc2VnKSA9PSAyIGFuZCBzZWdbMV0gYW5kICIuLiIgbm90IGluIHNlZ1swXSBhbmQgIi4uIiBub3QgaW4gc2VnWzFdOgogICAgICAgICAgICAgICAgZnAgPSBQUk9PRl9ESVIgLyBzZWdbMF0gLyBzZWdbMV0KICAgICAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgICAgICBkYXRhID0gZnAucmVhZF9ieXRlcygpCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gc2VsZi5fc2VuZCg0MDQsIHsiZXJyb3IiOiAibm8gc3VjaCBwcm9vZiJ9KQogICAgICAgICAgICAgICAgZXh0ID0gZnAuc3VmZml4Lmxvd2VyKCkubHN0cmlwKCIuIikKICAgICAgICAgICAgICAgIGN0eXBlID0geyJwbmciOiJpbWFnZS9wbmciLCJqcGciOiJpbWFnZS9qcGVnIiwianBlZyI6ImltYWdlL2pwZWciLCJnaWYiOiJpbWFnZS9naWYiLAogICAgICAgICAgICAgICAgICAgICAgICAgIndlYnAiOiJpbWFnZS93ZWJwIiwic3ZnIjoiaW1hZ2Uvc3ZnK3htbCIsIm1wNCI6InZpZGVvL21wNCIsIndlYm0iOiJ2aWRlby93ZWJtIiwKICAgICAgICAgICAgICAgICAgICAgICAgICJtb3YiOiJ2aWRlby9xdWlja3RpbWUifS5nZXQoZXh0LCAiYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFtIikKICAgICAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZXJ2ZV9ieXRlcyhkYXRhLCBjdHlwZSkgICAjIFJhbmdlLWF3YXJlIC0+IGlubGluZSB2aWRlbyBwbGF5YmFjayArIHNlZWtpbmcKICAgICAgICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoNDA0LCB7ImVycm9yIjogImJhZCBwcm9vZiBwYXRoIn0pCiAgICAgICAgaWYgcCA9PSAiL3RvZG8vYm9hcmQiOgogICAgICAgICAgICBpZiBub3Qgc2VsZi5fYXV0aCgpOiByZXR1cm4gc2VsZi5fc2VuZCg0MDMsIHsiZXJyb3IiOiAidW5hdXRob3JpemVkIn0pCiAgICAgICAgICAgIHdpdGggX2xvY2s6IGIgPSBtaWdyYXRlX3Byb29mcyhsb2FkKCkpCiAgICAgICAgICAgIGIgPSBkaWN0KGIpOyBiWyJidWlsZCJdID0gX2J1aWxkX3N0YW1wKCkgICAgICAjIGNsaWVudCBhdXRvLXJlbG9hZHMgaWYgdGhlIHNlcnZlZCBIVE1MIGJ1aWxkIGNoYW5nZWQgKGtpbGxzIHN0YWxlLUpTIGJ1Z3MpCiAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgYikKICAgICAgICBpZiBwID09ICIvdG9kby9hdHRhY2giOiAgICAgICAgICAgICAgICMgcmVzb2x2ZSBhbiBhc3NpZ25lZSAtPiB0dHlkIGF0dGFjaCB0YXJnZXQgKHNsaWNlIGMpCiAgICAgICAgICAgIGlmIG5vdCBzZWxmLl9hdXRoKCk6IHJldHVybiBzZWxmLl9zZW5kKDQwMywgeyJlcnJvciI6ICJ1bmF1dGhvcml6ZWQifSkKICAgICAgICAgICAgYWdlbnQgPSAocGFyc2VfcXModXJscGFyc2Uoc2VsZi5wYXRoKS5xdWVyeSkuZ2V0KCJhZ2VudCIpIG9yIFsiIl0pWzBdCiAgICAgICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDIwMCwgcmVzb2x2ZV9hdHRhY2goYWdlbnQpKQogICAgICAgIGlmIHAgPT0gIi90b2RvL3dhIjogICAgICAgICAgICAgICAgICAgIyBpbnNwZWN0IHRoZSBXaGF0c0FwcCBvdXRib3ggKHNsaWNlIGUpCiAgICAgICAgICAgIGlmIG5vdCBzZWxmLl9hdXRoKCk6IHJldHVybiBzZWxmLl9zZW5kKDQwMywgeyJlcnJvciI6ICJ1bmF1dGhvcml6ZWQifSkKICAgICAgICAgICAgd2l0aCBfd2FfbG9jazogbyA9IHdhX2xvYWQoKQogICAgICAgICAgICBwZW5kID0gW2UgZm9yIGUgaW4gb1sicXVldWUiXSBpZiBlLmdldCgic2VudEF0IikgaXMgTm9uZSBhbmQgbm90IGUuZ2V0KCJjYW5jZWxlZCIpXQogICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIHsiamlkIjogV0FfQ0hBVF9KSUQsICJkcmFpbiI6IFdBX0RSQUlOX09OLCAicGVuZGluZyI6IGxlbihwZW5kKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgInF1ZXVlIjogb1sicXVldWUiXVstNTA6XX0pCiAgICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoNDA0LCB7ImVycm9yIjogIm5vdCBmb3VuZCJ9KQogICAgZGVmIGRvX1BPU1Qoc2VsZik6CiAgICAgICAgcCA9IHNlbGYucGF0aC5zcGxpdCgiPyIsIDEpWzBdCiAgICAgICAgaWYgcCA9PSAiL2hvb2svc3RvcCI6ICAgICAgICAgICAgIyB1c2VkIGJ5IHRoZSBzdG9wLWhvb2sgYnJpZGdlIC8gc2ltLXN0b3AtaG9vawogICAgICAgICAgICBkID0gc2VsZi5fYm9keSgpOyBvbl9zdG9wX2hvb2soZC5nZXQoImFnZW50IiwgIiIpLCBkLmdldCgic3RhdGUiLCAiaWRsZSIpKQogICAgICAgICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIHsib2siOiBUcnVlfSkKICAgICAgICBpZiBub3Qgc2VsZi5fYXV0aCgpOiByZXR1cm4gc2VsZi5fc2VuZCg0MDMsIHsiZXJyb3IiOiAiZm9yYmlkZGVuIn0pCiAgICAgICAgZCA9IHNlbGYuX2JvZHkoKQogICAgICAgIGlmIHAgPT0gIi90b2RvL3VwZGF0ZSI6ICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIGFwcGx5X3VwZGF0ZShkKSkKICAgICAgICBpZiBwID09ICIvdG9kby9icmFpbnN0b3JtIjogcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV9icmFpbnN0b3JtKGQpKQogICAgICAgIGlmIHAgPT0gIi90b2RvL3N0YXR1cyI6ICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIGFwcGx5X3N0YXR1cyhkKSkKICAgICAgICBpZiBwID09ICIvdG9kby9wcm9vZiI6ICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV9wcm9vZihkKSkKICAgICAgICBpZiBwID09ICIvdG9kby9jb21tZW50IjogICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCBhcHBseV9jb21tZW50KGQpKQogICAgICAgIGlmIHAgPT0gIi90b2RvL2Fuc3dlciI6ICAgICByZXR1cm4gc2VsZi5fc2VuZCgyMDAsIGFwcGx5X2Fuc3dlcihkKSkKICAgICAgICBpZiBwID09ICIvdG9kby93YS90ZXN0IjogICAgIyBlbnF1ZXVlIGEgb25lLW9mZiBtZXNzYWdlIChwcm9vZiAvIHNtb2tlKSAtPiBkcmFpbmVkIHRvIENFTyBXaGF0c0FwcAogICAgICAgICAgICB0eHQgPSAoZC5nZXQoInRleHQiKSBvciAiQm9hcmQgdGVzdCBwaW5nLiIpLnN0cmlwKCkKICAgICAgICAgICAgd2l0aCBfd2FfbG9jazoKICAgICAgICAgICAgICAgIG8gPSB3YV9sb2FkKCk7IG9bInF1ZXVlIl0uYXBwZW5kKHsiaWQiOiB1aWQoKSwgInRhc2tfaWQiOiBOb25lLCAia2luZCI6ICJ0ZXN0IiwKICAgICAgICAgICAgICAgICAgICAiZGVkdXBLZXkiOiBmInRlc3Q6e3VpZCgpfSIsICJ0ZXh0IjogdHh0LCAiY3JlYXRlZCI6IG5vdygpLCAic2VudEF0IjogTm9uZSwKICAgICAgICAgICAgICAgICAgICAiYXR0ZW1wdHMiOiAwLCAibGFzdEVycm9yIjogIiIsICJjYW5jZWxlZCI6IEZhbHNlfSk7IHdhX3NhdmUobykKICAgICAgICAgICAgcmV0dXJuIHNlbGYuX3NlbmQoMjAwLCB7Im9rIjogVHJ1ZSwgImVucXVldWVkIjogdHh0fSkKICAgICAgICBpZiBwID09ICIvdG9kby93YS9kcmFpbiI6ICAgdGhyZWFkaW5nLlRocmVhZCh0YXJnZXQ9d2FfZHJhaW5fb25jZSwgZGFlbW9uPVRydWUpLnN0YXJ0KCk7IHJldHVybiBzZWxmLl9zZW5kKDIwMCwgeyJvayI6IFRydWV9KQogICAgICAgIHJldHVybiBzZWxmLl9zZW5kKDQwNCwgeyJlcnJvciI6ICJub3QgZm91bmQifSkKCmNsYXNzIFNlcnZlcihodHRwLnNlcnZlci5UaHJlYWRpbmdIVFRQU2VydmVyKToKICAgIGRhZW1vbl90aHJlYWRzID0gVHJ1ZTsgYWxsb3dfcmV1c2VfYWRkcmVzcyA9IFRydWUKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBUT0RPX0RJUi5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICBpZiBub3QgQk9BUkRfUEFUSC5leGlzdHMoKTogc2F2ZShfZGVmYXVsdF9ib2FyZCgpKQogICAgdGhyZWFkaW5nLlRocmVhZCh0YXJnZXQ9Y3Jvbl9sb29wLCBkYWVtb249VHJ1ZSkuc3RhcnQoKQogICAgdGhyZWFkaW5nLlRocmVhZCh0YXJnZXQ9d2F0Y2hkb2dfbG9vcCwgZGFlbW9uPVRydWUpLnN0YXJ0KCkKICAgIGlmIFdBX0RSQUlOX09OOiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHNsaWNlIGU6IENFTy1ibG9ja2VkIHdhdGNoZG9nICsgV2hhdHNBcHAgZHJhaW4gcGFydGljaXBhbnQKICAgICAgICB0aHJlYWRpbmcuVGhyZWFkKHRhcmdldD13YV93YXRjaGRvZ19sb29wLCBkYWVtb249VHJ1ZSkuc3RhcnQoKQogICAgICAgIHRocmVhZGluZy5UaHJlYWQodGFyZ2V0PXdhX2RyYWluX2xvb3AsIGRhZW1vbj1UcnVlKS5zdGFydCgpCiAgICBwcmludChmInRvZG8gOntQT1JUfSAgc3RvcmU9e0JPQVJEX1BBVEh9ICBjcm9uPXtQSU5HX0NST059cyBncmFjZT17SURMRV9HUkFDRX1zICIKICAgICAgICAgIGYic3RhbGw9e0lETEVfU1RBTEx9cy9zY2Fue1dBVENIRE9HfXMgc2luaz17J2ZpbGUnIGlmIFRFU1RfU0lOSyBlbHNlICdtcCd9ICIKICAgICAgICAgIGYid2E9eydvbuKGkicrV0FfQ0hBVF9KSUQgaWYgV0FfRFJBSU5fT04gZWxzZSAnb2ZmJ30iLCBmbHVzaD1UcnVlKQogICAgU2VydmVyKCgiMC4wLjAuMCIsIFBPUlQpLCBIKS5zZXJ2ZV9mb3JldmVyKCkK | base64 -d > "$INSTALL_DIR/bin/todo-server.py"
echo PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+UGxvdyDigJQgUHJpb3JpdGllcyAoVE9ETyk8L3RpdGxlPgo8bGluayBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PURNK01vbm86d2dodEA0MDA7NTAwOzcwMCZmYW1pbHk9RE0rU2FuczppdGFsLHdnaHRAMCwzMDA7MCw0MDA7MCw1MDA7MCw2MDA7MCw3MDA7MSw0MDAmZmFtaWx5PUluc3RydW1lbnQrU2VyaWY6aXRhbEAwOzEmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8c3R5bGU+Cjpyb290ewogIC0tbWlkbmlnaHQ6IzAxMDAwQTsgLS12b2x0OiNENUVGOEE7IC0tZ3JvdmU6IzVlN2E1ZTsgLS1pcmlzOiNDNEJGRkY7CiAgLS1kYXJrLWJnOiMxMTExMTA7IC0tZGFyay1ib3JkZXI6cmdiYSgyNTUsMjU1LDI1NSwwLjA5KTsKICAtLXRleHQtZGFyazojRjBGMEU4OyAtLW11dGVkLWRhcms6cmdiYSgyNDAsMjQwLDIzMiwwLjQ1KTsKICAtLXN1Y2Nlc3M6IzM0Yzc1OTsgLS1kYW5nZXI6I2ZmM2IzMDsgLS13YXJuaW5nOiNmZWJjMmU7IC0taW5mbzojNWFjOGZhOwogIC0tdm9sdC1kaW06cmdiYSgyMTMsMjM5LDEzOCwwLjE1KTsgLS12b2x0LWdsb3c6cmdiYSgyMTMsMjM5LDEzOCwwLjI1KTsKICAtLXN1cmZhY2U6cmdiYSgyNTUsMjU1LDI1NSwwLjA1KTsgLS1zdXJmYWNlMjpyZ2JhKDI1NSwyNTUsMjU1LDAuMDgpOyAtLWJvcmRlcjI6cmdiYSgyNTUsMjU1LDI1NSwwLjE1KTsKICAtLXNlcmlmOidJbnN0cnVtZW50IFNlcmlmJyxHZW9yZ2lhLHNlcmlmOyAtLXNhbnM6J0RNIFNhbnMnLHN5c3RlbS11aSxzYW5zLXNlcmlmOyAtLW1vbm86J0RNIE1vbm8nLCdTRiBNb25vJyxtb25vc3BhY2U7Cn0KKnttYXJnaW46MDtwYWRkaW5nOjA7Ym94LXNpemluZzpib3JkZXItYm94fQpodG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJnKTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjMwMDttaW4taGVpZ2h0OjEwMHZoO292ZXJmbG93LXg6aGlkZGVuOy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50aWFsaWFzZWR9CmJvZHk6OmFmdGVye2NvbnRlbnQ6Jyc7cG9zaXRpb246Zml4ZWQ7aW5zZXQ6MDtiYWNrZ3JvdW5kLWltYWdlOnVybCgiZGF0YTppbWFnZS9zdmcreG1sLCUzQ3N2ZyB2aWV3Qm94PScwIDAgMjAwIDIwMCcgeG1sbnM9J2h0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnJyUzRSUzQ2ZpbHRlciBpZD0nbiclM0UlM0NmZVR1cmJ1bGVuY2UgdHlwZT0nZnJhY3RhbE5vaXNlJyBiYXNlRnJlcXVlbmN5PScwLjc1JyBudW1PY3RhdmVzPSc0JyBzdGl0Y2hUaWxlcz0nc3RpdGNoJy8lM0UlM0MvZmlsdGVyJTNFJTNDcmVjdCB3aWR0aD0nMTAwJTI1JyBoZWlnaHQ9JzEwMCUyNScgZmlsdGVyPSd1cmwoJTIzbiknLyUzRSUzQy9zdmclM0UiKTtvcGFjaXR5OjAuMDQ7cG9pbnRlci1ldmVudHM6bm9uZTt6LWluZGV4Ojk5OTl9Ci53cmFwe21heC13aWR0aDoxMjAwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjQ4cHggNTZweCA4MHB4O3Bvc2l0aW9uOnJlbGF0aXZlO3otaW5kZXg6MX0KaGVhZGVye2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjMycHg7cGFkZGluZy1ib3R0b206MjhweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7ZmxleC13cmFwOndyYXB9Ci5icmFuZHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxOHB4fQoubWFya3t3aWR0aDo1NnB4O2hlaWdodDo1NnB4O2JvcmRlci1yYWRpdXM6MTNweDtiYWNrZ3JvdW5kOnZhcigtLXZvbHQpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtmbGV4LXNocmluazowO2JveC1zaGFkb3c6MCA0cHggMjRweCByZ2JhKDAsMCwwLC40KX0KLm1hcmsgc3Bhbntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zaXplOjM4cHg7Y29sb3I6dmFyKC0tZ3JvdmUpO2xpbmUtaGVpZ2h0OjF9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo0MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNHZ3LDU0cHgpO2xldHRlci1zcGFjaW5nOi0uMDJlbTtsaW5lLWhlaWdodDoxfQpoMSBlbXtmb250LXN0eWxlOml0YWxpYztjb2xvcjpyZ2JhKDI0MCwyNDAsMjMyLC41NSl9Ci5zdWJ0e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2xldHRlci1zcGFjaW5nOi4xMmVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTttYXJnaW4tdG9wOjZweH0KLmxpdmUtcGlsbHtkaXNwbGF5OmlubGluZS1mbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS12b2x0KTtiYWNrZ3JvdW5kOnJnYmEoMjEzLDIzOSwxMzgsLjEwKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjEzLDIzOSwxMzgsLjQ1KTtwYWRkaW5nOjVweCAxM3B4O2JvcmRlci1yYWRpdXM6MTAwcHg7dGV4dC1zaGFkb3c6MCAwIDEwcHggcmdiYSgyMTMsMjM5LDEzOCwuMjgpfQoubGl2ZS1kb3R7d2lkdGg6OHB4O2hlaWdodDo4cHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDp2YXIoLS12b2x0KTtib3gtc2hhZG93OjAgMCA4cHggdmFyKC0tdm9sdCk7YW5pbWF0aW9uOnB1bHNlIDEuNnMgZWFzZS1pbi1vdXQgaW5maW5pdGV9CiNjbG9ja3tjb2xvcjp2YXIoLS10ZXh0LWRhcmspO29wYWNpdHk6Ljg0fQpAa2V5ZnJhbWVzIHB1bHNlezAlLDEwMCV7b3BhY2l0eToxO3RyYW5zZm9ybTpzY2FsZSgxKX01MCV7b3BhY2l0eTouMzU7dHJhbnNmb3JtOnNjYWxlKC43KX19Ci5jb3VudHN7ZGlzcGxheTpmbGV4O2dhcDoxMHB4O21hcmdpbi10b3A6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtmbGV4LXdyYXA6d3JhcH0KLmNvdW50cyBzcGFue3BhZGRpbmc6NHB4IDEycHg7Ym9yZGVyLXJhZGl1czoxMDBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmFkZGJhcntkaXNwbGF5OmZsZXg7Z2FwOjEycHg7bWFyZ2luOjM0cHggMCAxNHB4O2ZsZXgtd3JhcDp3cmFwfQouYWRkYmFyIGlucHV0e2ZsZXg6MTttaW4td2lkdGg6MjgwcHg7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjIwcHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxLjVweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MTZweCAyMHB4O291dGxpbmU6bm9uZX0KLmFkZGJhciBpbnB1dDpmb2N1c3tib3JkZXItY29sb3I6dmFyKC0tZ3JvdmUpO2JveC1zaGFkb3c6MCAwIDAgM3B4IHJnYmEoOTQsMTIyLDk0LC4yNSl9Ci5idG4tdm9sdHtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbWlkbmlnaHQpO2JhY2tncm91bmQ6dmFyKC0tdm9sdCk7Ym9yZGVyOm5vbmU7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MCAzMnB4O2N1cnNvcjpwb2ludGVyO3doaXRlLXNwYWNlOm5vd3JhcH0KLmJ0bi12b2x0OmhvdmVye2ZpbHRlcjpicmlnaHRuZXNzKDEuMDYpO2JveC1zaGFkb3c6MCA0cHggMjBweCB2YXIoLS12b2x0LWdsb3cpfQouY250LWhpZGRlbntjb2xvcjp2YXIoLS1pcmlzKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnJnYmEoMTk2LDE5MSwyNTUsLjM1KSFpbXBvcnRhbnR9Ci52aWV3YmFye2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE4cHggMjhweDtmbGV4LXdyYXA6d3JhcDttYXJnaW46MThweCAwIDRweDtwYWRkaW5nOjE0cHggMDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQoudmItZ3JvdXB7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwfQoudmItbGFiZWx7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjEzZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO21hcmdpbi1yaWdodDozcHh9Ci5jaGlwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6NHB4IDExcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2N1cnNvcjpwb2ludGVyO2JvcmRlcjoxcHggc29saWQgdHJhbnNwYXJlbnQ7dXNlci1zZWxlY3Q6bm9uZTt0cmFuc2l0aW9uOmZpbHRlciAuMTVzLG9wYWNpdHkgLjE1c30KLmNoaXA6aG92ZXJ7ZmlsdGVyOmJyaWdodG5lc3MoMS4xMil9Ci5jaGlwLm9mZntiYWNrZ3JvdW5kOnRyYW5zcGFyZW50IWltcG9ydGFudDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWRhcmstYm9yZGVyKSFpbXBvcnRhbnQ7dGV4dC1kZWNvcmF0aW9uOmxpbmUtdGhyb3VnaDtvcGFjaXR5Oi41NX0KLnZiLXNlcHt3aWR0aDoxcHg7aGVpZ2h0OjIycHg7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJvcmRlcik7bWFyZ2luOjAgM3B4fQoudmJ0bntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6NXB4IDEycHg7Y3Vyc29yOnBvaW50ZXI7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO3RyYW5zaXRpb246LjE1c30KLnZidG46aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpO2NvbG9yOnZhcigtLXZvbHQpfQoudmJ0bi5vbntiYWNrZ3JvdW5kOnZhcigtLXZvbHQtZGltKTtib3JkZXItY29sb3I6dmFyKC0tdm9sdCk7Y29sb3I6dmFyKC0tdm9sdCl9CnVse2xpc3Qtc3R5bGU6bm9uZX0KLnRhc2t7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjE4cHg7cGFkZGluZzoyMHB4IDIycHg7bWFyZ2luLXRvcDoxNHB4fQoudGFzay5mcmVzaHthbmltYXRpb246ZmFkZVVwIC4ycyBlYXNlLW91dH0KQGtleWZyYW1lcyBmYWRlVXB7ZnJvbXtvcGFjaXR5OjA7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoMTZweCl9dG97b3BhY2l0eToxO3RyYW5zZm9ybTpub25lfX0KLnRhc2suZG9uZXtvcGFjaXR5Oi42fQoudGFzay5jYW5jZWxsZWR7b3BhY2l0eTouNX0KLnRhc2stdG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpmbGV4LXN0YXJ0O2dhcDoxNnB4fQouY2hlY2t7d2lkdGg6MzhweDtoZWlnaHQ6MzhweDtmbGV4LXNocmluazowO2JvcmRlci1yYWRpdXM6MTFweDtjdXJzb3I6cG9pbnRlcjtib3JkZXI6MnB4IHNvbGlkIHZhcigtLWJvcmRlcjIpO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3RyYW5zaXRpb246LjJzO2NvbG9yOiNmZmY7Zm9udC13ZWlnaHQ6NzAwfQouY2hlY2s6aG92ZXJ7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpfQouY2hlY2sub257YmFja2dyb3VuZDp2YXIoLS1zdWNjZXNzKTtib3JkZXItY29sb3I6dmFyKC0tc3VjY2Vzcyl9Ci5jaGVjay5kaXNhYmxlZHtvcGFjaXR5Oi4zO2N1cnNvcjpub3QtYWxsb3dlZH0KLnRhc2stbWFpbntmbGV4OjE7bWluLXdpZHRoOjB9Ci50YXNrLXRleHR7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtc2l6ZTpjbGFtcCgyMnB4LDIuMnZ3LDMwcHgpO2xpbmUtaGVpZ2h0OjEuMTU7bGV0dGVyLXNwYWNpbmc6LS4wMWVtO3dvcmQtYnJlYWs6YnJlYWstd29yZDtjdXJzb3I6dGV4dDtvdXRsaW5lOm5vbmV9Ci50YXNrLXRleHQ6Zm9jdXN7Ym94LXNoYWRvdzowIDJweCAwIHZhcigtLWdyb3ZlKX0KLnRhc2suZG9uZSAudGFzay10ZXh0e3RleHQtZGVjb3JhdGlvbjpsaW5lLXRocm91Z2g7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci50YXNrLmNhbmNlbGxlZCAudGFzay10ZXh0e3RleHQtZGVjb3JhdGlvbjpsaW5lLXRocm91Z2g7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci5tZXRhe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweDttYXJnaW4tdG9wOjhweDtmbGV4LXdyYXA6d3JhcH0KLmJhZGdle2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDRlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6M3B4IDEwcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQouc3QtbmVlZHNfYnJhaW5zdG9ybXtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjE4KTtjb2xvcjp2YXIoLS1pcmlzKX0KLnN0LXdvcmtpbmd7YmFja2dyb3VuZDpyZ2JhKDI1NCwxODgsNDYsLjE4KTtjb2xvcjp2YXIoLS13YXJuaW5nKX0KLnN0LXJldmlld3tiYWNrZ3JvdW5kOnJnYmEoOTAsMjAwLDI1MCwuMTYpO2NvbG9yOnZhcigtLWluZm8pfQouc3QtYmxvY2tlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDU5LDQ4LC4xNik7Y29sb3I6dmFyKC0tZGFuZ2VyKX0KLnN0LWRvbmV7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMTYpO2NvbG9yOiM1MmQ4NzN9Ci5zdC1jYW5jZWxsZWR7YmFja2dyb3VuZDpyZ2JhKDE0MiwxNDIsMTQ3LC4xOCk7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayl9Ci51bnJlYWQtYmFkZ2V7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMC41cHg7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLXZvbHQpO2JvcmRlcjoxcHggc29saWQgcmdiYSgyMTMsMjM5LDEzOCwuNyk7Ym9yZGVyLXJhZGl1czoxMDBweDtwYWRkaW5nOjNweCA5cHg7Ym94LXNoYWRvdzowIDAgMTZweCByZ2JhKDIxMywyMzksMTM4LC4yNCl9Ci50YWd7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7Ym9yZGVyLXJhZGl1czoxMDBweDtwYWRkaW5nOjNweCAxMHB4fQovKiBjbGljay10aGUtbGlua2VkLWVuZ2luZWVyIOKGkiBhdHRhY2ggdG8gaXRzIHRlcm1pbmFsIChzbGljZSBjKSAqLwoudGFnLmF0dGFjaHtjdXJzb3I6cG9pbnRlcjtjb2xvcjp2YXIoLS1pbmZvKTtib3JkZXItY29sb3I6cmdiYSg5MCwyMDAsMjUwLC40KX0KLnRhZy5hdHRhY2g6OmJlZm9yZXtjb250ZW50Oifip4kgJztvcGFjaXR5Oi44NX0KLnRhZy5hdHRhY2g6aG92ZXJ7Y29sb3I6dmFyKC0tdm9sdCk7Ym9yZGVyLWNvbG9yOnZhcigtLXZvbHQpO2JhY2tncm91bmQ6dmFyKC0tdm9sdC1kaW0pfQoucm93e2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHg7bWFyZ2luLXRvcDoxMnB4O2ZsZXgtd3JhcDp3cmFwfQouZmllbGR7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjlweCAxMnB4O291dGxpbmU6bm9uZTtmbGV4OjE7bWluLXdpZHRoOjIyMHB4fQouZmllbGQ6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWdyb3ZlKTtib3gtc2hhZG93OjAgMCAwIDJweCByZ2JhKDk0LDEyMiw5NCwuMil9Ci5sYWJlbHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzouMDZlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7bWluLXdpZHRoOjEyMHB4fQoubGFiZWwucmVxOjphZnRlcntjb250ZW50OicgKic7Y29sb3I6dmFyKC0tZGFuZ2VyKX0KLnRvZ2dsZXtkaXNwbGF5OmlubGluZS1mbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspO3VzZXItc2VsZWN0Om5vbmV9Ci50b2dnbGUuZGlzYWJsZWR7b3BhY2l0eTouNDtjdXJzb3I6bm90LWFsbG93ZWR9Ci5zd3t3aWR0aDo0MnB4O2hlaWdodDoyNHB4O2JvcmRlci1yYWRpdXM6MTAwcHg7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIyKTtwb3NpdGlvbjpyZWxhdGl2ZTt0cmFuc2l0aW9uOi4yc30KLnN3OjphZnRlcntjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO3RvcDoycHg7bGVmdDoycHg7d2lkdGg6MThweDtoZWlnaHQ6MThweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLW11dGVkLWRhcmspO3RyYW5zaXRpb246LjJzfQoudG9nZ2xlLm9uIC5zd3tiYWNrZ3JvdW5kOnZhcigtLXZvbHQtZGltKTtib3JkZXItY29sb3I6dmFyKC0tdm9sdCl9Ci50b2dnbGUub24gLnN3OjphZnRlcntsZWZ0OjIxcHg7YmFja2dyb3VuZDp2YXIoLS12b2x0KX0KLmJyYWluc3Rvcm17bWFyZ2luLXRvcDoxMHB4O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtc2l6ZToxNHB4O2xpbmUtaGVpZ2h0OjEuNTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6cmdiYSgxOTYsMTkxLDI1NSwuMDcpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB2YXIoLS1pcmlzKTtib3JkZXItcmFkaXVzOjAgOHB4IDhweCAwO3BhZGRpbmc6MTBweCAxNHB4fQouYnJhaW5zdG9ybSAuaHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1pcmlzKTtkaXNwbGF5OmJsb2NrO21hcmdpbi1ib3R0b206NHB4fQouc3RhdHVze21hcmdpbi10b3A6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLXdhcm5pbmcpO2JhY2tncm91bmQ6cmdiYSgyNTQsMTg4LDQ2LC4wOCk7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzo4cHggMTJweH0KLm5lZWRicmFpbnttYXJnaW4tdG9wOjEwcHg7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEyLjVweDtjb2xvcjp2YXIoLS1pcmlzKTtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjEpO2JvcmRlcjoxcHggc29saWQgcmdiYSgxOTYsMTkxLDI1NSwuMzUpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6OXB4IDEzcHg7Zm9udC13ZWlnaHQ6NTAwfQoucHJvb2Zze2Rpc3BsYXk6ZmxleDtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6MTBweDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5wcm9vZi1saXN0e2Rpc3BsYXk6Y29udGVudHN9Ci5wcm9vZntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6dmFyKC0tc3VyZmFjZTIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6NnB4IDEwcHg7bWF4LXdpZHRoOjI0MHB4O292ZXJmbG93OmhpZGRlbjt0ZXh0LW92ZXJmbG93OmVsbGlwc2lzO3doaXRlLXNwYWNlOm5vd3JhcDt0ZXh0LWRlY29yYXRpb246bm9uZTtkaXNwbGF5OmlubGluZS1ibG9ja30KLnByb29mLmltZ3twYWRkaW5nOjNweH0KLnByb29mLmltZyBpbWd7bWF4LXdpZHRoOjIwMHB4O21heC1oZWlnaHQ6MTQwcHg7Ym9yZGVyLXJhZGl1czo2cHg7ZGlzcGxheTpibG9ja30KLnByb29mLnZpZHtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDo1cHg7cGFkZGluZzowO21heC13aWR0aDpub25lO292ZXJmbG93OnZpc2libGU7d2hpdGUtc3BhY2U6bm9ybWFsO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Ym9yZGVyOm5vbmV9Ci5wcm9vZi52aWQgdmlkZW97d2lkdGg6MzgwcHg7bWF4LXdpZHRoOjc4dnc7Ym9yZGVyLXJhZGl1czoxMHB4O2JhY2tncm91bmQ6IzAwMDtkaXNwbGF5OmJsb2NrO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQoucHJvb2YudmlkIC52Y2Fwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLXZvbHQpO3RleHQtZGVjb3JhdGlvbjpub25lfQoucHJvb2YudmlkIC52Y2FwOmhvdmVye3RleHQtZGVjb3JhdGlvbjp1bmRlcmxpbmV9Ci5wcm9vZi5tb3Jle2N1cnNvcjpwb2ludGVyO2NvbG9yOnZhcigtLXZvbHQpO2JvcmRlci1jb2xvcjpyZ2JhKDIxMywyMzksMTM4LC40NSk7YmFja2dyb3VuZDpyZ2JhKDIxMywyMzksMTM4LC4xMCk7Zm9udC13ZWlnaHQ6NzAwfQoucHJvb2YubW9yZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tdm9sdCk7YmFja2dyb3VuZDp2YXIoLS12b2x0LWRpbSl9Ci5jdHJsc3tkaXNwbGF5OmZsZXg7Z2FwOjZweDtmbGV4LXNocmluazowfQouaWN0cmx7bWluLXdpZHRoOjM0cHg7aGVpZ2h0OjM0cHg7cGFkZGluZzowIDhweDtib3JkZXItcmFkaXVzOjlweDtjdXJzb3I6cG9pbnRlcjtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2ZvbnQtc2l6ZToxNHB4O2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcn0KLmljdHJsOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS12b2x0KTtjb2xvcjp2YXIoLS12b2x0KX0KLmljdHJsLmRlbDpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tZGFuZ2VyKTtjb2xvcjp2YXIoLS1kYW5nZXIpfQouZW1wdHl7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo3MHB4IDIwcHg7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtc3R5bGU6aXRhbGljO2ZvbnQtc2l6ZToyOHB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspfQoucGluZ3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLnRhc2stb3BlbnttYXJnaW4tbGVmdDphdXRvO2N1cnNvcjpwb2ludGVyfQovKiDilIDilIAgaXNzdWUtc3R5bGUgY2FyZCB2aWV3IChzbGljZSBiKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAgKi8KLm1vZGFse3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7ei1pbmRleDoxMDAwO2Rpc3BsYXk6bm9uZTtiYWNrZ3JvdW5kOnJnYmEoMSwwLDEwLC43Mik7YmFja2Ryb3AtZmlsdGVyOmJsdXIoNHB4KTtvdmVyZmxvdy15OmF1dG87cGFkZGluZzo0MHB4IDIwcHh9Ci5tb2RhbC5zaG93e2Rpc3BsYXk6YmxvY2t9Ci5jYXJke21heC13aWR0aDo4MjBweDttYXJnaW46MCBhdXRvO2JhY2tncm91bmQ6dmFyKC0tZGFyay1iZyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIyKTtib3JkZXItcmFkaXVzOjIwcHg7Ym94LXNoYWRvdzowIDMwcHggOTBweCByZ2JhKDAsMCwwLC42KTtvdmVyZmxvdzpoaWRkZW59Ci5jYXJkLWhke3BhZGRpbmc6MjZweCAzMHB4IDIycHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO3Bvc2l0aW9uOnJlbGF0aXZlfQouY2FyZC1jbG9zZXtwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MThweDtyaWdodDoyMHB4O3dpZHRoOjM2cHg7aGVpZ2h0OjM2cHg7Ym9yZGVyLXJhZGl1czoxMHB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Zm9udC1zaXplOjIwcHg7Y3Vyc29yOnBvaW50ZXI7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyfQouY2FyZC1jbG9zZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tZGFuZ2VyKTtjb2xvcjp2YXIoLS1kYW5nZXIpfQouY2FyZC10aXRsZXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zaXplOmNsYW1wKDI2cHgsM3Z3LDM4cHgpO2xpbmUtaGVpZ2h0OjEuMTtsZXR0ZXItc3BhY2luZzotLjAxZW07cGFkZGluZy1yaWdodDo0OHB4O3dvcmQtYnJlYWs6YnJlYWstd29yZH0KLmNhcmQtc3Vie2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjlweDttYXJnaW4tdG9wOjEzcHg7ZmxleC13cmFwOndyYXB9Ci5jYXJkLWlke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspfQouY2FyZC1zdGF0dXNyb3d7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O21hcmdpbi10b3A6MTRweH0KLmNhcmQtc3RhdHVzbGJse2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMHB4O2xldHRlci1zcGFjaW5nOi4xMWVtO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmNhcmQtc3RhdGV7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcjIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6NnB4IDEycHg7Y3Vyc29yOnBvaW50ZXI7b3V0bGluZTpub25lfQouY2FyZC1zdGF0ZTpob3Zlcntib3JkZXItY29sb3I6dmFyKC0tdm9sdCl9Ci5jYXJkLXN0YXRlOmZvY3Vze2JvcmRlci1jb2xvcjp2YXIoLS1ncm92ZSk7Ym94LXNoYWRvdzowIDAgMCAycHggcmdiYSg5NCwxMjIsOTQsLjIpfQouY2FyZC1jb25ke21hcmdpbi10b3A6MTZweDtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTVweDtsaW5lLWhlaWdodDoxLjU7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKTtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjEzcHggMTZweH0KLmNhcmQtY29uZCAuaCwuY2FyZC1hcnQgLmh7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjExZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2Rpc3BsYXk6YmxvY2s7bWFyZ2luLWJvdHRvbTo2cHh9Ci5jYXJkLWFydHttYXJnaW46MTRweCAzMHB4IDA7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0LjVweDtsaW5lLWhlaWdodDoxLjU1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4wOCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDE5NiwxOTEsMjU1LC4zKTtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0taXJpcyk7Ym9yZGVyLXJhZGl1czowIDEycHggMTJweCAwO3BhZGRpbmc6MTRweCAxOHB4O3doaXRlLXNwYWNlOnByZS13cmFwO3dvcmQtYnJlYWs6YnJlYWstd29yZH0KLyogcmVsYXRpb25zOiBibG9ja2VkLWJ5IGRlcHMgKyBzdWJ0YXNrIHByb2dyZXNzIChpc3N1ZSAjMykg4oCUIGJvYXJkIGNhcmQgY2hpcHMgKi8KLnJlbHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMDNlbTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6MnB4IDhweDtkaXNwbGF5OmlubGluZS1ibG9ja30KLnJlbC5ibG9ja2Vke2JhY2tncm91bmQ6cmdiYSgyNTUsNTksNDgsLjE2KTtjb2xvcjp2YXIoLS1kYW5nZXIpfQoucmVsLnN1YnN7YmFja2dyb3VuZDpyZ2JhKDkwLDIwMCwyNTAsLjE0KTtjb2xvcjp2YXIoLS1pbmZvKX0KLnJlbC5jaGlsZHtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjE0KTtjb2xvcjp2YXIoLS1pcmlzKX0KLyogcmVsYXRpb25zIHBhbmVsIGluc2lkZSB0aGUgb3BlbmVkIGNhcmQgKGlzc3VlICMzKSAqLwouY2FyZC1yZWx7bWFyZ2luOjE0cHggMzBweCAwO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE0cHggMTZweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDoxNHB4fQoucmVsLXNlYyAuaHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMTFlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7ZGlzcGxheTpibG9jazttYXJnaW4tYm90dG9tOjhweH0KLnJlbC1yb3d7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4O3BhZGRpbmc6NXB4IDB9Ci5yZWwtbGlua3tmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2N1cnNvcjpwb2ludGVyO2ZsZXg6MTttaW4td2lkdGg6MDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpczt3aGl0ZS1zcGFjZTpub3dyYXA7dGV4dC1kZWNvcmF0aW9uOm5vbmV9Ci5yZWwtbGluazpob3Zlcntjb2xvcjp2YXIoLS12b2x0KX0KLnJlbC1kZWx7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtib3JkZXItcmFkaXVzOjdweDt3aWR0aDoyNHB4O2hlaWdodDoyNHB4O2N1cnNvcjpwb2ludGVyO2ZsZXgtc2hyaW5rOjB9Ci5yZWwtZGVsOmhvdmVye2JvcmRlci1jb2xvcjp2YXIoLS1kYW5nZXIpO2NvbG9yOnZhcigtLWRhbmdlcil9Ci5yZWwtYWRke2Rpc3BsYXk6ZmxleDtnYXA6OHB4O21hcmdpbi10b3A6OHB4fQoucmVsLWFkZCBpbnB1dCwucmVsLWFkZCBzZWxlY3R7ZmxleDoxO21pbi13aWR0aDowO2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDp2YXIoLS1kYXJrLWJnKTtib3JkZXI6MS41cHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6OHB4IDExcHg7b3V0bGluZTpub25lfQoucmVsLWFkZCBpbnB1dDpmb2N1cywucmVsLWFkZCBzZWxlY3Q6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWlyaXMpfQoucmVsLWFkZCBidXR0b257Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NjAwO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLWlyaXMpO2JvcmRlcjpub25lO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6MCAxNHB4O2N1cnNvcjpwb2ludGVyO3doaXRlLXNwYWNlOm5vd3JhcH0KLnJlbC1hZGQgYnV0dG9uOmhvdmVye2ZpbHRlcjpicmlnaHRuZXNzKDEuMDcpfQoucmVsLWdhdGV7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS10ZXh0LWRhcmspfQoucmVsLWdhdGUgLmdhdGUtaGludHtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKTtmb250LXNpemU6MTFweH0KLnJlbC1lbXB0eXtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXN0eWxlOml0YWxpYztmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmNhcmQtYXJ0IC5oe2NvbG9yOnZhcigtLWlyaXMpfQovKiBicmFpbnN0b3JtIGdhdGUg4oCUIGludGVyYWN0aXZlIFEmQSAoc2xpY2UgZCkgKi8KLmNhcmQtcWF7bWFyZ2luOjE0cHggMzBweCAwO2JvcmRlcjoxcHggc29saWQgcmdiYSgxOTYsMTkxLDI1NSwuMzIpO2JvcmRlci1yYWRpdXM6MTRweDtvdmVyZmxvdzpoaWRkZW59Ci5xYS1iYW5uZXJ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7bGV0dGVyLXNwYWNpbmc6LjAyZW07cGFkZGluZzoxMXB4IDE2cHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OXB4fQoucWEtYmFubmVyLmJsb2NrZWR7YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4xMik7Y29sb3I6dmFyKC0taXJpcyl9Ci5xYS1iYW5uZXIucmVhZHl7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMTIpO2NvbG9yOiM1MmQ4NzN9Ci5xYS1saXN0e3BhZGRpbmc6NnB4IDE2cHggMTRweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDoxNHB4fQoucWEtaXRlbSAucXtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTVweDtsaW5lLWhlaWdodDoxLjQ1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7bWFyZ2luLWJvdHRvbTo3cHh9Ci5xYS1pdGVtIC5xOjpiZWZvcmV7Y29udGVudDonUSc7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWlyaXMpO2JhY2tncm91bmQ6cmdiYSgxOTYsMTkxLDI1NSwuMTgpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MnB4IDdweDttYXJnaW4tcmlnaHQ6OXB4fQoucWEtYW5zLXJvd3tkaXNwbGF5OmZsZXg7Z2FwOjhweDthbGlnbi1pdGVtczpmbGV4LXN0YXJ0fQoucWEtYW5zLXJvdyB0ZXh0YXJlYXtmbGV4OjE7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0cHg7bGluZS1oZWlnaHQ6MS40NTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6dmFyKC0tZGFyay1iZyk7Ym9yZGVyOjEuNXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzo5cHggMTJweDtvdXRsaW5lOm5vbmU7cmVzaXplOnZlcnRpY2FsO21pbi1oZWlnaHQ6NDJweH0KLnFhLWFucy1yb3cgdGV4dGFyZWE6Zm9jdXN7Ym9yZGVyLWNvbG9yOnZhcigtLWlyaXMpO2JveC1zaGFkb3c6MCAwIDAgMnB4IHJnYmEoMTk2LDE5MSwyNTUsLjIyKX0KLnFhLWFucy1idG57Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NjAwO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtiYWNrZ3JvdW5kOnZhcigtLWlyaXMpO2JvcmRlcjpub25lO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjAgMTVweDtjdXJzb3I6cG9pbnRlcjthbGlnbi1zZWxmOnN0cmV0Y2g7d2hpdGUtc3BhY2U6bm93cmFwfQoucWEtYW5zLWJ0bjpob3ZlcntmaWx0ZXI6YnJpZ2h0bmVzcygxLjA3KX0KLnFhLWl0ZW0uYW5zd2VyZWQgLnFhLWFuc3tmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXNpemU6MTRweDtsaW5lLWhlaWdodDoxLjQ1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7YmFja2dyb3VuZDpyZ2JhKDUyLDE5OSw4OSwuMDgpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCB2YXIoLS1zdWNjZXNzKTtib3JkZXItcmFkaXVzOjAgOHB4IDhweCAwO3BhZGRpbmc6OHB4IDEycHh9Ci5xYS1pdGVtLmFuc3dlcmVkIC5xYS1hbnM6OmJlZm9yZXtjb250ZW50OifinJMgJztjb2xvcjp2YXIoLS1zdWNjZXNzKTtmb250LXdlaWdodDo3MDB9Ci5xYS1wcm9tb3Rle2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1taWRuaWdodCk7YmFja2dyb3VuZDp2YXIoLS12b2x0KTtib3JkZXI6bm9uZTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxMHB4IDE4cHg7Y3Vyc29yOnBvaW50ZXI7bWFyZ2luOjAgMTZweCAxNHB4fQoucWEtcHJvbW90ZTpob3ZlcntmaWx0ZXI6YnJpZ2h0bmVzcygxLjA2KX0KLnRocmVhZHtwYWRkaW5nOjhweCAzMHB4IDIycHh9Ci50bC1lbXB0eXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zdHlsZTppdGFsaWM7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyOHB4IDEwcHh9Ci5ldntkaXNwbGF5OmZsZXg7Z2FwOjEzcHg7cGFkZGluZzoxNXB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpfQouZXY6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci5hdnt3aWR0aDozNHB4O2hlaWdodDozNHB4O2ZsZXgtc2hyaW5rOjA7Ym9yZGVyLXJhZGl1czo1MCU7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtd2VpZ2h0OjcwMDtmb250LXNpemU6MTNweDtiYWNrZ3JvdW5kOnZhcigtLXN1cmZhY2UyKTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspfQouYXYuY2Vve2JhY2tncm91bmQ6dmFyKC0tdm9sdCk7Y29sb3I6dmFyKC0tZ3JvdmUpfQouYXYuYWdlbnR7YmFja2dyb3VuZDpyZ2JhKDkwLDIwMCwyNTAsLjIpO2NvbG9yOnZhcigtLWluZm8pfQouYXYuYnJhaW57YmFja2dyb3VuZDpyZ2JhKDE5NiwxOTEsMjU1LC4yMik7Y29sb3I6dmFyKC0taXJpcyl9Ci5ldi1ib2R5e2ZsZXg6MTttaW4td2lkdGg6MH0KLmV2LWhke2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpiYXNlbGluZTtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdpbi1ib3R0b206NXB4fQouZXYtYnl7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToxMi41cHg7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKX0KLmV2LWtpbmR7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjA2ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOnZhcigtLW11dGVkLWRhcmspO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZGFyay1ib3JkZXIpO2JvcmRlci1yYWRpdXM6MTAwcHg7cGFkZGluZzoxcHggOHB4fQouZXYtdGltZXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1tdXRlZC1kYXJrKX0KLmV2LXRleHR7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC1zaXplOjE0LjVweDtsaW5lLWhlaWdodDoxLjU1O2NvbG9yOnZhcigtLXRleHQtZGFyayk7d2hpdGUtc3BhY2U6cHJlLXdyYXA7d29yZC1icmVhazpicmVhay13b3JkfQouZXYuYnJhaW5zdG9ybSAuZXYtdGV4dHtiYWNrZ3JvdW5kOnJnYmEoMTk2LDE5MSwyNTUsLjA3KTtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjEwcHggMTNweH0KLyogc3RhdGUtdHJhbnNpdGlvbjogY29tcGFjdCBjZW50ZXJlZCB0aW1lbGluZSBtYXJrZXIsIG5vIGF2YXRhciAqLwouZXYuc3RhdGV7cGFkZGluZzo5cHggMDtib3JkZXItYm90dG9tOm5vbmU7anVzdGlmeS1jb250ZW50OmNlbnRlcjtnYXA6OHB4O2FsaWduLWl0ZW1zOmNlbnRlcn0KLmV2LnN0YXRlIC5ldi10ZXh0e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41cHg7Y29sb3I6dmFyKC0tbXV0ZWQtZGFyayk7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjEwMHB4O3BhZGRpbmc6NHB4IDEzcHg7d2hpdGUtc3BhY2U6bm93cmFwfQouZXYtcHJvb2Zze2Rpc3BsYXk6ZmxleDtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6OHB4O2FsaWduLWl0ZW1zOmZsZXgtc3RhcnR9Ci8qIG9wZW5lZC1jYXJkIGF0dGFjaG1lbnRzIHJlbmRlciBGVUxMLVdJRFRIICYgdW5jcm9wcGVkIOKAlCB0aGUgMjAww5cxNDAgY2FwIGlzIG9ubHkgZm9yIHRoZSBzbWFsbAogICBib2FyZC1jYXJkIHRodW1ibmFpbHMgKC5wcm9vZnMpLCBuZXZlciB0aGUgb3BlbmVkIGlzc3VlIGNhcmQuIEVhY2ggbWVkaWEgdGFrZXMgaXRzIG93biByb3cuICovCi5ldi1wcm9vZnMgLnByb29mLmltZ3tmbGV4OjEgMSAxMDAlO21heC13aWR0aDoxMDAlO3BhZGRpbmc6MDtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2JvcmRlcjpub25lO292ZXJmbG93OnZpc2libGU7d2hpdGUtc3BhY2U6bm9ybWFsO2Rpc3BsYXk6YmxvY2t9Ci5ldi1wcm9vZnMgLnByb29mLmltZyBpbWd7bWF4LXdpZHRoOjEwMCU7d2lkdGg6YXV0bzttYXgtaGVpZ2h0Ojc4dmg7aGVpZ2h0OmF1dG87b2JqZWN0LWZpdDpjb250YWluO2JvcmRlci1yYWRpdXM6MTBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKX0KLmV2LXByb29mcyAucHJvb2Yudmlke2ZsZXg6MSAxIDEwMCU7bWF4LXdpZHRoOjEwMCV9Ci5ldi1wcm9vZnMgLnByb29mLnZpZCB2aWRlb3t3aWR0aDoxMDAlO21heC13aWR0aDoxMDAlfQouZXYtcHJvb2ZzIC5wcm9vZnttYXgtd2lkdGg6MTAwJX0KLmNvbXBvc2Vye2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Z2FwOjEwcHg7cGFkZGluZzoxOHB4IDMwcHggMjZweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlKX0KLmNvbXBvc2VyIHRleHRhcmVhe2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2ZvbnQtc2l6ZToxNXB4O2xpbmUtaGVpZ2h0OjEuNTtjb2xvcjp2YXIoLS10ZXh0LWRhcmspO2JhY2tncm91bmQ6dmFyKC0tZGFyay1iZyk7Ym9yZGVyOjEuNXB4IHNvbGlkIHZhcigtLWRhcmstYm9yZGVyKTtib3JkZXItcmFkaXVzOjEycHg7cGFkZGluZzoxM3B4IDE1cHg7b3V0bGluZTpub25lO3Jlc2l6ZTp2ZXJ0aWNhbDttaW4taGVpZ2h0Ojc4cHh9Ci5jb21wb3NlciB0ZXh0YXJlYTpmb2N1c3tib3JkZXItY29sb3I6dmFyKC0tZ3JvdmUpO2JveC1zaGFkb3c6MCAwIDAgM3B4IHJnYmEoOTQsMTIyLDk0LC4yMil9Ci5jb21wb3NlciAuY3Jvd3tkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2dhcDoxMnB4O2ZsZXgtd3JhcDp3cmFwfQouY29tcG9zZXIgLmNoaW50e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLW11dGVkLWRhcmspfQouY29tcG9zZXIgLmNidG5ze2Rpc3BsYXk6ZmxleDtnYXA6OXB4fQouY2J0bntmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXdlaWdodDo2MDA7Zm9udC1zaXplOjE0cHg7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6OXB4IDE4cHg7Y3Vyc29yOnBvaW50ZXI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1kYXJrLWJvcmRlcik7YmFja2dyb3VuZDp2YXIoLS1zdXJmYWNlMik7Y29sb3I6dmFyKC0tdGV4dC1kYXJrKX0KLmNidG4ucHJpbWFyeXtiYWNrZ3JvdW5kOnZhcigtLXZvbHQpO2NvbG9yOnZhcigtLW1pZG5pZ2h0KTtib3JkZXI6bm9uZTtmb250LXdlaWdodDo3MDB9Ci5jYnRuLnByaW1hcnk6aG92ZXJ7ZmlsdGVyOmJyaWdodG5lc3MoMS4wNil9CkBtZWRpYShtYXgtd2lkdGg6NzYwcHgpey53cmFwe3BhZGRpbmc6MzBweCAxOHB4IDYwcHh9aGVhZGVye2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjthbGlnbi1pdGVtczpmbGV4LXN0YXJ0fS5tb2RhbHtwYWRkaW5nOjB9LmNhcmR7Ym9yZGVyLXJhZGl1czowO21pbi1oZWlnaHQ6MTAwdmh9LmNhcmQtYXJ0e21hcmdpbi1sZWZ0OjE4cHg7bWFyZ2luLXJpZ2h0OjE4cHh9LnRocmVhZCwuY29tcG9zZXIsLmNhcmQtaGR7cGFkZGluZy1sZWZ0OjE4cHg7cGFkZGluZy1yaWdodDoxOHB4fX0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBjbGFzcz0id3JhcCI+CiAgPGhlYWRlcj4KICAgIDxkaXY+CiAgICAgIDxkaXYgY2xhc3M9ImJyYW5kIj4KICAgICAgICA8ZGl2IGNsYXNzPSJtYXJrIj48c3Bhbj5QPC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXY+PGgxPlByaW9yaXRpZXM8L2gxPjxkaXYgY2xhc3M9InN1YnQiPkJvc3Mgc291cmNlLW9mLXRydXRoIMK3IE15UGVvcGxlPC9kaXY+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjb3VudHMiIGlkPSJjb3VudHMiPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IHN0eWxlPSJ0ZXh0LWFsaWduOnJpZ2h0Ij4KICAgICAgPHNwYW4gY2xhc3M9ImxpdmUtcGlsbCI+PHNwYW4gY2xhc3M9ImxpdmUtZG90Ij48L3NwYW4+PHNwYW4gaWQ9ImNvbm4iPmxpdmU8L3NwYW4+PC9zcGFuPgogICAgICA8ZGl2IGNsYXNzPSJzdWJ0IiBpZD0iY2xvY2siIHN0eWxlPSJtYXJnaW4tdG9wOjhweCI+4oCUPC9kaXY+CiAgICA8L2Rpdj4KICA8L2hlYWRlcj4KICA8ZGl2IGNsYXNzPSJhZGRiYXIiPgogICAgPGlucHV0IGlkPSJuZXdJdGVtIiB0eXBlPSJ0ZXh0IiBwbGFjZWhvbGRlcj0iQWRkIGEgcHJpb3JpdHkgYW5kIGhpdCBFbnRlcuKApiIgYXV0b2NvbXBsZXRlPSJvZmYiPgogICAgPGJ1dHRvbiBjbGFzcz0iYnRuLXZvbHQiIGlkPSJhZGRCdG4iPkFkZDwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InZpZXdiYXIiPgogICAgPGRpdiBjbGFzcz0idmItZ3JvdXAiPgogICAgICA8c3BhbiBjbGFzcz0idmItbGFiZWwiPnNob3c8L3NwYW4+CiAgICAgIDxzcGFuIGlkPSJzaG93Q2hpcHMiIHN0eWxlPSJkaXNwbGF5OmNvbnRlbnRzIj48L3NwYW4+CiAgICAgIDxzcGFuIGNsYXNzPSJ2Yi1zZXAiPjwvc3Bhbj4KICAgICAgPGJ1dHRvbiBjbGFzcz0idmJ0biIgZGF0YS1wcmVzZXQ9ImFsbCI+YWxsPC9idXR0b24+CiAgICAgIDxidXR0b24gY2xhc3M9InZidG4iIGRhdGEtcHJlc2V0PSJoaWRlLWRvbmUiPmhpZGUgZG9uZTwvYnV0dG9uPgogICAgICA8YnV0dG9uIGNsYXNzPSJ2YnRuIiBkYXRhLXByZXNldD0ib25seS1kb25lIj5vbmx5IGRvbmU8L2J1dHRvbj4KICAgICAgPHNwYW4gY2xhc3M9InZiLXNlcCI+PC9zcGFuPgogICAgICA8YnV0dG9uIGNsYXNzPSJ2YnRuIiBkYXRhLXRvZ2dsZT0idW5yZWFkIiB0aXRsZT0ic2hvdyBvbmx5IGNhcmRzIHdpdGggYSBuZXcsIHVucmVhZCB1cGRhdGUg4oCUIG9wZW5pbmcgb25lIGNsZWFycyBpdCI+dW5yZWFkIG9ubHk8L2J1dHRvbj4KICAgIDwvZGl2PgogIDwvZGl2PgogIDx1bCBpZD0ibGlzdCI+PC91bD4KPC9kaXY+Cgo8IS0tIGlzc3VlLXN0eWxlIGNhcmQgdmlldyAoc2xpY2UgYik6IGZ1bGwgbWVzc2FnZSBoaXN0b3J5ICsgcHJvb2ZzICsgYnJhaW5zdG9ybSBhcnRpZmFjdCAtLT4KPGRpdiBjbGFzcz0ibW9kYWwiIGlkPSJjYXJkTW9kYWwiPgogIDxkaXYgY2xhc3M9ImNhcmQiIGlkPSJjYXJkSW5uZXIiPgogICAgPGRpdiBjbGFzcz0iY2FyZC1oZCI+CiAgICAgIDxidXR0b24gY2xhc3M9ImNhcmQtY2xvc2UiIGlkPSJjYXJkQ2xvc2UiIHRpdGxlPSJjbG9zZSAoRXNjKSI+w5c8L2J1dHRvbj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZC10aXRsZSIgaWQ9ImNhcmRUaXRsZSI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQtc3ViIiBpZD0iY2FyZFN1YiI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQtc3RhdHVzcm93Ij48c3BhbiBjbGFzcz0iY2FyZC1zdGF0dXNsYmwiPm1vdmUgdG88L3NwYW4+PHNlbGVjdCBjbGFzcz0iY2FyZC1zdGF0ZSIgaWQ9ImNhcmRTdGF0ZSI+PC9zZWxlY3Q+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQtY29uZCIgaWQ9ImNhcmRDb25kIiBzdHlsZT0iZGlzcGxheTpub25lIj48c3BhbiBjbGFzcz0iaCI+ZG9uZS1jb25kaXRpb248L3NwYW4+PHNwYW4gaWQ9ImNhcmRDb25kQm9keSI+PC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkLXFhIiBpZD0iY2FyZFFhIiBzdHlsZT0iZGlzcGxheTpub25lIj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQtYXJ0IiBpZD0iY2FyZEFydCIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PHNwYW4gY2xhc3M9ImgiPmJyYWluc3Rvcm0gYXJ0aWZhY3Q8L3NwYW4+PHNwYW4gaWQ9ImNhcmRBcnRCb2R5Ij48L3NwYW4+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkLXJlbCIgaWQ9ImNhcmRSZWwiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjwvZGl2PgogICAgPGRpdiBjbGFzcz0idGhyZWFkIiBpZD0iY2FyZFRocmVhZCI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjb21wb3NlciI+CiAgICAgIDx0ZXh0YXJlYSBpZD0iY2FyZENvbXBvc2UiIHBsYWNlaG9sZGVyPSJMZWF2ZSBhIGNvbW1lbnQgYXMgQ0VP4oCmIj48L3RleHRhcmVhPgogICAgICA8ZGl2IGNsYXNzPSJjcm93Ij4KICAgICAgICA8c3BhbiBjbGFzcz0iY2hpbnQiPuKMmC9DdHJsICsgRW50ZXIgdG8gY29tbWVudDwvc3Bhbj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYnRucyI+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJjYnRuIHByaW1hcnkiIGlkPSJjYXJkQ29tbWVudEJ0biI+Q29tbWVudDwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0IFNFQ1JFVD0iX19RVUVVRV9TRUNSRVRfXyI7CmNvbnN0IEJVSUxEPSJfX0JVSUxEX18iOyAgIC8vIHNlcnZlciBzdGFtcHMgdGhlIEhUTUwgbXRpbWU7IGlmIGEgbmV3ZXIgYm9hcmQgc2hpcHMsIHRoZSBvcGVuIHBhZ2UgYXV0by1yZWxvYWRzIChubyBzdGFsZS1KUyBidWdzKQpjb25zdCBsaXN0RWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2xpc3QnKSwgaW5wdXQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ25ld0l0ZW0nKTsKbGV0IGJvYXJkPXt2ZXJzaW9uOiJ2MiIsb3JkZXI6W10sdGFza3M6e319Owpjb25zdCBlbHM9e307ICAgICAgICAgICAgICAgICAgICAgICAgIC8vIHRhc2sgaWQgLT4gPGxpPiAod2l0aCBsaS5fciBjYWNoZWQgY2hpbGQgcmVmcykKY29uc3QgSE9NRV9NRURJQV9QUkVWSUVXX0xJTUlUPTM7CmNvbnN0IFJFQURfS0VZPSd0b2RvQ2VvUmVhZC52MScsIFJFQURfU0VFREVEX0tFWT0ndG9kb0Nlb1JlYWRTZWVkZWQudjEnOwpsZXQgcmVhZFN0YXRlPXt9Owp0cnl7IHJlYWRTdGF0ZT1KU09OLnBhcnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKFJFQURfS0VZKXx8J3t9Jyl8fHt9OyB9Y2F0Y2goZSl7IHJlYWRTdGF0ZT17fTsgfQpsZXQgcmVhZFNlZWRlZD1sb2NhbFN0b3JhZ2UuZ2V0SXRlbShSRUFEX1NFRURFRF9LRVkpPT09JzEnOwoKY29uc3QgSD0oKT0+KHsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbicsLi4uKFNFQ1JFVD97J1gtUXVldWUtU2VjcmV0JzpTRUNSRVR9Ont9KX0pOwphc3luYyBmdW5jdGlvbiBhcGkocGF0aCxib2R5KXtjb25zdCByPWF3YWl0IGZldGNoKHBhdGgse21ldGhvZDonUE9TVCcsaGVhZGVyczpIKCksYm9keTpKU09OLnN0cmluZ2lmeShib2R5KX0pO3JldHVybiByLmpzb24oKTt9CmNvbnN0IHVwZD1iPT5hcGkoJy90b2RvL3VwZGF0ZScsYiksIHN0YXR1c0FwaT1iPT5hcGkoJy90b2RvL3N0YXR1cycsYiksIGJyYWluc3Rvcm1BcGk9Yj0+YXBpKCcvdG9kby9icmFpbnN0b3JtJyxiKSwgcHJvb2ZBcGk9Yj0+YXBpKCcvdG9kby9wcm9vZicsYiksIGNvbW1lbnRBcGk9Yj0+YXBpKCcvdG9kby9jb21tZW50JyxiKSwgYW5zd2VyQXBpPWI9PmFwaSgnL3RvZG8vYW5zd2VyJyxiKTsKY29uc3QgU1RMQUJFTD17bmVlZHNfYnJhaW5zdG9ybTonbmVlZHMgYnJhaW5zdG9ybScsd29ya2luZzond29ya2luZycscmV2aWV3OidyZXZpZXcgKENFTyknLGJsb2NrZWQ6J2Jsb2NrZWQnLGRvbmU6J2RvbmUnLGNhbmNlbGxlZDonY2FuY2VsbGVkJ307CgovLyDilIDilIAgQ0xJQ0stVEhFLUxJTktFRC1FTkdJTkVFUiDihpIgQVRUQUNIIChzbGljZSBjKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKLy8gT3BlbiB0aGUgYXNzaWduZWUncyBsaXZlIHRlcm1pbmFsIGluIGEgbmV3IHRhYiB2aWEgdHR5ZCDigJQgdGhlIFNBTUUgZWZmZWN0IGFzIHRoZSBIVUQKLy8gYXR0YWNoLiBUaGUgc2VydmVyIHJlc29sdmVzIHRoZSB0bXV4IHRhcmdldCAobWMtPHNlc3Npb24+Ojx0YWI+KSArIHRoZSBob3N0J3MgdHR5ZCBiYXNlCi8vIGZyb20gdGhlIHF1ZXVlIC9jbGllbnRzOyB3ZSBhc3NlbWJsZSB0aGUgVVJMIHdpdGggdGhlIFNBTUUgYDxsb2NhdGlvbi5ob3N0bmFtZT46NzY4MWAKLy8gZmFsbGJhY2sgdGhlIEhVRCB1c2VzIHdoZW4gYSBob3N0IGFkdmVydGlzZXMgbm8gYXR0YWNoX2Jhc2UgKHRoZSBsb2NhbCBub2RlKS4KYXN5bmMgZnVuY3Rpb24gYXR0YWNoVG9FbmdpbmVlcihhZ2VudCl7CiAgaWYoIWFnZW50KSByZXR1cm47CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnL3RvZG8vYXR0YWNoP2FnZW50PScrZW5jb2RlVVJJQ29tcG9uZW50KGFnZW50KSx7aGVhZGVyczpIKCl9KTsKICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBpZighZC5vayl7IGFsZXJ0KGQuZXJyb3J8fCdjYW5ub3QgYXR0YWNoIHRvIHRoaXMgYXNzaWduZWUnKTsgcmV0dXJuOyB9CiAgICBjb25zdCBiYXNlPWQuYmFzZSB8fCAoJ2h0dHA6Ly8nKyhsb2NhdGlvbi5ob3N0bmFtZXx8JzEyNy4wLjAuMScpKyc6NzY4MScpOwogICAgd2luZG93Lm9wZW4oYmFzZSsnLz9hcmc9LXQmYXJnPScrZW5jb2RlVVJJQ29tcG9uZW50KGQudGFyZ2V0KSwnX2JsYW5rJywnbm9vcGVuZXInKTsKICB9Y2F0Y2goZSl7IGFsZXJ0KCdhdHRhY2ggZmFpbGVkOiAnK2UpOyB9Cn0KLy8gYW4gYXNzaWduZWUgaXMgYXR0YWNoYWJsZSBpZmYgaXQgY2FycmllcyBhIHRtdXggc2Vzc2lvbjp0YWIgKGhvc3Qvc2Vzc2lvbjp0YWIgb3Igc2Vzc2lvbjp0YWIpCmZ1bmN0aW9uIGlzQXR0YWNoYWJsZShhc2cpeyByZXR1cm4gISFhc2cgJiYgLzpbXjovXSskLy50ZXN0KGFzZykgJiYgLyhefFwvKVteLzpdKzpbXi86XSskLy50ZXN0KGFzZyk7IH0KZnVuY3Rpb24gZXNjKHMpe3JldHVybiAoc3x8JycpLnJlcGxhY2UoLyYvZywnJmFtcDsnKS5yZXBsYWNlKC88L2csJyZsdDsnKS5yZXBsYWNlKC8+L2csJyZndDsnKS5yZXBsYWNlKC8iL2csJyZxdW90OycpO30KCi8vIOKUgOKUgCBWSUVXIExBWUVSOiBmaWx0ZXIgYnkgc3RhdHVzIChjbGllbnQtb25seTsgTkVWRVIgbXV0YXRlcyBib2FyZC5vcmRlcikg4pSA4pSACi8vIFB1cmUgcHJlc2VudGF0aW9uLiBUaGUgZHVyYWJsZSBzdG9yZSwgbWFudWFsIG9yZGVyLCBjcm9uICYgd2F0Y2hkb2cgYXJlIHVudG91Y2hlZCDigJQKLy8gdGhpcyBvbmx5IGRlY2lkZXMgd2hpY2ggY2FyZHMgc2hvdy4gQ2FyZHMgYWx3YXlzIHJlbmRlciBpbiB0aGUgQ0VPJ3MgbWFudWFsIGJvYXJkIG9yZGVyLgovLyBQZXJzaXN0ZWQgaW4gbG9jYWxTdG9yYWdlLgpjb25zdCBTVEFURVM9WyduZWVkc19icmFpbnN0b3JtJywnd29ya2luZycsJ3JldmlldycsJ2Jsb2NrZWQnLCdkb25lJywnY2FuY2VsbGVkJ107CmxldCB2aWV3PXtoaWRkZW46bmV3IFNldCgpLHVucmVhZE9ubHk6ZmFsc2V9OyAgIC8vIGhpZGRlbjogc3RhdGVzIHRvIGhpZGU7IHVucmVhZE9ubHk6IHNob3cgb25seSBjYXJkcyB3aXRoIGEgbmV3ICh1bnJlYWQpIHVwZGF0ZQp0cnl7IGNvbnN0IHY9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2UuZ2V0SXRlbSgndG9kb1ZpZXcnKXx8J3t9Jyk7CiAgICAgaWYoQXJyYXkuaXNBcnJheSh2LmhpZGRlbikpIHZpZXcuaGlkZGVuPW5ldyBTZXQodi5oaWRkZW4uZmlsdGVyKHM9PlNUQVRFUy5pbmNsdWRlcyhzKSkpOwogICAgIGlmKHR5cGVvZiB2LnVucmVhZE9ubHk9PT0nYm9vbGVhbicpIHZpZXcudW5yZWFkT25seT12LnVucmVhZE9ubHk7IH1jYXRjaChlKXt9CmZ1bmN0aW9uIHNhdmVWaWV3KCl7IHRyeXtsb2NhbFN0b3JhZ2Uuc2V0SXRlbSgndG9kb1ZpZXcnLEpTT04uc3RyaW5naWZ5KHtoaWRkZW46Wy4uLnZpZXcuaGlkZGVuXSx1bnJlYWRPbmx5OnZpZXcudW5yZWFkT25seX0pKTt9Y2F0Y2goZSl7fSB9CgovLyBhcHBseSBjdXJyZW50IGZpbHRlciB0byBhbiBvcmRlcmVkIGlkIGxpc3QgLT4gdmlzaWJsZSBpZHMgaW4gbWFudWFsIGJvYXJkIG9yZGVyLgpmdW5jdGlvbiBhcHBseVZpZXcoaWRzKXsKICBsZXQgdj1pZHMuZmlsdGVyKGlkPT4hdmlldy5oaWRkZW4uaGFzKGJvYXJkLnRhc2tzW2lkXS5zdGF0ZSkpOwogIGlmKHZpZXcudW5yZWFkT25seSkgdj12LmZpbHRlcihpZD0+dW5yZWFkQ291bnQoYm9hcmQudGFza3NbaWRdKT4wKTsgICAvLyByZXVzZSB0aGUgU0FNRSB1bnJlYWQgZGVmaW5pdGlvbiBhcyB0aGUgJ04gbmV3JyBiYWRnZSDigJQgbm8gc2VwYXJhdGUgbm90aW9uIG9mIHVucmVhZAogIHJldHVybiB2Owp9CgovLyBidWlsZCB0aGUgcGVyLXN0YXR1cyB0b2dnbGUgY2hpcHMgb25jZSwgd2lyZSB1cCBhbGwgdmlldyBjb250cm9scwpmdW5jdGlvbiBpbml0Vmlld2JhcigpewogIGNvbnN0IHdyYXA9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Nob3dDaGlwcycpOwogIHdyYXAuaW5uZXJIVE1MPVNUQVRFUy5tYXAocz0+YDxzcGFuIGNsYXNzPSJjaGlwIHN0LSR7c30iIGRhdGEtc3Q9IiR7c30iPiR7ZXNjKFNUTEFCRUxbc118fHMpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICB3cmFwLnF1ZXJ5U2VsZWN0b3JBbGwoJy5jaGlwJykuZm9yRWFjaChjPT57CiAgICBjLm9uY2xpY2s9KCk9PnsgY29uc3Qgcz1jLmRhdGFzZXQuc3Q7IHZpZXcuaGlkZGVuLmhhcyhzKT92aWV3LmhpZGRlbi5kZWxldGUocyk6dmlldy5oaWRkZW4uYWRkKHMpOyBzYXZlVmlldygpOyByZW5kZXJWaWV3YmFyKCk7IHJlY29uY2lsZSgpOyB9OwogIH0pOwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy52aWV3YmFyIFtkYXRhLXByZXNldF0nKS5mb3JFYWNoKGI9PnsKICAgIGIub25jbGljaz0oKT0+eyBjb25zdCBwPWIuZGF0YXNldC5wcmVzZXQ7CiAgICAgIGlmKHA9PT0nYWxsJykgdmlldy5oaWRkZW49bmV3IFNldCgpOwogICAgICBlbHNlIGlmKHA9PT0naGlkZS1kb25lJykgdmlldy5oaWRkZW49bmV3IFNldChbJ2RvbmUnXSk7CiAgICAgIGVsc2UgaWYocD09PSdvbmx5LWRvbmUnKSB2aWV3LmhpZGRlbj1uZXcgU2V0KFNUQVRFUy5maWx0ZXIocz0+cyE9PSdkb25lJykpOwogICAgICBzYXZlVmlldygpOyByZW5kZXJWaWV3YmFyKCk7IHJlY29uY2lsZSgpOyB9OwogIH0pOwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy52aWV3YmFyIFtkYXRhLXRvZ2dsZT0idW5yZWFkIl0nKS5mb3JFYWNoKGI9PnsKICAgIGIub25jbGljaz0oKT0+eyB2aWV3LnVucmVhZE9ubHk9IXZpZXcudW5yZWFkT25seTsgc2F2ZVZpZXcoKTsgcmVuZGVyVmlld2JhcigpOyByZWNvbmNpbGUoKTsgfTsKICB9KTsKfQpmdW5jdGlvbiByZW5kZXJWaWV3YmFyKCl7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnI3Nob3dDaGlwcyAuY2hpcCcpLmZvckVhY2goYz0+Yy5jbGFzc0xpc3QudG9nZ2xlKCdvZmYnLCB2aWV3LmhpZGRlbi5oYXMoYy5kYXRhc2V0LnN0KSkpOwogIGNvbnN0IHVuYj1kb2N1bWVudC5xdWVyeVNlbGVjdG9yKCcudmlld2JhciBbZGF0YS10b2dnbGU9InVucmVhZCJdJyk7ICAgLy8gbGl2ZSBjb3VudCBzbyB0aGUgQ0VPIGNhbiBqdW1wIHN0cmFpZ2h0IHRvIHVucmVhZCBjYXJkcwogIGlmKHVuYil7IHVuYi5jbGFzc0xpc3QudG9nZ2xlKCdvbicsIHZpZXcudW5yZWFkT25seSk7CiAgICBsZXQgbj0wOyBjb25zdCBvcmQ9KGJvYXJkJiZib2FyZC5vcmRlcil8fFtdOwogICAgb3JkLmZvckVhY2goaWQ9PnsgY29uc3QgdD1ib2FyZC50YXNrc1tpZF07IGlmKHQmJnVucmVhZENvdW50KHQpPjApIG4rKzsgfSk7CiAgICBjb25zdCBsYmwgPSBuID8gYHVucmVhZCBvbmx5IMK3ICR7bn1gIDogJ3VucmVhZCBvbmx5JzsKICAgIGlmKHVuYi50ZXh0Q29udGVudCE9PWxibCkgdW5iLnRleHRDb250ZW50PWxibDsKICB9Cn0KCi8vIOKUgOKUgCBESVJUWSBGSUVMRFMgQVJFIFNBQ1JFRCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKLy8gQSBmaWVsZCBpcyBzYWNyZWQgaWYgaXQncyBmb2N1c2VkIE9SIGhhcyB1bnNhdmVkIGxvY2FsIGVkaXRzIChkYXRhLWRpcnR5PTEpLgovLyBUaGUgcG9sbCBuZXZlciBvdmVyd3JpdGVzIGEgc2FjcmVkIGZpZWxkOyBsb2NhbCB0eXBpbmcgd2lucyB1bnRpbCBjb21taXR0ZWQuCmZ1bmN0aW9uIGlzRGlydHkoZWwpeyByZXR1cm4gISFlbCAmJiAoZWw9PT1kb2N1bWVudC5hY3RpdmVFbGVtZW50IHx8IGVsLmRhdGFzZXQuZGlydHk9PT0nMScpOyB9CmZ1bmN0aW9uIHdhdGNoRGlydHkoZWwpeyBlbC5hZGRFdmVudExpc3RlbmVyKCdpbnB1dCcsKCk9PntlbC5kYXRhc2V0LmRpcnR5PScxJzt9KTsgfQpmdW5jdGlvbiBjbGVhckRpcnR5KGVsKXsgZWwuZGF0YXNldC5kaXJ0eT0nJzsgfQpmdW5jdGlvbiBzZXRDbGVhbihlbCx2YWwpeyBpZihpc0RpcnR5KGVsKSlyZXR1cm47IGlmKGVsLnZhbHVlIT09dmFsKSBlbC52YWx1ZT12YWw7IH0gICAgICAgICAgICAgIC8vIDxpbnB1dD4KZnVuY3Rpb24gc2V0Q2xlYW5UZXh0KGVsLHZhbCl7IGlmKGlzRGlydHkoZWwpKXJldHVybjsgaWYoZWwudGV4dENvbnRlbnQhPT12YWwpIGVsLnRleHRDb250ZW50PXZhbDsgfSAvLyBjb250ZW50ZWRpdGFibGUKZnVuY3Rpb24gc2hvdyhlbCxvbil7IGVsLnN0eWxlLmRpc3BsYXkgPSBvbj8nJzonbm9uZSc7IH0KZnVuY3Rpb24gc2F2ZVJlYWRTdGF0ZSgpeyB0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oUkVBRF9LRVksSlNPTi5zdHJpbmdpZnkocmVhZFN0YXRlKSk7fWNhdGNoKGUpe30gfQpmdW5jdGlvbiBpc0Nlb0FjdG9yKGJ5KXsgcmV0dXJuIChieXx8JycpLnRyaW0oKS50b0xvd2VyQ2FzZSgpPT09J2Nlbyc7IH0KLy8g4pSA4pSAIHJlbGF0aW9ucyAoaXNzdWUgIzMpOiBwYXJlbnQvY2hpbGQgKyAnYmxvY2tlZCBieScgZGVwZW5kZW5jaWVzIOKUgOKUgApjb25zdCBpc1Rlcm1pbmFsPXM9PnM9PT0nZG9uZSd8fHM9PT0nY2FuY2VsbGVkJzsKZnVuY3Rpb24gY2hpbGRyZW5PZihpZCl7IHJldHVybiBib2FyZC5vcmRlci5tYXAoeD0+Ym9hcmQudGFza3NbeF0pLmZpbHRlcih0PT50JiZ0LnBhcmVudD09PWlkKTsgfQpmdW5jdGlvbiB1bm1ldERlcHModCl7IHJldHVybiAodC5kZXBlbmRzT258fFtdKS5maWx0ZXIoaWQ9Pntjb25zdCB4PWJvYXJkLnRhc2tzW2lkXTsgcmV0dXJuIHggJiYgIWlzVGVybWluYWwoeC5zdGF0ZSk7fSk7IH0KZnVuY3Rpb24gdGFza1RpdGxlKHQpeyByZXR1cm4gKHQmJih0LnRleHR8fCcnKS50cmltKCkpfHwnKHVudGl0bGVkKSc7IH0KZnVuY3Rpb24gc2hvcnRUaXRsZSh0KXsgY29uc3Qgcz10YXNrVGl0bGUodCk7IHJldHVybiBzLmxlbmd0aD42MD9zLnNsaWNlKDAsNTcpKyfigKYnOnM7IH0KZnVuY3Rpb24gdGFza1VwZGF0ZUV2ZW50cyh0KXsKICBjb25zdCBpdGVtcz1bXTsKICAodC5jb21tZW50c3x8W10pLmZvckVhY2goYz0+eyBpZighaXNDZW9BY3RvcihjLmJ5KSkgaXRlbXMucHVzaCh7dHM6Yy50c3x8MH0pOyB9KTsKICAodC5wcm9vZnN8fFtdKS5mb3JFYWNoKHA9PnsgaWYoIWlzQ2VvQWN0b3IocC5ieSkpIGl0ZW1zLnB1c2goe3RzOnAudHN8fDB9KTsgfSk7CiAgcmV0dXJuIGl0ZW1zOwp9CmZ1bmN0aW9uIGxhdGVzdFVwZGF0ZVRzKHQpeyByZXR1cm4gTWF0aC5tYXgoMCwuLi50YXNrVXBkYXRlRXZlbnRzKHQpLm1hcChlPT5lLnRzfHwwKSk7IH0KZnVuY3Rpb24gdW5yZWFkQ291bnQodCl7CiAgY29uc3QgbGFzdD1OdW1iZXIocmVhZFN0YXRlW3QuaWRdfHwwKTsKICByZXR1cm4gdGFza1VwZGF0ZUV2ZW50cyh0KS5maWx0ZXIoZT0+KGUudHN8fDApPmxhc3QpLmxlbmd0aDsKfQpmdW5jdGlvbiBtYXJrVGFza1JlYWQoaWQpewogIGNvbnN0IHQ9Ym9hcmQudGFza3NbaWRdOyBpZighdClyZXR1cm47CiAgY29uc3QgbGF0ZXN0PWxhdGVzdFVwZGF0ZVRzKHQpOwogIGlmKGxhdGVzdD4oTnVtYmVyKHJlYWRTdGF0ZVtpZF18fDApKSl7CiAgICByZWFkU3RhdGVbaWRdPWxhdGVzdDsgc2F2ZVJlYWRTdGF0ZSgpOwogICAgaWYoZWxzW2lkXSkgc3luY1Rhc2soZWxzW2lkXSx0KTsKICB9Cn0KZnVuY3Rpb24gc2VlZFJlYWRCYXNlbGluZXMoaWRzKXsKICBpZihyZWFkU2VlZGVkKSByZXR1cm47CiAgaWRzLmZvckVhY2goaWQ9PnsgY29uc3QgdD1ib2FyZC50YXNrc1tpZF07IGlmKHQgJiYgcmVhZFN0YXRlW2lkXT09PXVuZGVmaW5lZCkgcmVhZFN0YXRlW2lkXT1sYXRlc3RVcGRhdGVUcyh0KTsgfSk7CiAgcmVhZFNlZWRlZD10cnVlOyBzYXZlUmVhZFN0YXRlKCk7CiAgdHJ5eyBsb2NhbFN0b3JhZ2Uuc2V0SXRlbShSRUFEX1NFRURFRF9LRVksJzEnKTsgfWNhdGNoKGUpe30KfQoKLy8g4pSA4pSAIGxpdmUgcG9sbDogZmV0Y2ggYm9hcmQsIHJlY29uY2lsZSBvbmx5IHRoZSBkZWx0YS4gTk8gcGFnZSByZWxvYWQuIOKUgOKUgOKUgOKUgOKUgOKUgAphc3luYyBmdW5jdGlvbiBwdWxsKCl7CiAgdHJ5ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaCgnL3RvZG8vYm9hcmQnLHtoZWFkZXJzOkgoKX0pOwogICAgaWYoIXIub2speyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29ubicpLnRleHRDb250ZW50PShyLnN0YXR1cz09PTQwMz8nYXV0aCc6J29mZmxpbmUnKTsgcmV0dXJuOyB9CiAgICBjb25zdCBuYj1hd2FpdCByLmpzb24oKTsKICAgIGlmKG5iLmJ1aWxkICYmIEJVSUxEIT09J19fQlVJTERfXycgJiYgbmIuYnVpbGQhPT1CVUlMRCl7IGxvY2F0aW9uLnJlbG9hZCgpOyByZXR1cm47IH0gICAvLyBhIG5ld2VyIGJvYXJkIHNoaXBwZWQgLT4gcmVsb2FkIHRvIHRoZSBsYXRlc3QgSlMKICAgIGJvYXJkPW5iOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29ubicpLnRleHRDb250ZW50PSdsaXZlJzsgcmVjb25jaWxlKCk7CiAgICBpZighX2hhc2hDaGVja2VkKXsgX2hhc2hDaGVja2VkPXRydWU7IGNoZWNrSGFzaCgpOyB9ICAgLy8gZGVlcCBsaW5rIHByZXNlbnQgYXQgbG9hZCAtPiBvcGVuIHRoYXQgY2FyZCAoaGFzaGNoYW5nZSBkb2Vzbid0IGZpcmUgb24gaW5pdGlhbCBsb2FkKQogIH1jYXRjaChlKXsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Nvbm4nKS50ZXh0Q29udGVudD0nb2ZmbGluZSc7IH0KfQoKZnVuY3Rpb24gcmVjb25jaWxlKCl7CiAgY29uc3QgaWRzPWJvYXJkLm9yZGVyLmZpbHRlcihpZD0+Ym9hcmQudGFza3NbaWRdKTsgICAgICAgIC8vIGV2ZXJ5IHJlYWwgY2FyZCwgaW4gbWFudWFsIG9yZGVyCiAgc2VlZFJlYWRCYXNlbGluZXMoaWRzKTsKICBsZXQgZG9uZT0wOyBpZHMuZm9yRWFjaChpZD0+e2lmKGJvYXJkLnRhc2tzW2lkXS5zdGF0ZT09PSdkb25lJylkb25lKys7fSk7CiAgY29uc3Qgdmlld0lkcz1hcHBseVZpZXcoaWRzKTsgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vIGZpbHRlcmVkICsgc29ydGVkIHZpZXcgKGNsaWVudC1vbmx5KQogIGNvbnN0IGhpZGRlbj1pZHMubGVuZ3RoLXZpZXdJZHMubGVuZ3RoOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb3VudHMnKS5pbm5lckhUTUw9CiAgICBgPHNwYW4+JHtkb25lfSBkb25lPC9zcGFuPjxzcGFuPiR7aWRzLmxlbmd0aC1kb25lfSBvcGVuPC9zcGFuPjxzcGFuPiR7aWRzLmxlbmd0aH0gdG90YWw8L3NwYW4+YCsKICAgIChoaWRkZW4/YDxzcGFuIGNsYXNzPSJjbnQtaGlkZGVuIj4ke2hpZGRlbn0gaGlkZGVuPC9zcGFuPmA6JycpOyAgIC8vIHN1YnRsZSBjb3VudCBjaGlwOyB0aGUgJ2FsbCcgcHJlc2V0IGNsZWFycyBmaWx0ZXJzCiAgcmVuZGVyVmlld2JhcigpOwogIGlmKCFpZHMubGVuZ3RoKXsgaWYoIWxpc3RFbC5xdWVyeVNlbGVjdG9yKCcuZW1wdHknKSkgbGlzdEVsLmlubmVySFRNTD0nPGxpIGNsYXNzPSJlbXB0eSI+TmFkYSBhaW5kYS4gQWRpY2lvbmEgYSBwcmltZWlyYSBwcmlvcmlkYWRlIGFjaW1hLjwvbGk+JzsgZm9yKGNvbnN0IGsgaW4gZWxzKSBkZWxldGUgZWxzW2tdOyByZXR1cm47IH0KICBjb25zdCBiYXNlRW1wdHk9bGlzdEVsLnF1ZXJ5U2VsZWN0b3IoJy5lbXB0eTpub3QoLmZpbHRlcmVkKScpOyBpZihiYXNlRW1wdHkpIGJhc2VFbXB0eS5yZW1vdmUoKTsKICBjb25zdCBzeT13aW5kb3cuc2Nyb2xsWSwgYWN0aXZlPWRvY3VtZW50LmFjdGl2ZUVsZW1lbnQ7CiAgLy8gY3JlYXRlICsgdXBkYXRlIGluIHBsYWNlIChldmVyeSBjYXJkIGlzIGtlcHQgc3luY2VkLCBldmVuIGlmIGZpbHRlcmVkIG91dCkKICBpZHMuZm9yRWFjaChpZD0+eyB0cnl7IGxldCBsaT1lbHNbaWRdOyBpZighbGkpeyBsaT1jcmVhdGVUYXNrKGlkKTsgZWxzW2lkXT1saTsgbGlzdEVsLmFwcGVuZENoaWxkKGxpKTsgbGkuY2xhc3NMaXN0LmFkZCgnZnJlc2gnKTsgfSBzeW5jVGFzayhsaSwgYm9hcmQudGFza3NbaWRdKTsgfQogICAgY2F0Y2goZSl7IGNvbnNvbGUuZXJyb3IoJ3JlbmRlciBlcnJvciBvbiBjYXJkJyxpZCxlKTsgfSB9KTsgICAvLyBvbmUgYmFkIGNhcmQgbXVzdCBORVZFUiBibGFuayB0aGUgd2hvbGUgYm9hcmQKICAvLyByZW1vdmUgZ29uZQogIGZvcihjb25zdCBpZCBpbiBlbHMpeyBpZighYm9hcmQudGFza3NbaWRdKXsgZWxzW2lkXS5yZW1vdmUoKTsgZGVsZXRlIGVsc1tpZF07IH0gfQogIC8vIGZpbHRlcjogc2hvdyBvbmx5IGNhcmRzIGluIHRoZSB2aWV3OyBoaWRkZW4gY2FyZHMgc3RheSBpbiB0aGUgRE9NIGJ1dCBkaXNwbGF5Om5vbmUKICBjb25zdCB2aXNpYmxlPW5ldyBTZXQodmlld0lkcyk7CiAgaWRzLmZvckVhY2goaWQ9PnsgZWxzW2lkXS5zdHlsZS5kaXNwbGF5ID0gdmlzaWJsZS5oYXMoaWQpPycnOidub25lJzsgfSk7CiAgLy8gIm5vdGhpbmcgbWF0Y2hlcyIgbWVzc2FnZSB3aGVuIHRoZSBmaWx0ZXIgaGlkZXMgZXZlcnl0aGluZwogIGxldCBmZT1saXN0RWwucXVlcnlTZWxlY3RvcignLmVtcHR5LmZpbHRlcmVkJyk7CiAgaWYoIXZpZXdJZHMubGVuZ3RoKXsgaWYoIWZlKXsgZmU9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnbGknKTsgZmUuY2xhc3NOYW1lPSdlbXB0eSBmaWx0ZXJlZCc7IGZlLnRleHRDb250ZW50PSdObyBjYXJkcyBtYXRjaCB0aGlzIGZpbHRlci4nOyBsaXN0RWwuYXBwZW5kQ2hpbGQoZmUpOyB9IH0KICBlbHNlIGlmKGZlKXsgZmUucmVtb3ZlKCk7IGZlPW51bGw7IH0KICAvLyByZW9yZGVyIERPTSBvbmx5IGlmIGl0IGFjdHVhbGx5IGNoYW5nZWQ6IHZpc2libGUgKHNvcnRlZCkgZmlyc3QsIHRoZW4gaGlkZGVuIGNhcmRzCiAgY29uc3QgdGFyZ2V0PVsuLi52aWV3SWRzLCAuLi5pZHMuZmlsdGVyKGlkPT4hdmlzaWJsZS5oYXMoaWQpKV07CiAgY29uc3QgY3VyPVsuLi5saXN0RWwuY2hpbGRyZW5dLm1hcChuPT5uLmRhdGFzZXQuaWQpLmZpbHRlcihCb29sZWFuKTsKICBpZihjdXIuam9pbignLCcpIT09dGFyZ2V0LmpvaW4oJywnKSkgdGFyZ2V0LmZvckVhY2goaWQ9Pmxpc3RFbC5hcHBlbmRDaGlsZChlbHNbaWRdKSk7CiAgaWYoZmUpIGxpc3RFbC5hcHBlbmRDaGlsZChmZSk7ICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vIGtlZXAgdGhlIGZpbHRlci1lbXB0eSBub3RpY2UgbGFzdAogIC8vIHByZXNlcnZlIGZvY3VzICsgc2Nyb2xsIGFjcm9zcyB0aGUgdGljawogIGlmKGFjdGl2ZSAmJiBkb2N1bWVudC5jb250YWlucyhhY3RpdmUpICYmIGRvY3VtZW50LmFjdGl2ZUVsZW1lbnQhPT1hY3RpdmUpeyB0cnl7YWN0aXZlLmZvY3VzKHtwcmV2ZW50U2Nyb2xsOnRydWV9KTt9Y2F0Y2goZSl7fSB9CiAgaWYod2luZG93LnNjcm9sbFkhPT1zeSkgd2luZG93LnNjcm9sbFRvKDAsc3kpOwogIGlmKGNhcmRPcGVuSWQpIHJlbmRlckNhcmQoKTsgICAgLy8gc3RyZWFtIG5ldyBhY3Rpdml0eSBpbnRvIHRoZSBvcGVuIGNhcmQgKGNvbXBvc2VyIHVudG91Y2hlZCkKfQoKZnVuY3Rpb24gY3JlYXRlVGFzayhpZCl7CiAgY29uc3QgbGk9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnbGknKTsgbGkuY2xhc3NOYW1lPSd0YXNrJzsgbGkuZGF0YXNldC5pZD1pZDsKICBsaS5pbm5lckhUTUw9YAogICAgPGRpdiBjbGFzcz0idGFzay10b3AiPgogICAgICA8ZGl2IGNsYXNzPSJjaGVjayIgdGl0bGU9IiI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InRhc2stbWFpbiI+CiAgICAgICAgPGRpdiBjbGFzcz0idGFzay10ZXh0IiBjb250ZW50ZWRpdGFibGU9InRydWUiIHNwZWxsY2hlY2s9ImZhbHNlIj48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJtZXRhIj48c3BhbiBjbGFzcz0iYmFkZ2UiPjwvc3Bhbj48c3BhbiBjbGFzcz0idW5yZWFkLWJhZGdlIiBzdHlsZT0iZGlzcGxheTpub25lIj48L3NwYW4+PHNwYW4gY2xhc3M9InRhZyBhc2ctdGFnIj48L3NwYW4+PHNwYW4gY2xhc3M9ImJhZGdlIHN0LWRvbmUgdmVyIiBzdHlsZT0iZGlzcGxheTpub25lIj52ZXJpZmllZDwvc3Bhbj48c3BhbiBjbGFzcz0icmVscyI+PC9zcGFuPjxzcGFuIGNsYXNzPSJwaW5nIj48L3NwYW4+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjdHJscyI+PGJ1dHRvbiBjbGFzcz0iaWN0cmwgb3BlbiIgdGl0bGU9Im9wZW4gY2FyZCDigJQgZnVsbCBoaXN0b3J5Ij7ipKI8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJpY3RybCB1cCI+4oaRPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iaWN0cmwgZG93biI+4oaTPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iaWN0cmwgZGVsIj7DlzwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJyb3ciPjxzcGFuIGNsYXNzPSJsYWJlbCByZXEiPmRvbmUtY29uZGl0aW9uPC9zcGFuPjxpbnB1dCBjbGFzcz0iZmllbGQgY29uZCIgcGxhY2Vob2xkZXI9ImhvdyBkbyB3ZSB2ZXJpZnkgdGhpcyBpcyBET05FPyI+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJyb3ciPjxsYWJlbCBjbGFzcz0idG9nZ2xlIj48c3BhbiBjbGFzcz0ic3ciPjwvc3Bhbj53b3JrIHRvIGRvbmU8L2xhYmVsPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ibmVlZGJyYWluIiBzdHlsZT0iZGlzcGxheTpub25lIj7imqAgTmVlZHMgYnJhaW5zdG9ybSDigJQgbm90IHdvcmthYmxlIHVudGlsIHByb21vdGVkLiBBbnN3ZXIgdGhlIG9wZW4gcXVlc3Rpb24ocyksIHRoZW4gaXQgbW92ZXMgdG8gd29ya2luZy48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImJyYWluc3Rvcm0iIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjxzcGFuIGNsYXNzPSJoIj5icmFpbnN0b3JtPC9zcGFuPjxzcGFuIGNsYXNzPSJicy1ib2R5Ij48L3NwYW4+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdGF0dXMiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjwvZGl2PgogICAgPGRpdiBjbGFzcz0icHJvb2ZzIj48c3BhbiBjbGFzcz0icHJvb2YtbGlzdCI+PC9zcGFuPjwvZGl2PmA7CiAgY29uc3Qgcj17IGNoZWNrOmxpLnF1ZXJ5U2VsZWN0b3IoJy5jaGVjaycpLCB0ZXh0OmxpLnF1ZXJ5U2VsZWN0b3IoJy50YXNrLXRleHQnKSwgYmFkZ2U6bGkucXVlcnlTZWxlY3RvcignLmJhZGdlJyksCiAgICB1bnJlYWQ6bGkucXVlcnlTZWxlY3RvcignLnVucmVhZC1iYWRnZScpLCBhc2dUYWc6bGkucXVlcnlTZWxlY3RvcignLmFzZy10YWcnKSwgdmVyOmxpLnF1ZXJ5U2VsZWN0b3IoJy52ZXInKSwgcGluZzpsaS5xdWVyeVNlbGVjdG9yKCcucGluZycpLCByZWxzOmxpLnF1ZXJ5U2VsZWN0b3IoJy5yZWxzJyksCiAgICBjb25kOmxpLnF1ZXJ5U2VsZWN0b3IoJy5jb25kJyksIHRvZ2dsZTpsaS5xdWVyeVNlbGVjdG9yKCcudG9nZ2xlJyksCiAgICBicmFpbjpsaS5xdWVyeVNlbGVjdG9yKCcuYnJhaW5zdG9ybScpLCBic0JvZHk6bGkucXVlcnlTZWxlY3RvcignLmJzLWJvZHknKSwgc3RhdHVzOmxpLnF1ZXJ5U2VsZWN0b3IoJy5zdGF0dXMnKSwgbmVlZGJyYWluOmxpLnF1ZXJ5U2VsZWN0b3IoJy5uZWVkYnJhaW4nKSwKICAgIHByb29mTGlzdDpsaS5xdWVyeVNlbGVjdG9yKCcucHJvb2YtbGlzdCcpLCB1cDpsaS5xdWVyeVNlbGVjdG9yKCcudXAnKSwgZG93bjpsaS5xdWVyeVNlbGVjdG9yKCcuZG93bicpLCBkZWw6bGkucXVlcnlTZWxlY3RvcignLmRlbCcpLAogICAgb3BlbjpsaS5xdWVyeVNlbGVjdG9yKCcub3BlbicpLCBwc2lnOm51bGwgfTsKICBsaS5fcj1yOwogIGNvbnN0IFQ9KCk9PmJvYXJkLnRhc2tzW2lkXTsKICAvLyB0ZXh0IChjb250ZW50ZWRpdGFibGUpCiAgd2F0Y2hEaXJ0eShyLnRleHQpOwogIHIudGV4dC5vbmJsdXI9KCk9PnsgY29uc3Qgdj1yLnRleHQudGV4dENvbnRlbnQudHJpbSgpOyBjbGVhckRpcnR5KHIudGV4dCk7IGNvbnN0IHQ9VCgpOyBpZih0JiZ2JiZ2IT09dC50ZXh0KSB1cGQoe29wOidzZXQnLGlkLHRleHQ6dn0pLnRoZW4ocHVsbCk7IH07CiAgci50ZXh0Lm9ua2V5ZG93bj1lPT57IGlmKGUua2V5PT09J0VudGVyJyl7ZS5wcmV2ZW50RGVmYXVsdCgpOyByLnRleHQuYmx1cigpO30gfTsKICAvLyBjaGVjayB0b2dnbGUgZG9uZS91bmRvbmUKICByLmNoZWNrLm9uY2xpY2s9ZT0+eyBlLnN0b3BQcm9wYWdhdGlvbigpOyAgICAgICAgICAgICAgLy8gQ0VPIG1hcmstZG9uZSDigJQgbXVzdCBOT1QgYnViYmxlIHRvIHRoZSBjYXJkLW9wZW4gaGFuZGxlcgogICAgY29uc3QgdD1UKCk7IGlmKCF0KXJldHVybjsKICAgIC8vIFJ1bGUgMjE6IHRoZSBDRU8gbWFya3MgZG9uZSBpbiBPTkUgY2xpY2sgZnJvbSBBTlkgc3RhdGUgKHRoZSB2ZXJpZnkvcmV2aWV3IGdhdGUgaXMgb25seSBmb3IgdGhlIEFJKS4KICAgIGlmKHQuc3RhdGU9PT0nZG9uZScpIHN0YXR1c0FwaSh7aWQsc3RhdGU6J3dvcmtpbmcnLHZlcmlmaWVkOmZhbHNlLGJ5OidDRU8nfSkudGhlbihwdWxsKTsgICAvLyB1bi1kb25lCiAgICBlbHNlIHN0YXR1c0FwaSh7aWQsc3RhdGU6J2RvbmUnLHZlcmlmaWVkOnRydWUsYnk6J0NFTyd9KS50aGVuKHB1bGwpOyB9OyAgICAgICAgICAgICAgICAgICAgIC8vIC0+IGRvbmUsIG9uZSBjbGljaywgYW55IHN0YXRlCiAgLy8gZG9uZS1jb25kaXRpb24KICB3YXRjaERpcnR5KHIuY29uZCk7CiAgci5jb25kLm9uYmx1cj0oKT0+eyBjb25zdCB0PVQoKTsgY2xlYXJEaXJ0eShyLmNvbmQpOyBpZih0JiZyLmNvbmQudmFsdWUhPT10LmRvbmVDb25kaXRpb24pIHVwZCh7b3A6J3NldCcsaWQsZG9uZUNvbmRpdGlvbjpyLmNvbmQudmFsdWV9KS50aGVuKHB1bGwpOyB9OwogIHIuY29uZC5vbmtleWRvd249ZT0+eyBpZihlLmtleT09PSdFbnRlcicpIHIuY29uZC5ibHVyKCk7IH07CiAgLy8gd29yay10by1kb25lIHRvZ2dsZQogIC8vIHdvcmstdG8tZG9uZTogREVCT1VOQ0VEIDUwMG1zIOKAlCByYXBpZCBvbi9vZmYgc2V0dGxlcyB0byBPTkUgZmluYWwgUE9TVDsgaWYgaXQgbmV0cyBiYWNrIHRvIHRoZQogIC8vIGN1cnJlbnQgc2VydmVyIHN0YXRlLCBub3RoaW5nIGlzIHNlbnQgKG5vIGR1cGxpY2F0ZSBCb3NzIG5vdGlmaWNhdGlvbikuCiAgci50b2dnbGUub25jbGljaz0oKT0+eyBjb25zdCB0PVQoKTsgaWYoIXR8fCEodC5kb25lQ29uZGl0aW9ufHwnJykudHJpbSgpKXJldHVybjsKICAgIGlmKHIuX3BlbmRXdGQ9PT11bmRlZmluZWQpIHIuX3BlbmRXdGQ9ISF0LndvcmtUb0RvbmU7CiAgICByLl9wZW5kV3RkPSFyLl9wZW5kV3RkOwogICAgci50b2dnbGUuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCByLl9wZW5kV3RkKTsgICAgICAgICAgICAvLyBpbW1lZGlhdGUgdmlzdWFsIGZlZWRiYWNrCiAgICBjbGVhclRpbWVvdXQoci5fd3RkVGltZXIpOwogICAgci5fd3RkVGltZXI9c2V0VGltZW91dCgoKT0+eyBjb25zdCBjdXI9VCgpLCB3YW50PXIuX3BlbmRXdGQ7IHIuX3BlbmRXdGQ9dW5kZWZpbmVkOwogICAgICBpZihjdXIgJiYgd2FudCE9PSEhY3VyLndvcmtUb0RvbmUpIHVwZCh7b3A6J3NldCcsaWQsd29ya1RvRG9uZTp3YW50fSkudGhlbihwdWxsKTsgICAvLyBvbmx5IHRoZSBuZXQgY2hhbmdlIGZpcmVzCiAgICAgIGVsc2UgcHVsbCgpOyAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vIG5vIG5ldCBjaGFuZ2UgLT4gcmVzeW5jLCBzZW5kIG5vdGhpbmcKICAgIH0sIDUwMCk7CiAgfTsKICAvLyBjbGljayB0aGUgbGlua2VkLWVuZ2luZWVyIGNoaXAgLT4gYXR0YWNoIHRvIGl0cyB0ZXJtaW5hbCAoZG9uJ3QgYWxzbyBvcGVuIHRoZSBjYXJkKQogIHIuYXNnVGFnLm9uY2xpY2s9ZT0+eyBjb25zdCB0PVQoKTsgaWYodCYmaXNBdHRhY2hhYmxlKHQuYXNzaWduZWUpKXsgZS5zdG9wUHJvcGFnYXRpb24oKTsgYXR0YWNoVG9FbmdpbmVlcih0LmFzc2lnbmVlKTsgfSB9OwogIC8vIHJlb3JkZXIgLyBkZWxldGUKICByLnVwLm9uY2xpY2s9KCk9Pm1vdmUoaWQsLTEpOyByLmRvd24ub25jbGljaz0oKT0+bW92ZShpZCwxKTsKICByLmRlbC5vbmNsaWNrPSgpPT57IGlmKGNvbmZpcm0oJ0RlbGV0ZSB0aGlzIHByaW9yaXR5PycpKSB1cGQoe29wOidkZWwnLGlkfSkudGhlbihwdWxsKTsgfTsKICAvLyBvcGVuIHRoZSBpc3N1ZS1zdHlsZSBjYXJkIChleHBsaWNpdCDipKIsIG9yIGNsaWNrIHRoZSBjYXJkIGJvZHkgYXdheSBmcm9tIGFueSBjb250cm9sKQogIHIub3Blbi5vbmNsaWNrPWU9PnsgZS5zdG9wUHJvcGFnYXRpb24oKTsgb3BlbkNhcmQoaWQpOyB9OwogIGxpLmFkZEV2ZW50TGlzdGVuZXIoJ2NsaWNrJyxlPT57IGlmKGUudGFyZ2V0LmNsb3Nlc3QoJ2lucHV0LHRleHRhcmVhLGJ1dHRvbixhLGxhYmVsLHZpZGVvLFtjb250ZW50ZWRpdGFibGVdLC5jaGVjaywuY3RybHMsLnByb29mcywudG9nZ2xlJykpIHJldHVybjsgb3BlbkNhcmQoaWQpOyB9KTsKICByZXR1cm4gbGk7Cn0KCmZ1bmN0aW9uIHByb29mQ2hpcChwKXsKICBpZihwLnR5cGU9PT0naW1hZ2UnKSByZXR1cm4gYDxhIGNsYXNzPSJwcm9vZiBpbWciIGhyZWY9IiR7ZXNjKHAucmVmKX0iIHRhcmdldD0iX2JsYW5rIiB0aXRsZT0iJHtlc2MocC5jYXB0aW9ufHwnaW1hZ2UnKX0iPjxpbWcgc3JjPSIke2VzYyhwLnJlZil9IiBsb2FkaW5nPSJsYXp5IiBhbHQ9InByb29mIj48L2E+YDsKICBpZihwLnR5cGU9PT0ndmlkZW8nKSByZXR1cm4gYDxkaXYgY2xhc3M9InByb29mIHZpZCI+PHZpZGVvIGNsYXNzPSJwdmlkIiBjb250cm9scyBwcmVsb2FkPSJtZXRhZGF0YSIgcGxheXNpbmxpbmUgc3JjPSIke2VzYyhwLnJlZil9Ij48L3ZpZGVvPmAKICAgICAgKyBgPGEgY2xhc3M9InZjYXAiIGhyZWY9IiR7ZXNjKHAucmVmKX0iIHRhcmdldD0iX2JsYW5rIj7ilrYgJHtlc2MocC5jYXB0aW9ufHwnd2F0Y2ggcHJvb2YnKX0g4oaXPC9hPjwvZGl2PmA7CiAgaWYocC50eXBlPT09J2xpbmsnKSAgcmV0dXJuIGA8YSBjbGFzcz0icHJvb2YiIGhyZWY9IiR7ZXNjKHAucmVmKX0iIHRhcmdldD0iX2JsYW5rIj7wn5SXICR7ZXNjKHAucmVmKX08L2E+YDsKICByZXR1cm4gYDxzcGFuIGNsYXNzPSJwcm9vZiIgdGl0bGU9IiR7ZXNjKHAucmVmKX0iPvCfk50gJHtlc2MocC5yZWYpfTwvc3Bhbj5gOwp9CmZ1bmN0aW9uIGlzTWVkaWFQcm9vZihwKXsgcmV0dXJuIHAgJiYgKHAudHlwZT09PSdpbWFnZSd8fHAudHlwZT09PSd2aWRlbycpOyB9CmZ1bmN0aW9uIGhvbWVQcm9vZnNIdG1sKHByb29mcyl7CiAgY29uc3QgcHM9cHJvb2ZzfHxbXSwgbWVkaWE9cHMuZmlsdGVyKGlzTWVkaWFQcm9vZik7CiAgY29uc3Qgc2hvd25NZWRpYT1uZXcgU2V0KG1lZGlhLnNsaWNlKDAsSE9NRV9NRURJQV9QUkVWSUVXX0xJTUlUKS5tYXAocD0+cC5pZCkpOwogIGxldCBodG1sPXBzLmZpbHRlcihwPT4haXNNZWRpYVByb29mKHApfHxzaG93bk1lZGlhLmhhcyhwLmlkKSkubWFwKHByb29mQ2hpcCkuam9pbignJyk7CiAgY29uc3QgaGlkZGVuPW1lZGlhLmxlbmd0aC1IT01FX01FRElBX1BSRVZJRVdfTElNSVQ7CiAgaWYoaGlkZGVuPjApIGh0bWwrPWA8YnV0dG9uIHR5cGU9ImJ1dHRvbiIgY2xhc3M9InByb29mIG1vcmUiIHRpdGxlPSJvcGVuIGNhcmQgdG8gdmlldyBhbGwgJHttZWRpYS5sZW5ndGh9IG1lZGlhIGF0dGFjaG1lbnRzIj4rJHtoaWRkZW59IG1vcmU8L2J1dHRvbj5gOwogIHJldHVybiBodG1sOwp9CgpmdW5jdGlvbiBzeW5jVGFzayhsaSx0KXsKICBjb25zdCByPWxpLl9yOwogIGxpLmNsYXNzTGlzdC50b2dnbGUoJ2RvbmUnLCB0LnN0YXRlPT09J2RvbmUnKTsKICBsaS5jbGFzc0xpc3QudG9nZ2xlKCdjYW5jZWxsZWQnLCB0LnN0YXRlPT09J2NhbmNlbGxlZCcpOwogIC8vIHRoZSBDRU8gY2FuIG1hcmsgZG9uZSBmcm9tIEFOWSBzdGF0ZSAoUnVsZSAyMSwgb25lIGNsaWNrKSAtPiB0aGUgY2hlY2sgaXMgYWx3YXlzIGVuYWJsZWQKICByLmNoZWNrLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgdC5zdGF0ZT09PSdkb25lJyk7CiAgci5jaGVjay5jbGFzc0xpc3QucmVtb3ZlKCdkaXNhYmxlZCcpOwogIHIuY2hlY2sudGV4dENvbnRlbnQgPSB0LnN0YXRlPT09J2RvbmUnID8gJ+KckycgOiAnJzsKICByLmNoZWNrLnRpdGxlID0gdC5zdGF0ZT09PSdkb25lJyA/ICdtYXJrIG5vdC1kb25lJyA6ICdtYXJrIERPTkUgKENFTywgb25lIGNsaWNrKSc7CiAgLy8gdGV4dCArIG1ldGEgKG5ldmVyIGNsb2JiZXIgaWYgdGhlIENFTyBpcyBlZGl0aW5nKQogIHNldENsZWFuVGV4dChyLnRleHQsIHQudGV4dCk7CiAgci5iYWRnZS50ZXh0Q29udGVudD1TVExBQkVMW3Quc3RhdGVdfHx0LnN0YXRlOyByLmJhZGdlLmNsYXNzTmFtZT0nYmFkZ2Ugc3QtJyt0LnN0YXRlOwogIGNvbnN0IHVjPXVucmVhZENvdW50KHQpOwogIGlmKHVjKXsgc2hvdyhyLnVucmVhZCx0cnVlKTsgci51bnJlYWQudGV4dENvbnRlbnQ9dWMrJyBuZXcnOyByLnVucmVhZC50aXRsZT11YysnIHVucmVhZCB0aW1lbGluZSB1cGRhdGUnKyh1Yz4xPydzJzonJyk7IH0KICBlbHNlIHNob3coci51bnJlYWQsZmFsc2UpOwogIGNvbnN0IGNhbkF0dGFjaD1pc0F0dGFjaGFibGUodC5hc3NpZ25lZSk7CiAgci5hc2dUYWcudGV4dENvbnRlbnQgPSB0LmFzc2lnbmVlID8gJ0AnK3QuYXNzaWduZWUgOiAndW5hc3NpZ25lZCc7CiAgci5hc2dUYWcuY2xhc3NMaXN0LnRvZ2dsZSgnYXR0YWNoJywgY2FuQXR0YWNoKTsKICByLmFzZ1RhZy50aXRsZSA9IGNhbkF0dGFjaCA/ICdjbGljayB0byBhdHRhY2ggdG8gJyt0LmFzc2lnbmVlKyfigJlzIHRlcm1pbmFsJyA6ICcnOwogIHNob3coci52ZXIsICEhdC52ZXJpZmllZCk7CiAgLy8gcmVsYXRpb25zIGluZGljYXRvcnMgKGlzc3VlICMzKTogYmxvY2tlZC1ieSwgc3VidGFzayBwcm9ncmVzcywgY2hpbGQgbWFya2VyCiAgY29uc3Qga2lkcz1jaGlsZHJlbk9mKHQuaWQpLCB1bT11bm1ldERlcHModCk7CiAgbGV0IHJlbEh0bWw9Jyc7CiAgaWYodW0ubGVuZ3RoKSByZWxIdG1sKz1gPHNwYW4gY2xhc3M9InJlbCBibG9ja2VkIiB0aXRsZT0iYmxvY2tlZCBieSAke3VtLmxlbmd0aH0gdW5maW5pc2hlZCBwcmVyZXF1aXNpdGUocykiPuKblCBibG9ja2VkIGJ5ICR7dW0ubGVuZ3RofTwvc3Bhbj5gOwogIGlmKGtpZHMubGVuZ3RoKXsgY29uc3QgZG49a2lkcy5maWx0ZXIoaz0+aXNUZXJtaW5hbChrLnN0YXRlKSkubGVuZ3RoOyByZWxIdG1sKz1gPHNwYW4gY2xhc3M9InJlbCBzdWJzIiB0aXRsZT0iJHtkbn0gb2YgJHtraWRzLmxlbmd0aH0gc3VidGFza3MgZG9uZS9jYW5jZWxsZWQiPuKGsyAke2RufS8ke2tpZHMubGVuZ3RofSBzdWJ0YXNrczwvc3Bhbj5gOyB9CiAgaWYodC5wYXJlbnQmJmJvYXJkLnRhc2tzW3QucGFyZW50XSkgcmVsSHRtbCs9YDxzcGFuIGNsYXNzPSJyZWwgY2hpbGQiIHRpdGxlPSJzdWJ0YXNrIG9mOiAke2VzYyhzaG9ydFRpdGxlKGJvYXJkLnRhc2tzW3QucGFyZW50XSkpfSI+c3VidGFzazwvc3Bhbj5gOwogIGlmKHIucmVscy5pbm5lckhUTUwhPT1yZWxIdG1sKSByLnJlbHMuaW5uZXJIVE1MPXJlbEh0bWw7CiAgci5waW5nLnRleHRDb250ZW50PSfihpFib3NzICcrKHQucGluZ3NUb0Jvc3N8fDApOwogIC8vIGZpZWxkcwogIHNldENsZWFuKHIuY29uZCwgdC5kb25lQ29uZGl0aW9ufHwnJyk7CiAgaWYoci5fcGVuZFd0ZD09PXVuZGVmaW5lZCkgci50b2dnbGUuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCAhIXQud29ya1RvRG9uZSk7ICAgLy8gZG9uJ3QgY2xvYmJlciBhIHBlbmRpbmcgKGRlYm91bmNpbmcpIHRvZ2dsZQogIHIudG9nZ2xlLmNsYXNzTGlzdC50b2dnbGUoJ2Rpc2FibGVkJywgISh0LmRvbmVDb25kaXRpb258fCcnKS50cmltKCkpOyAgIC8vIHdvcmstdG8tZG9uZSBzdGlsbCBuZWVkcyBhIGRvbmUtY29uZGl0aW9uIChzZXJ2ZXItZW5mb3JjZWQpCiAgLy8gYnJhaW5zdG9ybQogIGlmKCh0LmJyYWluc3Rvcm18fCcnKS50cmltKCkpeyBzaG93KHIuYnJhaW4sdHJ1ZSk7IGlmKHIuYnNCb2R5LnRleHRDb250ZW50IT09dC5icmFpbnN0b3JtKSByLmJzQm9keS50ZXh0Q29udGVudD10LmJyYWluc3Rvcm07IH0gZWxzZSBzaG93KHIuYnJhaW4sZmFsc2UpOwogIC8vIG5lZWRzLWJyYWluc3Rvcm0gYmFubmVyIChzaWxlbnQtbm8tb3AgZml4KTogYSBuZWVkc19icmFpbnN0b3JtIGNhcmQgbXVzdCBTVVJGQUNFLCBuZXZlciBzaXQgc2lsZW50CiAgc2hvdyhyLm5lZWRicmFpbiwgdC5zdGF0ZT09PSduZWVkc19icmFpbnN0b3JtJyk7CiAgLy8gc3RhdHVzIGxpbmUKICBpZih0Lmxhc3RTdGF0dXMgJiYgdC5zdGF0ZSE9PSdkb25lJyAmJiB0LnN0YXRlIT09J2NhbmNlbGxlZCcpeyBzaG93KHIuc3RhdHVzLHRydWUpOyBjb25zdCBzPSfimqAgJyt0Lmxhc3RTdGF0dXM7IGlmKHIuc3RhdHVzLnRleHRDb250ZW50IT09cykgci5zdGF0dXMudGV4dENvbnRlbnQ9czsgfSBlbHNlIHNob3coci5zdGF0dXMsZmFsc2UpOwogIC8vIGhvbWVwYWdlIHByb29mIHByZXZpZXdzOiBjYXAgYnVsa3kgaW1hZ2UvdmlkZW8gbWVkaWE7IHRoZSBpc3N1ZS1zdHlsZSBjYXJkIHN0aWxsIHNob3dzIGV2ZXJ5IHByb29mLgogIGNvbnN0IHNpZz0odC5wcm9vZnN8fFtdKS5tYXAocD0+W3AuaWQscC50eXBlLHAucmVmLHAuY2FwdGlvbl0uam9pbignOicpKS5qb2luKCcsJyk7CiAgaWYoc2lnIT09ci5wc2lnKXsKICAgIHIucHJvb2ZMaXN0LmlubmVySFRNTD1ob21lUHJvb2ZzSHRtbCh0LnByb29mcyk7CiAgICBjb25zdCBtb3JlPXIucHJvb2ZMaXN0LnF1ZXJ5U2VsZWN0b3IoJy5wcm9vZi5tb3JlJyk7CiAgICBpZihtb3JlKSBtb3JlLm9uY2xpY2s9ZT0+eyBlLnByZXZlbnREZWZhdWx0KCk7IGUuc3RvcFByb3BhZ2F0aW9uKCk7IG9wZW5DYXJkKHQuaWQpOyB9OwogICAgci5wc2lnPXNpZzsKICB9Cn0KCmZ1bmN0aW9uIG1vdmUoaWQsZCl7IGNvbnN0IG89Ym9hcmQub3JkZXIuZmlsdGVyKHg9PmJvYXJkLnRhc2tzW3hdKTsgY29uc3QgaT1vLmluZGV4T2YoaWQpLGo9aStkOyBpZihqPDB8fGo+PW8ubGVuZ3RoKXJldHVybjsgW29baV0sb1tqXV09W29bal0sb1tpXV07IHVwZCh7b3A6J3Jlb3JkZXInLG9yZGVyOm99KS50aGVuKHB1bGwpOyB9CgpmdW5jdGlvbiBhZGQoKXsgY29uc3QgdD1pbnB1dC52YWx1ZS50cmltKCk7IGlmKCF0KXJldHVybjsgaW5wdXQudmFsdWU9Jyc7IHVwZCh7b3A6J2FkZCcsdGV4dDp0fSkudGhlbihwdWxsKTsgfQpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWRkQnRuJykub25jbGljaz1hZGQ7CmlucHV0LmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLGU9PnsgaWYoZS5rZXk9PT0nRW50ZXInKSBhZGQoKTsgfSk7CgovLyDilIDilIAgSVNTVUUtU1RZTEUgQ0FSRCBWSUVXIChzbGljZSBiKSDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKLy8gQ2xpY2tpbmcgYSB0YXNrIG9wZW5zIGEgbW9kYWwgd2l0aCB0aGUgZnVsbCwgZHVyYWJsZSBtZXNzYWdlIGhpc3RvcnkgZm9yIHRoYXQgdGFzayDigJQKLy8gR2l0SHViLWlzc3VlIHN0eWxlOiB0aGUgb3BlbmluZyBldmVudCwgdGhlbiBBSS9lbmdpbmVlciArIENFTyBjb21tZW50cywgc3RhdHVzIHVwZGF0ZXMsCi8vIHN0YXRlIHRyYW5zaXRpb25zLCB0aGUgYnJhaW5zdG9ybSBhcnRpZmFjdCwgYW5kIGltYWdlL3ZpZGVvIHByb29mcywgbWVyZ2VkIGJ5IHRpbWVzdGFtcC4KLy8gUmUtcmVuZGVycyBsaXZlIG9uIGV2ZXJ5IHBvbGwgd2hpbGUgb3Blbiwgc28gbmV3IGFjdGl2aXR5IHN0cmVhbXMgaW4gKGNvbXBvc2VyIGlzIG5ldmVyCi8vIGNsb2JiZXJlZCDigJQgaXQgbGl2ZXMgb3V0c2lkZSB0aGUgcmUtcmVuZGVyZWQgcmVnaW9uOyBkaXJ0eSB0ZXh0ICsgZm9jdXMgc3Vydml2ZSB0aGUgdGljaykuCmxldCBjYXJkT3BlbklkPW51bGwsIF9oYXNoQ2hlY2tlZD1mYWxzZTsKY29uc3QgbW9kYWw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRNb2RhbCcpOwpjb25zdCBjYXJkVGl0bGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRUaXRsZScpLCBjYXJkU3ViPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkU3ViJyk7CmNvbnN0IGNhcmRDb25kPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQ29uZCcpLCBjYXJkQ29uZEJvZHk9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRDb25kQm9keScpOwpjb25zdCBjYXJkQXJ0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQXJ0JyksIGNhcmRBcnRCb2R5PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQXJ0Qm9keScpOwpjb25zdCBjYXJkVGhyZWFkPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkVGhyZWFkJyksIGNhcmRDb21wb3NlPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQ29tcG9zZScpOwpjb25zdCBjYXJkUWE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRRYScpLCBjYXJkU3RhdGU9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NhcmRTdGF0ZScpLCBjYXJkUmVsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkUmVsJyk7Ci8vIHJlbGF0aW9ucyBwYW5lbCBpbnNpZGUgdGhlIG9wZW5lZCBjYXJkIChpc3N1ZSAjMyk6IHN1YnRhc2tzICsgJ2Jsb2NrZWQgYnknIGRlcHMgKyBoYXJkLWdhdGUgdG9nZ2xlLgovLyBTaWduYXR1cmUtZ2F0ZWQgc28gbGl2ZSBwb2xscyBkb24ndCBjbG9iYmVyIGEgaGFsZi10eXBlZCBzdWJ0aXRsZSBvciByZXNldCB0aGUgZGVwZW5kZW5jeSBwaWNrZXIuCmZ1bmN0aW9uIHJlbmRlclJlbGF0aW9ucyh0KXsKICBjb25zdCBraWRzPWNoaWxkcmVuT2YodC5pZCksIGRlcHM9KHQuZGVwZW5kc09ufHxbXSkubWFwKGlkPT5ib2FyZC50YXNrc1tpZF0pLmZpbHRlcihCb29sZWFuKTsKICBjb25zdCBzaWc9SlNPTi5zdHJpbmdpZnkoW3QuaGFyZEdhdGUsa2lkcy5tYXAoaz0+W2suaWQsay5zdGF0ZSxrLnRleHRdKSxkZXBzLm1hcChkPT5bZC5pZCxkLnN0YXRlLGQudGV4dF0pLGJvYXJkLm9yZGVyLmxlbmd0aF0pOwogIGlmKGNhcmRSZWwuX3NpZz09PXNpZyl7IHNob3coY2FyZFJlbCx0cnVlKTsgcmV0dXJuOyB9IGNhcmRSZWwuX3NpZz1zaWc7CiAgY29uc3QgYmFkZ2U9cz0+YDxzcGFuIGNsYXNzPSJiYWRnZSBzdC0ke3N9IiBzdHlsZT0iZm9udC1zaXplOjlweDtwYWRkaW5nOjJweCA3cHgiPiR7ZXNjKFNUTEFCRUxbc118fHMpfTwvc3Bhbj5gOwogIGNvbnN0IGRvbmVOPWtpZHMuZmlsdGVyKGs9PmlzVGVybWluYWwoay5zdGF0ZSkpLmxlbmd0aDsKICBsZXQgaHRtbD1gPGRpdiBjbGFzcz0icmVsLXNlYyI+PHNwYW4gY2xhc3M9ImgiPnN1YnRhc2tzJHtraWRzLmxlbmd0aD9gIMK3ICR7ZG9uZU59LyR7a2lkcy5sZW5ndGh9IGRvbmVgOicnfTwvc3Bhbj5gOwogIGh0bWwrPSBraWRzLmxlbmd0aCA/IGtpZHMubWFwKGs9PmA8ZGl2IGNsYXNzPSJyZWwtcm93Ij48YSBjbGFzcz0icmVsLWxpbmsiIGRhdGEtb3Blbj0iJHtrLmlkfSI+4oazICR7ZXNjKHNob3J0VGl0bGUoaykpfTwvYT4ke2JhZGdlKGsuc3RhdGUpfTwvZGl2PmApLmpvaW4oJycpCiAgICAgICAgICAgICAgICAgICAgIDogYDxkaXYgY2xhc3M9InJlbC1lbXB0eSI+Tm8gc3VidGFza3MgeWV0LjwvZGl2PmA7CiAgaHRtbCs9YDxkaXYgY2xhc3M9InJlbC1hZGQiPjxpbnB1dCBpZD0icmVsU3ViVGV4dCIgcGxhY2Vob2xkZXI9Im5ldyBzdWJ0YXNrIHRpdGxl4oCmIiBtYXhsZW5ndGg9IjI0MCI+PGJ1dHRvbiBpZD0icmVsU3ViQWRkIj5BZGQgc3VidGFzazwvYnV0dG9uPjwvZGl2PjwvZGl2PmA7CiAgaHRtbCs9YDxkaXYgY2xhc3M9InJlbC1zZWMiPjxzcGFuIGNsYXNzPSJoIj5ibG9ja2VkIGJ5IChkZXBlbmRlbmNpZXMpPC9zcGFuPmA7CiAgaHRtbCs9IGRlcHMubGVuZ3RoID8gZGVwcy5tYXAoZD0+YDxkaXYgY2xhc3M9InJlbC1yb3ciPjxhIGNsYXNzPSJyZWwtbGluayIgZGF0YS1vcGVuPSIke2QuaWR9Ij4ke2lzVGVybWluYWwoZC5zdGF0ZSk/J+Kckyc6J+KblCd9ICR7ZXNjKHNob3J0VGl0bGUoZCkpfTwvYT4ke2JhZGdlKGQuc3RhdGUpfTxidXR0b24gY2xhc3M9InJlbC1kZWwiIGRhdGEtZGVsZGVwPSIke2QuaWR9IiB0aXRsZT0icmVtb3ZlIGRlcGVuZGVuY3kiPsOXPC9idXR0b24+PC9kaXY+YCkuam9pbignJykKICAgICAgICAgICAgICAgICAgICAgIDogYDxkaXYgY2xhc3M9InJlbC1lbXB0eSI+Tm90IGJsb2NrZWQgYnkgYW55dGhpbmcuPC9kaXY+YDsKICBjb25zdCBvcHRzPWJvYXJkLm9yZGVyLm1hcChpZD0+Ym9hcmQudGFza3NbaWRdKS5maWx0ZXIoeD0+eCYmeC5pZCE9PXQuaWQmJiEodC5kZXBlbmRzT258fFtdKS5pbmNsdWRlcyh4LmlkKSYmeC5wYXJlbnQhPT10LmlkKQogICAgIC5tYXAoeD0+YDxvcHRpb24gdmFsdWU9IiR7eC5pZH0iPiR7ZXNjKHNob3J0VGl0bGUoeCkpfSDigJQgJHtlc2MoU1RMQUJFTFt4LnN0YXRlXXx8eC5zdGF0ZSl9PC9vcHRpb24+YCkuam9pbignJyk7CiAgaHRtbCs9YDxkaXYgY2xhc3M9InJlbC1hZGQiPjxzZWxlY3QgaWQ9InJlbERlcFNlbCI+PG9wdGlvbiB2YWx1ZT0iIj5hZGQgYSBkZXBlbmRlbmN54oCmPC9vcHRpb24+JHtvcHRzfTwvc2VsZWN0PjxidXR0b24gaWQ9InJlbERlcEFkZCI+QWRkPC9idXR0b24+PC9kaXY+PC9kaXY+YDsKICBodG1sKz1gPGRpdiBjbGFzcz0icmVsLXNlYyI+PGxhYmVsIGNsYXNzPSJyZWwtZ2F0ZSI+PHNwYW4gY2xhc3M9InRvZ2dsZSR7dC5oYXJkR2F0ZT8nIG9uJzonJ30iIGlkPSJyZWxHYXRlIj48c3BhbiBjbGFzcz0ic3ciPjwvc3Bhbj48L3NwYW4+IGhhcmQgZ2F0ZSDigJQgYmxvY2sgZW50ZXJpbmcg4oCcd29ya2luZ+KAnSB1bnRpbCBwcmVyZXF1aXNpdGVzIGFyZSBkb25lIDxzcGFuIGNsYXNzPSJnYXRlLWhpbnQiPihvZmYgYnkgZGVmYXVsdCk8L3NwYW4+PC9sYWJlbD48L2Rpdj5gOwogIGNhcmRSZWwuaW5uZXJIVE1MPWh0bWw7IHNob3coY2FyZFJlbCx0cnVlKTsKICBjYXJkUmVsLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLW9wZW5dJykuZm9yRWFjaChhPT5hLm9uY2xpY2s9KCk9Pm9wZW5DYXJkKGEuZGF0YXNldC5vcGVuKSk7CiAgY29uc3Qgc3ViVGV4dD1jYXJkUmVsLnF1ZXJ5U2VsZWN0b3IoJyNyZWxTdWJUZXh0JyksIHN1YkFkZD1jYXJkUmVsLnF1ZXJ5U2VsZWN0b3IoJyNyZWxTdWJBZGQnKTsKICBpZihzdWJBZGQpIHN1YkFkZC5vbmNsaWNrPSgpPT57IGNvbnN0IHY9KHN1YlRleHQudmFsdWV8fCcnKS50cmltKCk7IGlmKCF2KXJldHVybjsgc3ViQWRkLmRpc2FibGVkPXRydWU7IHVwZCh7b3A6J2FkZCcsdGV4dDp2LHBhcmVudDp0LmlkfSkudGhlbihwdWxsKTsgfTsKICBpZihzdWJUZXh0KSBzdWJUZXh0Lm9ua2V5ZG93bj1lPT57IGlmKGUua2V5PT09J0VudGVyJyl7ZS5wcmV2ZW50RGVmYXVsdCgpOyBzdWJBZGQuY2xpY2soKTt9IH07CiAgY29uc3QgZGVwU2VsPWNhcmRSZWwucXVlcnlTZWxlY3RvcignI3JlbERlcFNlbCcpLCBkZXBBZGQ9Y2FyZFJlbC5xdWVyeVNlbGVjdG9yKCcjcmVsRGVwQWRkJyk7CiAgaWYoZGVwQWRkKSBkZXBBZGQub25jbGljaz0oKT0+eyBjb25zdCB2PWRlcFNlbC52YWx1ZTsgaWYoIXYpcmV0dXJuOyB1cGQoe29wOidzZXQnLGlkOnQuaWQsZGVwZW5kc09uOlsuLi4odC5kZXBlbmRzT258fFtdKSx2XX0pLnRoZW4ocHVsbCk7IH07CiAgY2FyZFJlbC5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1kZWxkZXBdJykuZm9yRWFjaChiPT5iLm9uY2xpY2s9KCk9PnVwZCh7b3A6J3NldCcsaWQ6dC5pZCxkZXBlbmRzT246KHQuZGVwZW5kc09ufHxbXSkuZmlsdGVyKHg9PnghPT1iLmRhdGFzZXQuZGVsZGVwKX0pLnRoZW4ocHVsbCkpOwogIGNvbnN0IGdhdGU9Y2FyZFJlbC5xdWVyeVNlbGVjdG9yKCcjcmVsR2F0ZScpOwogIGlmKGdhdGUpIGdhdGUub25jbGljaz0oKT0+dXBkKHtvcDonc2V0JyxpZDp0LmlkLGhhcmRHYXRlOiF0LmhhcmRHYXRlfSkudGhlbihwdWxsKTsKfQovLyBtYW51YWwgc3RhdHVzIGNvbnRyb2w6IGEgZHJvcGRvd24gb24gdGhlIGNhcmQgdG8gbW92ZSBzdGF0ZSBiYWNrIChlLmcuIHJldmlldyAtPiB3b3JraW5nKSB3aXRob3V0IGVkaXRpbmcgSlNPTgpjYXJkU3RhdGUuaW5uZXJIVE1MPVNUQVRFUy5tYXAocz0+YDxvcHRpb24gdmFsdWU9IiR7c30iPiR7ZXNjKFNUTEFCRUxbc118fHMpfTwvb3B0aW9uPmApLmpvaW4oJycpOwpjYXJkU3RhdGUub25jaGFuZ2U9KCk9PnsgY29uc3QgdD1jYXJkT3BlbklkJiZib2FyZC50YXNrc1tjYXJkT3BlbklkXTsgY29uc3Qgdj1jYXJkU3RhdGUudmFsdWU7CiAgaWYoIXR8fHY9PT10LnN0YXRlKSByZXR1cm47CiAgc3RhdHVzQXBpKHtpZDpjYXJkT3BlbklkLHN0YXRlOnYsYnk6J0NFTyd9KS50aGVuKHI9PnsgaWYociYmci5lcnJvcikgYWxlcnQoci5lcnJvcik7IHB1bGwoKTsgfSk7IH07CgovLyBicmFpbnN0b3JtIGdhdGUgKHNsaWNlIGQpOiByZW5kZXIgdGhlIGludGVyYWN0aXZlIFEmQS4gUmVidWlsZHMgT05MWSB3aGVuIHRoZSBzZXJ2ZXItc2lkZQovLyBxdWVzdGlvbi9hbnN3ZXIgc3RhdGUgY2hhbmdlcyAoc2lnbmF0dXJlKSwgc28gYSBoYWxmLXR5cGVkIGFuc3dlciArIGZvY3VzIHN1cnZpdmUgbGl2ZSBwb2xscy4KZnVuY3Rpb24gcmVuZGVyQ2FyZFFhKHQpewogIGlmKHQuc3RhdGUhPT0nbmVlZHNfYnJhaW5zdG9ybScpeyBzaG93KGNhcmRRYSxmYWxzZSk7IGNhcmRRYS5fc2lnPW51bGw7IHJldHVybjsgfQogIGNvbnN0IHFzPXQucXVlc3Rpb25zfHxbXTsKICBjb25zdCB1YT1xcy5maWx0ZXIocT0+IShxLmFuc3dlcnx8JycpLnRyaW0oKSkubGVuZ3RoOwogIGNvbnN0IGhhc0FydD0hISh0LmJyYWluc3Rvcm18fCcnKS50cmltKCk7CiAgY29uc3QgcmVhZHk9dWE9PT0wICYmIChxcy5sZW5ndGg+MCB8fCBoYXNBcnQpOwogIHNob3coY2FyZFFhLHRydWUpOwogIGNvbnN0IHNpZz1KU09OLnN0cmluZ2lmeSh7YXNrOnQuYnJhaW5zdG9ybUFza2VkLGFydDpoYXNBcnQscTpxcy5tYXAocT0+W3EuaWQsISEocS5hbnN3ZXJ8fCcnKS50cmltKCldKX0pOwogIGlmKGNhcmRRYS5fc2lnPT09c2lnKSByZXR1cm47ICAgICAgICAgICAgICAgICAvLyBubyBzZXJ2ZXIgY2hhbmdlIC0+IGRvbid0IGNsb2JiZXIgaW5wdXRzL2ZvY3VzCiAgY2FyZFFhLl9zaWc9c2lnOwogIGxldCBodG1sPScnOwogIGlmKHFzLmxlbmd0aCl7CiAgICBodG1sICs9IHVhPjAKICAgICAgPyBgPGRpdiBjbGFzcz0icWEtYmFubmVyIGJsb2NrZWQiPuKaoCBOb3Qgd29ya2FibGUg4oCUICR7dWF9IG9wZW4gcXVlc3Rpb24ke3VhPjE/J3MnOicnfS4gQW5zd2VyIHRvIHVuYmxvY2sgdGhpcyB0YXNrLjwvZGl2PmAKICAgICAgOiBgPGRpdiBjbGFzcz0icWEtYmFubmVyIHJlYWR5Ij7inJMgQWxsIHF1ZXN0aW9ucyBhbnN3ZXJlZCDigJQgcmVhZHkgdG8gcHJvbW90ZS48L2Rpdj5gOwogICAgaHRtbCArPSAnPGRpdiBjbGFzcz0icWEtbGlzdCI+Jytxcy5tYXAocT0+ewogICAgICBjb25zdCBhPShxLmFuc3dlcnx8JycpLnRyaW0oKTsKICAgICAgcmV0dXJuIGEKICAgICAgICA/IGA8ZGl2IGNsYXNzPSJxYS1pdGVtIGFuc3dlcmVkIj48ZGl2IGNsYXNzPSJxIj4ke2VzYyhxLnEpfTwvZGl2PjxkaXYgY2xhc3M9InFhLWFucyI+JHtlc2MoYSl9PC9kaXY+PC9kaXY+YAogICAgICAgIDogYDxkaXYgY2xhc3M9InFhLWl0ZW0iIGRhdGEtcWlkPSIke2VzYyhxLmlkKX0iPjxkaXYgY2xhc3M9InEiPiR7ZXNjKHEucSl9PC9kaXY+YCsKICAgICAgICAgIGA8ZGl2IGNsYXNzPSJxYS1hbnMtcm93Ij48dGV4dGFyZWEgcGxhY2Vob2xkZXI9IkFuc3dlcuKApiI+PC90ZXh0YXJlYT48YnV0dG9uIGNsYXNzPSJxYS1hbnMtYnRuIj5BbnN3ZXI8L2J1dHRvbj48L2Rpdj48L2Rpdj5gOwogICAgfSkuam9pbignJykrJzwvZGl2Pic7CiAgfSBlbHNlIGlmKGhhc0FydCl7CiAgICBodG1sICs9IGA8ZGl2IGNsYXNzPSJxYS1iYW5uZXIgcmVhZHkiPuKckyBCcmFpbnN0b3JtZWQg4oCUIHJlYWR5IHRvIHByb21vdGUgdG8gd29ya2luZy48L2Rpdj5gOwogIH0gZWxzZSB7CiAgICBodG1sICs9IGA8ZGl2IGNsYXNzPSJxYS1iYW5uZXIgYmxvY2tlZCI+4oyBIEJyYWluc3Rvcm1pbmcg4oCUIGdlbmVyYXRpbmcgY2xhcmlmeWluZyBxdWVzdGlvbnMgZm9yIHRoZSBDRU/igKY8L2Rpdj5gOwogIH0KICBpZihyZWFkeSkgaHRtbCArPSBgPGJ1dHRvbiBjbGFzcz0icWEtcHJvbW90ZSI+UHJvbW90ZSB0byB3b3JraW5nIOKGkjwvYnV0dG9uPmA7CiAgY2FyZFFhLmlubmVySFRNTD1odG1sOwogIGNhcmRRYS5xdWVyeVNlbGVjdG9yQWxsKCcucWEtaXRlbVtkYXRhLXFpZF0nKS5mb3JFYWNoKGl0PT57CiAgICBjb25zdCBxaWQ9aXQuZGF0YXNldC5xaWQsIHRhPWl0LnF1ZXJ5U2VsZWN0b3IoJ3RleHRhcmVhJyk7CiAgICBjb25zdCBzdWJtaXQ9KCk9PnsgY29uc3Qgdj10YS52YWx1ZS50cmltKCk7IGlmKCF2KXJldHVybjsgYW5zd2VyQXBpKHt0YXNrX2lkOmNhcmRPcGVuSWQscWlkLGFuc3dlcjp2LGJ5OidDRU8nfSkudGhlbihwdWxsKTsgfTsKICAgIGl0LnF1ZXJ5U2VsZWN0b3IoJy5xYS1hbnMtYnRuJykub25jbGljaz1zdWJtaXQ7CiAgICB0YS5vbmtleWRvd249ZT0+eyBpZigoZS5tZXRhS2V5fHxlLmN0cmxLZXkpJiZlLmtleT09PSdFbnRlcicpeyBlLnByZXZlbnREZWZhdWx0KCk7IHN1Ym1pdCgpOyB9IH07CiAgfSk7CiAgY29uc3QgcGI9Y2FyZFFhLnF1ZXJ5U2VsZWN0b3IoJy5xYS1wcm9tb3RlJyk7CiAgaWYocGIpIHBiLm9uY2xpY2s9KCk9PmJyYWluc3Rvcm1BcGkoe2lkOmNhcmRPcGVuSWQscHJvbW90ZTond29ya2luZyd9KS50aGVuKHB1bGwpOwp9CgpmdW5jdGlvbiByZWx0aW1lKHRzKXsgaWYoIXRzKXJldHVybicnOyBjb25zdCBzPU1hdGguZmxvb3IoKERhdGUubm93KCktdHMpLzEwMDApOwogIGlmKHM8NjApcmV0dXJuIHMrJ3MgYWdvJzsgY29uc3QgbT1NYXRoLmZsb29yKHMvNjApOyBpZihtPDYwKXJldHVybiBtKydtIGFnbyc7CiAgY29uc3QgaD1NYXRoLmZsb29yKG0vNjApOyBpZihoPDI0KXJldHVybiBoKydoIGFnbyc7IGNvbnN0IGQ9TWF0aC5mbG9vcihoLzI0KTsKICByZXR1cm4gZDw3PyBkKydkIGFnbycgOiBuZXcgRGF0ZSh0cykudG9Mb2NhbGVEYXRlU3RyaW5nKCk7IH0KZnVuY3Rpb24gZXZDbGFzcyhieSxraW5kKXsgaWYoa2luZD09PSdicmFpbnN0b3JtJylyZXR1cm4nYnJhaW4nOyByZXR1cm4gKGJ5fHwnJykudG9Mb3dlckNhc2UoKT09PSdjZW8nPydjZW8nOidhZ2VudCc7IH0KZnVuY3Rpb24gYnlMYWJlbChieSl7IGlmKCFieSlyZXR1cm4nc3lzdGVtJzsgaWYoYnkudG9Mb3dlckNhc2UoKT09PSdjZW8nKXJldHVybidDRU8nOyBpZihieT09PSdicmFpbnN0b3JtJylyZXR1cm4nQnJhaW5zdG9ybSc7IHJldHVybiBieTsgfQpmdW5jdGlvbiBpbml0aWFscyhieSl7IGlmKCFieSlyZXR1cm4n4oCiJzsgaWYoYnkudG9Mb3dlckNhc2UoKT09PSdjZW8nKXJldHVybidDRU8nOyBpZihieT09PSdicmFpbnN0b3JtJylyZXR1cm4nQlInOwogIGNvbnN0IHRhaWw9Ynkuc3BsaXQoJy8nKS5wb3AoKS5zcGxpdCgnOicpLnBvcCgpOyByZXR1cm4gKHRhaWx8fGJ5KS5yZXBsYWNlKC9bXmEtejAtOV0vZ2ksJycpLnNsaWNlKDAsMikudG9VcHBlckNhc2UoKXx8J+KAoic7IH0KCmZ1bmN0aW9uIGV2SHRtbChpdCl7CiAgLy8gY29tcGFjdCBjZW50ZXJlZCBtYXJrZXJzOiBvcGVuZWQsIHN0YXRlIHRyYW5zaXRpb25zLCBicmFpbnN0b3JtLXNhdmVkLgogIC8vICh0aGUgYnJhaW5zdG9ybSBhcnRpZmFjdCdzIGZ1bGwgdGV4dCBpcyBwaW5uZWQgYWJvdmUgdGhlIHRocmVhZCwgc28gdGhlIHRpbWVsaW5lCiAgLy8gIG9ubHkgbWFya3MgV0hFTiBpdCB3YXMgc2F2ZWQvdXBkYXRlZCDigJQgbm8gZHVwbGljYXRlZCB3YWxsIG9mIHRleHQuKQogIGlmKGl0LmtpbmQ9PT0nc3RhdGUnfHxpdC5raW5kPT09J29wZW5lZCd8fGl0LmtpbmQ9PT0nYnJhaW5zdG9ybScpewogICAgY29uc3QgdHh0ID0gaXQua2luZD09PSdvcGVuZWQnID8gJ29wZW5lZCB0aGlzIHRhc2snCiAgICAgICAgICAgICAgOiBpdC5raW5kPT09J2JyYWluc3Rvcm0nID8gYGJyYWluc3Rvcm0gYXJ0aWZhY3Qgc2F2ZWQgYnkgJHtlc2MoYnlMYWJlbChpdC5ieSkpfWAKICAgICAgICAgICAgICA6IGVzYyhpdC5ib2R5KTsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0iZXYgc3RhdGUiPjxzcGFuIGNsYXNzPSJldi10ZXh0Ij7ijIEgJHt0eHR9IMK3ICR7cmVsdGltZShpdC50cyl9PC9zcGFuPjwvZGl2PmA7CiAgfQogIGxldCBib2R5OwogIGlmKGl0LmtpbmQ9PT0ncHJvb2YnKXsKICAgIGJvZHk9KGl0LmJvZHk/YDxkaXYgY2xhc3M9ImV2LXRleHQiPiR7ZXNjKGl0LmJvZHkpfTwvZGl2PmA6JycpK2A8ZGl2IGNsYXNzPSJldi1wcm9vZnMiPiR7cHJvb2ZDaGlwKGl0LnByb29mKX08L2Rpdj5gOwogIH1lbHNleyBib2R5PWA8ZGl2IGNsYXNzPSJldi10ZXh0Ij4ke2VzYyhpdC5ib2R5KX08L2Rpdj5gOyB9CiAgY29uc3Qga2luZExibCA9IGl0LmtpbmQ9PT0nY29tbWVudCcgPyAnJyA6IGA8c3BhbiBjbGFzcz0iZXYta2luZCI+JHtlc2MoaXQua2luZCl9PC9zcGFuPmA7CiAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJldiBldi0ke2l0LmtpbmR9Ij48ZGl2IGNsYXNzPSJhdiAke2V2Q2xhc3MoaXQuYnksaXQua2luZCl9Ij4ke2VzYyhpbml0aWFscyhpdC5ieSkpfTwvZGl2PmArCiAgICBgPGRpdiBjbGFzcz0iZXYtYm9keSI+PGRpdiBjbGFzcz0iZXYtaGQiPjxzcGFuIGNsYXNzPSJldi1ieSI+JHtlc2MoYnlMYWJlbChpdC5ieSkpfTwvc3Bhbj4ke2tpbmRMYmx9YCsKICAgIGA8c3BhbiBjbGFzcz0iZXYtdGltZSI+JHtyZWx0aW1lKGl0LnRzKX08L3NwYW4+PC9kaXY+JHtib2R5fTwvZGl2PjwvZGl2PmA7Cn0KCi8vIFJlLXJlbmRlciBpcyBJTkNSRU1FTlRBTCBhbmQgbm9uLWRpc3J1cHRpdmU6IHRoZSBsaXZlIHBvbGwgbXVzdCBuZXZlciB5YW5rIHRoZSBtb2RhbCB0byB0aGUgdG9wCi8vIG9yIHN0ZWFsIGZvY3VzIGZyb20gdGhlIGNvbXBvc2VyLiBXZSBvbmx5IHRvdWNoIGEgcmVnaW9uIHdoZW4gaXRzIGRhdGEgYWN0dWFsbHkgY2hhbmdlZCwgYW5kIHRoZQovLyB0aHJlYWQgaXMgQVBQRU5ELU9OTFkgKG5ldyBldmVudHMgYXJlIGFkZGVkIHRvIHRoZSBlbmQ7IGV4aXN0aW5nIG5vZGVzIOKAlCBhbmQgdGhlaXIgaW1hZ2VzIOKAlCBhcmUKLy8gbmV2ZXIgcmVidWlsdCkuIFNvIHNjcm9sbFRvcCBob2xkcyBhbmQgdGhlIGNvbXBvc2VyJ3MgZm9jdXMvY2FyZXQvdHlwZWQgdGV4dCBzdXJ2aXZlIGV2ZXJ5IHRpY2suCmZ1bmN0aW9uIHJlbmRlckNhcmQoKXsKICBpZighY2FyZE9wZW5JZCkgcmV0dXJuOwogIGNvbnN0IHQ9Ym9hcmQudGFza3NbY2FyZE9wZW5JZF07CiAgaWYoIXQpeyBjbG9zZUNhcmQoKTsgcmV0dXJuOyB9ICAgICAgICAgICAgICAgICAvLyB0YXNrIGRlbGV0ZWQgd2hpbGUgb3BlbgogIGNvbnN0IHRpdGxlPXQudGV4dHx8Jyh1bnRpdGxlZCknOwogIGlmKGNhcmRUaXRsZS50ZXh0Q29udGVudCE9PXRpdGxlKSBjYXJkVGl0bGUudGV4dENvbnRlbnQ9dGl0bGU7CiAgLy8gc3ViLWhlYWRlcjogcmVidWlsZCBPTkxZIHdoZW4gYSBkaXNwbGF5ZWQgZmllbGQgY2hhbmdlcyAoYXZvaWRzIHBlci10aWNrIHJlZmxvdy9mb2N1cyBjaHVybikKICBjb25zdCBjYW5BdHRhY2g9aXNBdHRhY2hhYmxlKHQuYXNzaWduZWUpOwogIGNvbnN0IHN1YlNpZz1KU09OLnN0cmluZ2lmeShbdC5zdGF0ZSx0LmFzc2lnbmVlLHQud29ya1RvRG9uZSx0LnZlcmlmaWVkLGNhbkF0dGFjaF0pOwogIGlmKGNhcmRTdWIuX3NpZyE9PXN1YlNpZyl7IGNhcmRTdWIuX3NpZz1zdWJTaWc7CiAgICBjYXJkU3ViLmlubmVySFRNTD1gPHNwYW4gY2xhc3M9ImJhZGdlIHN0LSR7dC5zdGF0ZX0iPiR7ZXNjKFNUTEFCRUxbdC5zdGF0ZV18fHQuc3RhdGUpfTwvc3Bhbj5gKwogICAgICBgPHNwYW4gY2xhc3M9InRhZyR7Y2FuQXR0YWNoPycgYXR0YWNoJzonJ30iJHtjYW5BdHRhY2g/YCBkYXRhLWF0dGFjaD0iJHtlc2ModC5hc3NpZ25lZSl9IiB0aXRsZT0iY2xpY2sgdG8gYXR0YWNoIHRvICR7ZXNjKHQuYXNzaWduZWUpfeKAmXMgdGVybWluYWwiYDonJ30+YCsKICAgICAgYCR7dC5hc3NpZ25lZT8nQCcrZXNjKHQuYXNzaWduZWUpOid1bmFzc2lnbmVkJ308L3NwYW4+YCsKICAgICAgKHQud29ya1RvRG9uZT8nPHNwYW4gY2xhc3M9InRhZyI+d29yayDihpIgZG9uZTwvc3Bhbj4nOicnKSsKICAgICAgKHQudmVyaWZpZWQ/JzxzcGFuIGNsYXNzPSJiYWRnZSBzdC1kb25lIj52ZXJpZmllZDwvc3Bhbj4nOicnKSsKICAgICAgYDxzcGFuIGNsYXNzPSJjYXJkLWlkIj4jJHtlc2MoY2FyZE9wZW5JZCl9PC9zcGFuPmA7CiAgfQogIGlmKGRvY3VtZW50LmFjdGl2ZUVsZW1lbnQhPT1jYXJkU3RhdGUgJiYgY2FyZFN0YXRlLnZhbHVlIT09dC5zdGF0ZSkgY2FyZFN0YXRlLnZhbHVlPXQuc3RhdGU7ICAgLy8ga2VlcCB0aGUgc3RhdHVzIGNvbnRyb2wgaW4gc3luYyAoZG9uJ3QgZmlnaHQgdGhlIENFTyBtaWQtc2VsZWN0KQogIGlmKCh0LmRvbmVDb25kaXRpb258fCcnKS50cmltKCkpeyBpZihjYXJkQ29uZEJvZHkudGV4dENvbnRlbnQhPT10LmRvbmVDb25kaXRpb24pIGNhcmRDb25kQm9keS50ZXh0Q29udGVudD10LmRvbmVDb25kaXRpb247IHNob3coY2FyZENvbmQsdHJ1ZSk7IH0gZWxzZSBzaG93KGNhcmRDb25kLGZhbHNlKTsKICByZW5kZXJDYXJkUWEodCk7ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAvLyBicmFpbnN0b3JtIGdhdGUgKHNsaWNlIGQpLCBhbHJlYWR5IHNpZ25hdHVyZS1nYXRlZAogIGlmKCh0LmJyYWluc3Rvcm18fCcnKS50cmltKCkpeyBpZihjYXJkQXJ0Qm9keS50ZXh0Q29udGVudCE9PXQuYnJhaW5zdG9ybSkgY2FyZEFydEJvZHkudGV4dENvbnRlbnQ9dC5icmFpbnN0b3JtOyBzaG93KGNhcmRBcnQsdHJ1ZSk7IH0gZWxzZSBzaG93KGNhcmRBcnQsZmFsc2UpOwogIHJlbmRlclJlbGF0aW9ucyh0KTsgICAgICAgICAgICAgICAgICAgICAgICAgICAgIC8vIHN1YnRhc2tzICsgZGVwZW5kZW5jaWVzIHBhbmVsIChpc3N1ZSAjMykKICAvLyB0aHJlYWQ6IGFwcGVuZCBvbmx5IHRoZSBldmVudHMgbm90IGFscmVhZHkgaW4gdGhlIERPTSAoa2V5ZWQpIOKAlCBuZXZlciByZWJ1aWxkIGV4aXN0aW5nIG5vZGVzCiAgY29uc3QgaXRlbXM9W3trZXk6J29wZW5lZCcsdHM6dC5jcmVhdGVkLGtpbmQ6J29wZW5lZCcsYnk6J0NFTycsYm9keTonJ31dOwogICh0LmNvbW1lbnRzfHxbXSkuZm9yRWFjaChjPT5pdGVtcy5wdXNoKHtrZXk6J2M6JytjLmlkLHRzOmMudHMsa2luZDpjLmtpbmQsYnk6Yy5ieSxib2R5OmMuYm9keX0pKTsKICAodC5wcm9vZnN8fFtdKS5mb3JFYWNoKHA9Pml0ZW1zLnB1c2goe2tleToncDonK3AuaWQsdHM6cC50cyxraW5kOidwcm9vZicsYnk6cC5ieSxib2R5OnAuY2FwdGlvbnx8JycscHJvb2Y6cH0pKTsKICBpdGVtcy5zb3J0KChhLGIpPT4oYS50c3x8MCktKGIudHN8fDApKTsKICBtYXJrVGFza1JlYWQoY2FyZE9wZW5JZCk7CiAgY29uc3QgaGF2ZT1uZXcgU2V0KFsuLi5jYXJkVGhyZWFkLmNoaWxkcmVuXS5tYXAobj0+bi5kYXRhc2V0LmspKTsKICBjb25zdCBuZWFyQm90dG9tPShtb2RhbC5zY3JvbGxIZWlnaHQtbW9kYWwuc2Nyb2xsVG9wLW1vZGFsLmNsaWVudEhlaWdodCk8NjA7CiAgbGV0IGFkZGVkPWZhbHNlOwogIGl0ZW1zLmZvckVhY2goaXQ9PnsgaWYoaGF2ZS5oYXMoaXQua2V5KSlyZXR1cm47CiAgICBjb25zdCB0bXA9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7IHRtcC5pbm5lckhUTUw9ZXZIdG1sKGl0KTsgY29uc3Qgbm9kZT10bXAuZmlyc3RFbGVtZW50Q2hpbGQ7CiAgICBpZihub2RlKXsgbm9kZS5kYXRhc2V0Lms9aXQua2V5OyBjYXJkVGhyZWFkLmFwcGVuZENoaWxkKG5vZGUpOyBhZGRlZD10cnVlOyB9IH0pOwogIC8vIGFwcGVuZGVkIGV2ZW50cyBzaXQgQkVMT1cgdGhlIHZpZXdwb3J0LCBzbyBzY3JvbGxUb3AgaXMgdW5hZmZlY3RlZDsgb25seSBhdXRvLWZvbGxvdyBpZiB0aGUKICAvLyBDRU8gd2FzIGFscmVhZHkgYXQgdGhlIGJvdHRvbSAoZG9uJ3QgeWFuayBoaW0gdXAgaWYgaGUncyByZWFkaW5nL3Njcm9sbGVkIG1pZC10aHJlYWQpCiAgaWYoYWRkZWQgJiYgbmVhckJvdHRvbSkgbW9kYWwuc2Nyb2xsVG9wPW1vZGFsLnNjcm9sbEhlaWdodDsKfQoKZnVuY3Rpb24gb3BlbkNhcmQoaWQpeyBpZighYm9hcmQudGFza3NbaWRdKXJldHVybjsgY2FyZE9wZW5JZD1pZDsgbW9kYWwuY2xhc3NMaXN0LmFkZCgnc2hvdycpOwogIGRvY3VtZW50LmJvZHkuc3R5bGUub3ZlcmZsb3c9J2hpZGRlbic7IGNhcmRDb21wb3NlLnZhbHVlPScnOwogIGNhcmRUaHJlYWQuaW5uZXJIVE1MPScnOyBjYXJkU3ViLl9zaWc9bnVsbDsgY2FyZFFhLl9zaWc9bnVsbDsgY2FyZFJlbC5fc2lnPW51bGw7IG1vZGFsLnNjcm9sbFRvcD0wOyAgIC8vIGZyZXNoIHJlbmRlciBmb3IgdGhpcyBjYXJkCiAgbWFya1Rhc2tSZWFkKGlkKTsKICByZW5kZXJDYXJkKCk7CiAgaWYobG9jYXRpb24uaGFzaCE9PScjY2FyZC8nK2lkKXsgdHJ5e2hpc3RvcnkucmVwbGFjZVN0YXRlKG51bGwsJycsJyNjYXJkLycraWQpO31jYXRjaChlKXsgbG9jYXRpb24uaGFzaD0nY2FyZC8nK2lkOyB9IH0gfQpmdW5jdGlvbiBjbG9zZUNhcmQoKXsgY2FyZE9wZW5JZD1udWxsOyBtb2RhbC5jbGFzc0xpc3QucmVtb3ZlKCdzaG93Jyk7IGRvY3VtZW50LmJvZHkuc3R5bGUub3ZlcmZsb3c9Jyc7IGNhcmRDb21wb3NlLnZhbHVlPScnOwogIGlmKC9eI2NhcmRcLy8udGVzdChsb2NhdGlvbi5oYXNofHwnJykpeyB0cnl7aGlzdG9yeS5yZXBsYWNlU3RhdGUobnVsbCwnJyxsb2NhdGlvbi5wYXRobmFtZStsb2NhdGlvbi5zZWFyY2gpO31jYXRjaChlKXsgbG9jYXRpb24uaGFzaD0nJzsgfSB9IH0KLy8gZGVlcCBsaW5rOiAjY2FyZC88aWQ+IG9wZW5zIHRoYXQgY2FyZCBkaXJlY3RseSAodGhlIFdoYXRzQXBwIHBpbmcgbGlua3Mgc3RyYWlnaHQgdG8gdGhlIGNhcmQpCmZ1bmN0aW9uIGNoZWNrSGFzaCgpeyBjb25zdCBtPShsb2NhdGlvbi5oYXNofHwnJykubWF0Y2goL14jY2FyZFwvKFthLXowLTldKykkL2kpOwogIGlmKG0gJiYgYm9hcmQudGFza3NbbVsxXV0gJiYgY2FyZE9wZW5JZCE9PW1bMV0pIG9wZW5DYXJkKG1bMV0pOyB9CndpbmRvdy5hZGRFdmVudExpc3RlbmVyKCdoYXNoY2hhbmdlJyxjaGVja0hhc2gpOwpmdW5jdGlvbiBwb3N0Q29tbWVudCgpeyBjb25zdCB2PWNhcmRDb21wb3NlLnZhbHVlLnRyaW0oKTsgaWYoIXZ8fCFjYXJkT3BlbklkKXJldHVybjsKICBjYXJkQ29tcG9zZS52YWx1ZT0nJzsgY29tbWVudEFwaSh7dGFza19pZDpjYXJkT3BlbklkLGJvZHk6dixieTonQ0VPJ30pLnRoZW4ocHVsbCk7IH0KCmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjYXJkQ2xvc2UnKS5vbmNsaWNrPWNsb3NlQ2FyZDsKY2FyZFN1Yi5vbmNsaWNrPWU9PnsgY29uc3QgYz1lLnRhcmdldC5jbG9zZXN0KCcudGFnLmF0dGFjaCcpOyBpZihjJiZjLmRhdGFzZXQuYXR0YWNoKSBhdHRhY2hUb0VuZ2luZWVyKGMuZGF0YXNldC5hdHRhY2gpOyB9Owpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FyZENvbW1lbnRCdG4nKS5vbmNsaWNrPXBvc3RDb21tZW50OwpjYXJkQ29tcG9zZS5vbmtleWRvd249ZT0+eyBpZigoZS5tZXRhS2V5fHxlLmN0cmxLZXkpJiZlLmtleT09PSdFbnRlcicpeyBlLnByZXZlbnREZWZhdWx0KCk7IHBvc3RDb21tZW50KCk7IH0gfTsKbW9kYWwub25jbGljaz1lPT57IGlmKGUudGFyZ2V0PT09bW9kYWwpIGNsb3NlQ2FyZCgpOyB9OyAgICAgICAgICAvLyBjbGljayBiYWNrZHJvcCB0byBjbG9zZQpkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJyxlPT57IGlmKGUua2V5PT09J0VzY2FwZScmJmNhcmRPcGVuSWQpIGNsb3NlQ2FyZCgpOyB9KTsKCmZ1bmN0aW9uIGNsb2NrKCl7IGNvbnN0IGQ9bmV3IERhdGUoKTsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Nsb2NrJykudGV4dENvbnRlbnQ9ZC50b0xvY2FsZVRpbWVTdHJpbmcoKTsgfQpzZXRJbnRlcnZhbChjbG9jaywxMDAwKTsgY2xvY2soKTsKaW5pdFZpZXdiYXIoKTsgcmVuZGVyVmlld2JhcigpOyAgIC8vIGJ1aWxkICsgcmVzdG9yZSB0aGUgZmlsdGVyL3NvcnQgY29udHJvbHMgYmVmb3JlIGZpcnN0IHBhaW50CnNldEludGVydmFsKHB1bGwsMTAwMCk7IHB1bGwoKTsgICAvLyAxcyBsaXZlIHBvbGwsIGluY3JlbWVudGFsIOKAlCBubyByZWxvYWQsIGRpcnR5IGZpZWxkcyBwcmVzZXJ2ZWQKaW5wdXQuZm9jdXMoKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo= | base64 -d > "$INSTALL_DIR/bin/todos.html"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvLXJlY29uY2lsZSDigJQgdGhlIGRldGVybWluaXN0aWMgbWVjaGFuaWNzIG9mIEJvc3MgUnVsZSA0LgoKVGhlIEJvc3MgcnVucyB0aGlzIG9uIGV2ZXJ5IHBpbmcvU3RvcC9jaGFuZ2UuIEl0IGRvZXMgdGhlIG5vbi1qdWRnbWVudCBwYXJ0czoKICAtIHdvcmtpbmcgKyB3b3JrVG9Eb25lICsgdW5hc3NpZ25lZCAtPiBhc3NpZ24gYW4gaWRsZSBlbmdpbmVlciArIGRpc3BhdGNoCiAgLSB3b3JraW5nICsgcHJvb2YgcHJlc2VudCAgICAgICAgICAgIC0+IGF1dG8tdmVyaWZ5IG1hY2hpbmUtY2hlY2thYmxlIGNvbmRpdGlvbnMKSnVkZ21lbnQgcGFydHMgKGJyYWluc3Rvcm0gd29yZGluZywgZnV6enkgdmVyaWZpY2F0aW9uKSBzdGF5IHdpdGggdGhlIEJvc3MuCgpFbnY6CiAgVE9ET19IT1NUICAgICAgICgxMjcuMC4wLjE6OTkwMCkKICBRVUVVRV9TRUNSRVQgICAgKHNlbnQgb24gd3JpdGVzKQogIERJU1BBVENIICAgICAgICAnbXAnIChyZWFsOiBtcCBzZW5kKSB8ICdzaW0nIChydW4gRU5HSU5FRVJfU0lNKSB8ICdub25lJwogIEVOR0lORUVSX1BPT0wgICBjb21tYSBsaXN0IG9mIGlkbGUgZW5naW5lZXJzIChyZWFsOiBmcm9tIGBtcCBzdGF0dXNgKTsgZGVmYXVsdCAnbWFpbjplbmctMScKICBFTkdJTkVFUl9TSU0gICAgcGF0aCB0byBhIHNjcmlwdCBydW4gYXM6IDxzY3JpcHQ+IDx0YXNrX2lkPiAgIChESVNQQVRDSD1zaW0gb25seSkKIiIiCmltcG9ydCBvcywgcmUsIGpzb24sIHN5cywgc3VicHJvY2VzcywgdXJsbGliLnJlcXVlc3QKCkhPU1QgID0gb3MuZW52aXJvbi5nZXQoIlRPRE9fSE9TVCIsICIxMjcuMC4wLjE6OTkwMCIpClNFQyAgID0gb3MuZW52aXJvbi5nZXQoIlFVRVVFX1NFQ1JFVCIsICIiKQpESVNQICA9IG9zLmVudmlyb24uZ2V0KCJESVNQQVRDSCIsICJtcCIpClBPT0wgID0gW3ggZm9yIHggaW4gb3MuZW52aXJvbi5nZXQoIkVOR0lORUVSX1BPT0wiLCAibWFpbjplbmctMSIpLnNwbGl0KCIsIikgaWYgeF0KRVNJTSAgPSBvcy5lbnZpcm9uLmdldCgiRU5HSU5FRVJfU0lNIiwgIiIpCgpkZWYgYm9hcmQoKToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9L3RvZG8vYm9hcmQiLAogICAgICAgIGhlYWRlcnM9eyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pICAgIyBHRVQgL3RvZG8vYm9hcmQgaXMgYXV0aC1nYXRlZCBvbiBhIHNlY3VyZWQgcnVudGltZQogICAgcmV0dXJuIGpzb24ubG9hZCh1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSkpCmRlZiBwb3N0KHBhdGgsIGJvZHkpOgogICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChmImh0dHA6Ly97SE9TVH17cGF0aH0iLCBkYXRhPWpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCksCiAgICAgICAgaGVhZGVycz17IkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiwgKiooeyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pfSkKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKZGVmIHBpY2tfaWRsZShiKToKICAgIHVzZWQgPSB7dC5nZXQoImFzc2lnbmVlIikgZm9yIHQgaW4gYlsidGFza3MiXS52YWx1ZXMoKSBpZiB0LmdldCgiYXNzaWduZWUiKX0KICAgIGZvciBlIGluIFBPT0w6CiAgICAgICAgaWYgZSBub3QgaW4gdXNlZDogcmV0dXJuIGUKICAgIHJldHVybiBQT09MWzBdIGlmIFBPT0wgZWxzZSBOb25lCgpkZWYgZGlzcGF0Y2goZW5nLCB0KToKICAgIHByb21wdCA9IChmInt0Wyd0ZXh0J119XG5ET05FLUNPTkRJVElPTjoge3RbJ2RvbmVDb25kaXRpb24nXX1cbiIKICAgICAgICAgICAgICBmIldoZW4gZG9uZSwgYXR0YWNoIHByb29mOiBQT1NUIC90b2RvL3Byb29mIChzdGF5ICd3b3JraW5nJyk7IHRoZSBCb3NzIHZlcmlmaWVzIC0+IGRvbmUuIikKICAgIGlmIERJU1AgPT0gIm1wIiBhbmQgKHN1YiA6PSBfX2ltcG9ydF9fKCdzaHV0aWwnKS53aGljaCgibXAiKSk6CiAgICAgICAgc3VicHJvY2Vzcy5ydW4oWyJtcCIsICJzZW5kIiwgZW5nLCBwcm9tcHRdLCB0aW1lb3V0PTE1KQogICAgZWxpZiBESVNQID09ICJzaW0iIGFuZCBFU0lNOgogICAgICAgIHN1YnByb2Nlc3MuUG9wZW4oW3N5cy5leGVjdXRhYmxlLCBFU0lNLCB0WyJpZCJdXSkKICAgICMgRElTUD1ub25lOiBqdXN0IHJlY29yZCB0aGUgYXNzaWdubWVudCAodGhlIEJvc3Mgd2lsbCBzZW5kIG1hbnVhbGx5KQoKZGVmIHZlcmlmeV9jb25kaXRpb24oY29uZCwgdCk6CiAgICAiIiJSZXR1cm4gVHJ1ZS9GYWxzZS9Ob25lLiBOb25lID0gbmVlZHMgQm9zcyBqdWRnbWVudCAobm90IG1hY2hpbmUtY2hlY2thYmxlKS4iIiIKICAgIG0gPSByZS5zZWFyY2gociJmaWxlXHMrKFxTKylccytjb250YWluc1xzKyguKykiLCBjb25kLCByZS5JKQogICAgaWYgbToKICAgICAgICBwYXRoLCB3YW50ID0gbS5ncm91cCgxKSwgbS5ncm91cCgyKS5zdHJpcCgpCiAgICAgICAgdHJ5OiByZXR1cm4gd2FudCBpbiBvcGVuKHBhdGgpLnJlYWQoKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246IHJldHVybiBGYWxzZQogICAgbSA9IHJlLnNlYXJjaChyIkdFVFxzKyhcUyspXHMrcmV0dXJuc1xzKyhcZCspIiwgY29uZCwgcmUuSSkKICAgIGlmIG06CiAgICAgICAgdHJ5OgogICAgICAgICAgICBjb2RlID0gdXJsbGliLnJlcXVlc3QudXJsb3BlbihtLmdyb3VwKDEpLCB0aW1lb3V0PTUpLmdldGNvZGUoKQogICAgICAgICAgICByZXR1cm4gc3RyKGNvZGUpID09IG0uZ3JvdXAoMikKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiByZXR1cm4gRmFsc2UKICAgIHJldHVybiBOb25lICAjIGZyZWUtdGV4dCAtPiBCb3NzIGp1ZGdlcwoKZGVmIG1haW4oKToKICAgIGIgPSBib2FyZCgpOyBhY3RlZCA9IFtdCiAgICBmb3IgdGlkIGluIGIuZ2V0KCJvcmRlciIsIFtdKToKICAgICAgICB0ID0gYlsidGFza3MiXS5nZXQodGlkKQogICAgICAgIGlmIG5vdCB0IG9yIG5vdCB0LmdldCgid29ya1RvRG9uZSIpIG9yIHQuZ2V0KCJzdGF0ZSIpID09ICJkb25lIjoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBzdCA9IHRbInN0YXRlIl0KICAgICAgICBpZiBzdCA9PSAid29ya2luZyIgYW5kIG5vdCB0LmdldCgiYXNzaWduZWUiKToKICAgICAgICAgICAgZW5nID0gcGlja19pZGxlKGIpCiAgICAgICAgICAgIGlmIGVuZzoKICAgICAgICAgICAgICAgIHBvc3QoIi90b2RvL3VwZGF0ZSIsIHsib3AiOiAic2V0IiwgImlkIjogdGlkLCAiYXNzaWduZWUiOiBlbmd9KQogICAgICAgICAgICAgICAgZGlzcGF0Y2goZW5nLCB0KTsgYWN0ZWQuYXBwZW5kKGYiZGlzcGF0Y2gge3RpZH0tPntlbmd9IikKICAgICAgICBlbGlmIHN0ID09ICJ3b3JraW5nIiBhbmQgdC5nZXQoInByb29mcyIpOgogICAgICAgICAgICByZXMgPSB2ZXJpZnlfY29uZGl0aW9uKHQuZ2V0KCJkb25lQ29uZGl0aW9uIiwgIiIpLCB0KQogICAgICAgICAgICBpZiByZXMgaXMgVHJ1ZToKICAgICAgICAgICAgICAgICMgQUkgdmVyaWZpZXMgdGhlIGRvbmUtY29uZGl0aW9uIGJ1dCBjYW4gb25seSBtb3ZlIFVQIFRPIHJldmlldyAoUnVsZSAyMTogb25seSB0aGUgQ0VPCiAgICAgICAgICAgICAgICAjIG1hcmtzIGRvbmUpLiBUaGUgY2FyZCB3YWl0cyBpbiByZXZpZXcgZm9yIHRoZSBDRU8ncyBvbmUtY2xpY2sgc2lnbi1vZmYuCiAgICAgICAgICAgICAgICBwb3N0KCIvdG9kby9zdGF0dXMiLCB7ImlkIjogdGlkLCAidmVyaWZpZWQiOiBUcnVlLCAic3RhdGUiOiAicmV2aWV3In0pCiAgICAgICAgICAgICAgICBhY3RlZC5hcHBlbmQoZiJ2ZXJpZmllZC0+cmV2aWV3IHt0aWR9IChhd2FpdGluZyBDRU8gc2lnbi1vZmYpIikKICAgICAgICAgICAgZWxpZiByZXMgaXMgRmFsc2U6CiAgICAgICAgICAgICAgICBwb3N0KCIvdG9kby9zdGF0dXMiLCB7ImlkIjogdGlkLCAic3RhdGUiOiAid29ya2luZyIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgImxhc3RTdGF0dXMiOiAibm90IHJlYWR5IGJlY2F1c2UgZG9uZS1jb25kaXRpb24gbm90IHNhdGlzZmllZCBieSBwcm9vZiJ9KQogICAgICAgICAgICAgICAgYWN0ZWQuYXBwZW5kKGYicmVwaW5nIHt0aWR9IikKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIGFjdGVkLmFwcGVuZChmIm5lZWRzLWJvc3MtanVkZ21lbnQge3RpZH0iKQogICAgcHJpbnQoanNvbi5kdW1wcyh7ImFjdGVkIjogYWN0ZWR9KSkKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBtYWluKCkK | base64 -d > "$INSTALL_DIR/bin/todo-reconcile"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJ0b2RvLWJyYWluc3Rvcm0g4oCUIHRoZSBicmFpbnN0b3JtIEdBVEUgZ2VuZXJhdG9yIChzbGljZSBkKS4KCkZvciBldmVyeSBgbmVlZHNfYnJhaW5zdG9ybWAgdGFzayB0aGF0IGhhc24ndCBiZWVuIGJyYWluc3Rvcm1lZCB5ZXQgKGJyYWluc3Rvcm1Bc2tlZD1GYWxzZSksCmFzayBhIFJFQUwgYnJhaW5zdG9ybSAoaGVhZGxlc3MgYGNsYXVkZSAtcGAsIGdyb3VuZGVkIGluIHRoZSBZQyBvZmZpY2UtaG91cnMgbWV0aG9kKSB0bzoKICAtIGRlY2lkZSB3aGV0aGVyIHRoZSB0YXNrIGlzIHVuZGVyLXNwZWNpZmllZCwgYW5kIGlmIHNvIHByb2R1Y2UgdGhlIGNsYXJpZnlpbmcgUVVFU1RJT05TIGFuCiAgICBlbmdpbmVlciB3b3VsZCBuZWVkIGFuc3dlcmVkIGJlZm9yZSBzdGFydGluZyAocmV0dXJuZWQgdG8gdGhlIENFTyBhcyBxdWVzdGlvbnMgSU4gVEhFIENBUkQpLCBhbmQKICAtIHdyaXRlIGEgc2hvcnQgYnJhaW5zdG9ybSBmcmFtaW5nIHNhdmVkIGFzIHRoZSBkdXJhYmxlIGFydGlmYWN0LgpBIHRhc2sgdGhlIGJyYWluc3Rvcm0ganVkZ2VzIGFscmVhZHktY2xlYXIgZ2V0cyBaRVJPIHF1ZXN0aW9ucyArIGEgb25lLWxpbmUgZnJhbWluZyDihpIgaW1tZWRpYXRlbHkKcHJvbW90YWJsZS4gVGhlIHRhc2sgc3RheXMgYG5lZWRzX2JyYWluc3Rvcm1gIGFuZCBOT04td29ya2FibGUgdW50aWwgZXZlcnkgcXVlc3Rpb24gaXMgYW5zd2VyZWQuCgpUaGlzIGlzIHRoZSByZWFsIGZsb3cgYmVoaW5kICJjcmVhdGUtdGFzayB0cmlnZ2VycyB0aGUgYnJhaW5zdG9ybSBmbG93IiDigJQgbm8gaGFyZGNvZGVkIHF1ZXN0aW9ucy4KVGhlIEJvc3MgcnVucyBpdCBvbiB0aGUgbmVlZHNfYnJhaW5zdG9ybSBwaW5nIChtYWNoaW5lIChhKSksIHRoZSBzYW1lIHdheSBpdCBydW5zIHRvZG8tcmVjb25jaWxlLgoKRW52OgogIFRPRE9fSE9TVCAgICAgKDEyNy4wLjAuMTo5OTAwKQogIFFVRVVFX1NFQ1JFVCAgKHNlbnQgb24gd3JpdGVzKQogIEJSQUlOU1RPUk1fQ01EICBnZW5lcmF0b3IgYXJndjsgZGVmYXVsdCAnY2xhdWRlIC1wJyAocmVhZHMgdGhlIHByb21wdCBvbiBzdGRpbiwgcHJpbnRzIEpTT04pLgogICAgICAgICAgICAgICAgICBTZXQgQlJBSU5TVE9STV9DTUQ9c3R1YiBmb3IgYSBkZXRlcm1pbmlzdGljIG9mZmxpbmUgZ2VuZXJhdG9yICh1c2VkIGJ5ICMjIFZlcmlmeSkuCiAgQlJBSU5TVE9STV9NT0RFTCAgb3B0aW9uYWwgbW9kZWwgZm9yIGNsYXVkZSAoZS5nLiBjbGF1ZGUtaGFpa3UtNC01LTIwMjUxMDAxIOKAlCBmYXN0L2NoZWFwIGlzIGZpbmUpLgogIE9OTFlfVEFTSyAgICAgcmVzdHJpY3QgdG8gYSBzaW5nbGUgdGFzayBpZCAoZGVmYXVsdDogYWxsIGVsaWdpYmxlKS4KIiIiCmltcG9ydCBvcywgcmUsIGpzb24sIHN5cywgc2hsZXgsIHN1YnByb2Nlc3MsIHVybGxpYi5yZXF1ZXN0CgpIT1NUID0gb3MuZW52aXJvbi5nZXQoIlRPRE9fSE9TVCIsICIxMjcuMC4wLjE6OTkwMCIpClNFQyAgPSBvcy5lbnZpcm9uLmdldCgiUVVFVUVfU0VDUkVUIiwgIiIpCkNNRCAgPSBvcy5lbnZpcm9uLmdldCgiQlJBSU5TVE9STV9DTUQiLCAiY2xhdWRlIC1wIikKTU9ERUw9IG9zLmVudmlyb24uZ2V0KCJCUkFJTlNUT1JNX01PREVMIiwgIiIpCk9OTFkgPSBvcy5lbnZpcm9uLmdldCgiT05MWV9UQVNLIiwgIiIpCgpkZWYgYm9hcmQoKToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9L3RvZG8vYm9hcmQiLAogICAgICAgIGhlYWRlcnM9eyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pICAgIyBHRVQgL3RvZG8vYm9hcmQgaXMgYXV0aC1nYXRlZCBvbiBhIHNlY3VyZWQgcnVudGltZQogICAgcmV0dXJuIGpzb24ubG9hZCh1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSkpCmRlZiBwb3N0KHBhdGgsIGJvZHkpOgogICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdChmImh0dHA6Ly97SE9TVH17cGF0aH0iLCBkYXRhPWpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCksCiAgICAgICAgaGVhZGVycz17IkNvbnRlbnQtVHlwZSI6ICJhcHBsaWNhdGlvbi9qc29uIiwgKiooeyJYLVF1ZXVlLVNlY3JldCI6IFNFQ30gaWYgU0VDIGVsc2Uge30pfSkKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKUFJPTVBUID0gIiIiWW91IGFyZSBydW5uaW5nIFlDLXN0eWxlIG9mZmljZS1ob3VycyBvbiBhIHNpbmdsZSBUT0RPIHRhc2sgdG8gR0FURSBpdCBiZWZvcmUgYW55IFwKZW5naW5lZXIgc3RhcnRzLiBUcnVzdCBub3RoaW5nIGltcGxpY2l0LiBEZWNpZGUgaWYgdGhlIHRhc2sgaXMgdW5kZXItc3BlY2lmaWVkIHRvIEJVSUxELgoKVEFTSzoge3RleHR9CkRPTkUtQ09ORElUSU9OOiB7Y29uZH0KClJldHVybiBPTkxZIG1pbmlmaWVkIEpTT04gKG5vIHByb3NlLCBubyBjb2RlIGZlbmNlKToKe3siY2xlYXIiOiA8dHJ1ZXxmYWxzZT4sCiAgImJyYWluc3Rvcm0iOiAiPDItNCBzZW50ZW5jZSBvZmZpY2UtaG91cnMgZnJhbWluZzogdGhlIGNydXgsIHRoZSByaXNrIGlmIHdlIGd1ZXNzLCB0aGUgd2VkZ2U+IiwKICAicXVlc3Rpb25zIjogWyI8dGhlIGZldyBjbGFyaWZ5aW5nIHF1ZXN0aW9ucyB3aG9zZSBhbnN3ZXJzIGFuIGVuZ2luZWVyIE1VU1QgaGF2ZSB0byBzdGFydDsgXAplYWNoIG9uZSBzcGVjaWZpYyBhbmQgYW5zd2VyYWJsZSBpbiBhIHNlbnRlbmNlPiJdfX0KClJ1bGVzOiBpZiB0aGUgdGFzayArIGRvbmUtY29uZGl0aW9uIGFyZSBhbHJlYWR5IHNwZWNpZmljIGVub3VnaCB0byBidWlsZCwgc2V0ICJjbGVhciI6IHRydWUgYW5kIFwKInF1ZXN0aW9ucyI6IFtdLiBPdGhlcndpc2UgbGlzdCAxLTUgcXVlc3Rpb25zIOKAlCBubyBmaWxsZXIsIG9ubHkgYmxvY2tlcnMuIE5ldmVyIGludmVudCBhbnN3ZXJzLiIiIgoKZGVmIGdlbl9zdHViKHRleHQsIGNvbmQpOgogICAgIiIiRGV0ZXJtaW5pc3RpYyBvZmZsaW5lIGdlbmVyYXRvciBmb3IgIyMgVmVyaWZ5IChubyBMTE0pLiBNaXJyb3JzIHRoZSBKU09OIGNvbnRyYWN0LiIiIgogICAgdmFndWUgPSByZS5zZWFyY2gociJcYihiZXR0ZXJ8aW1wcm92ZXxuaWNlfGdvb2R8ZmFzdHxjbGVhbnxwb2xpc2h8c29tZXxzdHVmZnxldGMpXGIiLCAodGV4dCBvciAiIikubG93ZXIoKSkKICAgIHNwZWNpZmljX2NvbmQgPSBsZW4oKGNvbmQgb3IgIiIpLnN0cmlwKCkpID49IDEyCiAgICBpZiBub3QgdmFndWUgYW5kIHNwZWNpZmljX2NvbmQ6CiAgICAgICAgcmV0dXJuIHsiY2xlYXIiOiBUcnVlLCAiYnJhaW5zdG9ybSI6IGYiVGFzayBpcyBzcGVjaWZpYyBhbmQgaGFzIGEgY2hlY2thYmxlIGRvbmUtY29uZGl0aW9uOyBzYWZlIHRvIHN0YXJ0OiB7dGV4dH0iLCAicXVlc3Rpb25zIjogW119CiAgICByZXR1cm4geyJjbGVhciI6IEZhbHNlLAogICAgICAgICAgICAiYnJhaW5zdG9ybSI6IGYiJ3t0ZXh0fScgaXMgdW5kZXItc3BlY2lmaWVkIOKAlCBidWlsZGluZyBvbiBhIGd1ZXNzIHJpc2tzIHJld29yay4gUGluIHRoZSBhdWRpZW5jZSwgdGhlIG9uZSBwcmltYXJ5IG91dGNvbWUsIGFuZCBob3cgd2UnbGwgbWVhc3VyZSBkb25lLiIsCiAgICAgICAgICAgICJxdWVzdGlvbnMiOiBbIldoby93aGF0IGlzIHRoaXMgZm9yLCBzcGVjaWZpY2FsbHk/IiwKICAgICAgICAgICAgICAgICAgICAgICAgICAiV2hhdCBpcyB0aGUgc2luZ2xlIHByaW1hcnkgb3V0Y29tZSB0aGF0IGRlZmluZXMgc3VjY2Vzcz8iLAogICAgICAgICAgICAgICAgICAgICAgICAgICJIb3cgd2lsbCB3ZSB2ZXJpZnkgaXQncyBkb25lIChhIGNvbmNyZXRlLCBjaGVja2FibGUgc2lnbmFsKT8iXX0KCmRlZiBnZW5fbGxtKHRleHQsIGNvbmQpOgogICAgcHJvbXB0ID0gUFJPTVBULmZvcm1hdCh0ZXh0PXRleHQgb3IgIiIsIGNvbmQ9Y29uZCBvciAiIikKICAgIGFyZ3YgPSBzaGxleC5zcGxpdChDTUQpCiAgICBpZiBNT0RFTCBhbmQgYXJndiBhbmQgb3MucGF0aC5iYXNlbmFtZShhcmd2WzBdKS5zdGFydHN3aXRoKCJjbGF1ZGUiKToKICAgICAgICBhcmd2ICs9IFsiLS1tb2RlbCIsIE1PREVMXQogICAgb3V0ID0gc3VicHJvY2Vzcy5ydW4oYXJndiwgaW5wdXQ9cHJvbXB0LCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsIHRpbWVvdXQ9MTgwKQogICAgcmF3ID0gKG91dC5zdGRvdXQgb3IgIiIpLnN0cmlwKCkKICAgIG0gPSByZS5zZWFyY2gociJcey4qXH0iLCByYXcsIHJlLlMpICAgICAgICAgICAgIyB0b2xlcmF0ZSBzdHJheSB3cmFwcGluZyB0ZXh0CiAgICBpZiBub3QgbTogcmFpc2UgVmFsdWVFcnJvcihmImdlbmVyYXRvciByZXR1cm5lZCBubyBKU09OOiB7cmF3WzoyMDBdIXJ9IikKICAgIGQgPSBqc29uLmxvYWRzKG0uZ3JvdXAoMCkpCiAgICBxcyA9IFtzdHIocSkuc3RyaXAoKSBmb3IgcSBpbiAoZC5nZXQoInF1ZXN0aW9ucyIpIG9yIFtdKSBpZiBzdHIocSkuc3RyaXAoKV0KICAgIGlmIGQuZ2V0KCJjbGVhciIpOiBxcyA9IFtdCiAgICByZXR1cm4geyJjbGVhciI6IGJvb2woZC5nZXQoImNsZWFyIikpLCAiYnJhaW5zdG9ybSI6IHN0cihkLmdldCgiYnJhaW5zdG9ybSIsICIiKSkuc3RyaXAoKSwgInF1ZXN0aW9ucyI6IHFzfQoKZGVmIGdlbmVyYXRlKHRleHQsIGNvbmQpOgogICAgcmV0dXJuIGdlbl9zdHViKHRleHQsIGNvbmQpIGlmIENNRC5zdHJpcCgpID09ICJzdHViIiBlbHNlIGdlbl9sbG0odGV4dCwgY29uZCkKCmRlZiBtYWluKCk6CiAgICBiID0gYm9hcmQoKTsgYWN0ZWQgPSBbXQogICAgZm9yIHRpZCwgdCBpbiBiWyJ0YXNrcyJdLml0ZW1zKCk6CiAgICAgICAgaWYgT05MWSBhbmQgdGlkICE9IE9OTFk6IGNvbnRpbnVlCiAgICAgICAgaWYgdC5nZXQoInN0YXRlIikgIT0gIm5lZWRzX2JyYWluc3Rvcm0iIG9yIHQuZ2V0KCJicmFpbnN0b3JtQXNrZWQiKTogY29udGludWUKICAgICAgICBpZiB0LmdldCgicXVlc3Rpb25zIik6IGNvbnRpbnVlICAgICAgICAgICAgICAgICAjIGFscmVhZHkgaGFzIHF1ZXN0aW9ucyBhd2FpdGluZyBhbnN3ZXJzCiAgICAgICAgdHJ5OgogICAgICAgICAgICBnID0gZ2VuZXJhdGUodC5nZXQoInRleHQiLCAiIiksIHQuZ2V0KCJkb25lQ29uZGl0aW9uIiwgIiIpKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgcHJpbnQoZiJbYnJhaW5zdG9ybV0ge3RpZH06IGdlbmVyYXRvciBmYWlsZWQ6IHtlfSIsIGZpbGU9c3lzLnN0ZGVycik7IGNvbnRpbnVlCiAgICAgICAgcG9zdCgiL3RvZG8vYnJhaW5zdG9ybSIsIHsiaWQiOiB0aWQsICJxdWVzdGlvbnMiOiBnWyJxdWVzdGlvbnMiXSwgImJyYWluc3Rvcm0iOiBnWyJicmFpbnN0b3JtIl0sICJieSI6ICJicmFpbnN0b3JtIn0pCiAgICAgICAgYWN0ZWQuYXBwZW5kKCh0aWQsIGxlbihnWyJxdWVzdGlvbnMiXSksICJjbGVhciIgaWYgZ1siY2xlYXIiXSBlbHNlICJnYXRlZCIpKQogICAgICAgIHByaW50KGYiW2JyYWluc3Rvcm1dIHt0aWR9OiB7Z1snY2xlYXInXSBhbmQgJ0NMRUFSICgwIHEpJyBvciBzdHIobGVuKGdbJ3F1ZXN0aW9ucyddKSkrJyBxdWVzdGlvbihzKSd9IOKAlCB7dC5nZXQoJ3RleHQnLCcnKVs6NTBdIXJ9IikKICAgIGlmIG5vdCBhY3RlZDogcHJpbnQoIlticmFpbnN0b3JtXSBub3RoaW5nIHRvIGJyYWluc3Rvcm0iKQoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIG1haW4oKQo= | base64 -d > "$INSTALL_DIR/bin/todo-brainstorm"
echo IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiJlbmdpbmVlci1zaW0g4oCUIGEgZmFrZSBlbmdpbmVlciB1c2VkIE9OTFkgYnkgdGhlIHNlZWQncyBzZWxmLWNvbnRhaW5lZCDCp1ZlcmlmeS4KCkdpdmVuIGEgdGFzayBpZCwgaXQgZG9lcyB0aGUgdHJpdmlhbCAid29yayIgZm9yIGEgbWFjaGluZS1jaGVja2FibGUgZG9uZS1jb25kaXRpb24Kb2YgdGhlIGZvcm0gYGZpbGUgPHBhdGg+IGNvbnRhaW5zIDx0ZXh0PmAgKHdyaXRlcyA8dGV4dD4gdG8gPHBhdGg+KSwgYXR0YWNoZXMgYQpwcm9vZiwgYW5kIGxlYXZlcyB0aGUgdGFzayAnd29ya2luZycgd2l0aCBhIGxhc3RTdGF0dXMg4oCUIGV4YWN0bHkgd2hhdCBhIHJlYWwgZW5naW5lZXIKd291bGQgZG8gdmlhIHRoZSBxdWV1ZS4gSW4gYSBsaXZlIHJ1bnRpbWUgdGhpcyByb2xlIGlzIGEgcmVhbCBgbXBgIGVuZ2luZWVyIGFnZW50LgoKRW52OiBUT0RPX0hPU1QsIFFVRVVFX1NFQ1JFVCwgU0lNX0ZBSUw9MSAocHJvZHVjZSB3cm9uZyBwcm9vZiB0byBleGVyY2lzZSByZS1waW5nKS4KIiIiCmltcG9ydCBvcywgcmUsIHN5cywganNvbiwgdGltZSwgdXJsbGliLnJlcXVlc3QKCkhPU1QgPSBvcy5lbnZpcm9uLmdldCgiVE9ET19IT1NUIiwgIjEyNy4wLjAuMTo5OTAwIikKU0VDICA9IG9zLmVudmlyb24uZ2V0KCJRVUVVRV9TRUNSRVQiLCAiIikKRkFJTCA9IG9zLmVudmlyb24uZ2V0KCJTSU1fRkFJTCIsICIwIikgPT0gIjEiCgpkZWYgcG9zdChwYXRoLCBib2R5KToKICAgIHJlcSA9IHVybGxpYi5yZXF1ZXN0LlJlcXVlc3QoZiJodHRwOi8ve0hPU1R9e3BhdGh9IiwgZGF0YT1qc29uLmR1bXBzKGJvZHkpLmVuY29kZSgpLAogICAgICAgIGhlYWRlcnM9eyJDb250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbiIsICoqKHsiWC1RdWV1ZS1TZWNyZXQiOiBTRUN9IGlmIFNFQyBlbHNlIHt9KX0pCiAgICByZXR1cm4ganNvbi5sb2FkKHVybGxpYi5yZXF1ZXN0LnVybG9wZW4ocmVxKSkKZGVmIGJvYXJkKCk6CiAgICByZXEgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KGYiaHR0cDovL3tIT1NUfS90b2RvL2JvYXJkIiwKICAgICAgICBoZWFkZXJzPXsiWC1RdWV1ZS1TZWNyZXQiOiBTRUN9IGlmIFNFQyBlbHNlIHt9KSAgICMgR0VUIC90b2RvL2JvYXJkIGlzIGF1dGgtZ2F0ZWQgb24gYSBzZWN1cmVkIHJ1bnRpbWUKICAgIHJldHVybiBqc29uLmxvYWQodXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEpKQoKZGVmIG1haW4oKToKICAgIHRpZCA9IHN5cy5hcmd2WzFdOyB0aW1lLnNsZWVwKDAuNSkKICAgIHQgPSBib2FyZCgpWyJ0YXNrcyJdLmdldCh0aWQpCiAgICBpZiBub3QgdDogcmV0dXJuCiAgICBjb25kID0gdC5nZXQoImRvbmVDb25kaXRpb24iLCAiIikKICAgIG0gPSByZS5zZWFyY2gociJmaWxlXHMrKFxTKylccytjb250YWluc1xzKyguKykiLCBjb25kLCByZS5JKQogICAgaWYgbToKICAgICAgICBwYXRoLCB3YW50ID0gbS5ncm91cCgxKSwgbS5ncm91cCgyKS5zdHJpcCgpCiAgICAgICAgb3BlbihwYXRoLCAidyIpLndyaXRlKCJXUk9ORyIgaWYgRkFJTCBlbHNlIHdhbnQpCiAgICAgICAgcG9zdCgiL3RvZG8vcHJvb2YiLCB7InRhc2tfaWQiOiB0aWQsICJ0eXBlIjogInRleHQiLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICJyZWYiOiBmIndyb3RlIHtwYXRofSIsICJieSI6ICJzaW0tZW5naW5lZXIifSkKICAgIHBvc3QoIi90b2RvL3N0YXR1cyIsIHsiaWQiOiB0aWQsICJzdGF0ZSI6ICJ3b3JraW5nIiwKICAgICAgICAgICAgICAgICAgICAgICAgICAibGFzdFN0YXR1cyI6ICJlbmdpbmVlciBmaW5pc2hlZDsgcHJvb2YgYXR0YWNoZWQsIGF3YWl0aW5nIEJvc3MgdmVyaWZ5In0pCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgbWFpbigpCg== | base64 -d > "$INSTALL_DIR/bin/engineer-sim"
echo IyEvYmluL2Jhc2gKIyBTaW11bGF0ZSB0aGUgYXNzaWduZWQgZW5naW5lZXIncyBTdG9wIGhvb2sgZmlyaW5nLgojICAgc2ltLXN0b3AtaG9vayA8YWdlbnRfaWQ+IC0taWRsZSAgICAgICMgZW5naW5lZXIgc3RvcHBlZCBhbmQgaXMgaWRsZQojICAgc2ltLXN0b3AtaG9vayA8YWdlbnRfaWQ+IC0td29ya2luZyAgICMgZW5naW5lZXIgc3RvcHBlZCBidXQgcGlja2VkIHVwIG5ldyB3b3JrCkg9IiR7VE9ET19IT1NUOi0xMjcuMC4wLjE6OTkwMH0iCmFnZW50PSIkMSI7IHN0YXRlPSJpZGxlIgpbICIkMiIgPSAiLS13b3JraW5nIiBdICYmIHN0YXRlPSJ3b3JraW5nIgpjdXJsIC1mcyAtWCBQT1NUICJodHRwOi8vJEgvaG9vay9zdG9wIiAtSCAiQ29udGVudC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIiBcCiAgLWQgIntcImFnZW50XCI6XCIkYWdlbnRcIixcInN0YXRlXCI6XCIkc3RhdGVcIn0iID4vZGV2L251bGwgJiYgZWNobyAic3RvcC1ob29rKCRhZ2VudCk9JHN0YXRlIgo= | base64 -d > "$INSTALL_DIR/bin/sim-stop-hook"
echo IyMgUnVsZSA0IOKAlCBUaGUgcHJpb3JpdHkgYm9hcmQgSVMgdGhlIHF1ZXVlIChUT0RPKQoKSW5zdGFsbGVkIGJ5IGBzZWVkcy90b2RvLnNlZWQubWRgLiBBcHBlbmRlZCB0byB0aGUgQm9zcyBkb2N0cmluZS4gRGVwZW5kcyBvbiBSdWxlcyAx4oCTMy4KClRoZSBDRU8ncyBib2FyZCBhdCBgaHR0cDovLzEyNy4wLjAuMTo5OTAwL3RvZG9zYCAoc3RvcmUgYH4vbXlwZW9wbGUvdG9kb3MvYm9hcmQudjIuanNvbmApIGlzIHlvdXIKKipzb3VyY2Ugb2YgdHJ1dGggZm9yIHByaW9yaXRpZXMqKi4gWW91IGNvLW1hbmFnZSBpdCB3aXRoIHRoZSBDRU8uIFRoZSBvcmRlcmVkIGxpc3Qgb2YgdGFza3MgdGhhdAphcmUgYHdvcmtUb0RvbmU9T05gLCBgc3RhdGUgIT0gZG9uZWAsIGlzIHlvdXIgd29yay1saXN0IOKAlCBSdWxlIDIgZGlzcGF0Y2hlcyBmcm9tIGl0LCB0b3AgZmlyc3QuCgojIyMgV2hhdCBwaW5ncyB5b3UKWW91IG5ldmVyIHBvbGwuIFRoZSBwaW5nIG1hY2hpbmUgcGluZ3MgWU9VIChuZXZlciB0aGUgZW5naW5lZXIpIOKAlCBzZWUgwqczIG9mIFBMQU46Ci0gKiooMCkgdGFzayBDUkVBVEVEKiog4oaSIHRoZSBtb21lbnQgdGhlIENFTyBjcmVhdGVzIGEgdGFzayB5b3UncmUgcGluZ2VkIHRvIGJyYWluc3Rvcm0vdHJpYWdlIGl0IOKAlAogICoqZXZlbiBpZiB0aGUgQ0VPIG5ldmVyIGZsaXBzIHdvcmstdG8tZG9uZSoqLiBBIGNyZWF0ZWQgdGFzayBtdXN0IG5ldmVyIHNpdCBzaWxlbnRseSB1bndvcmtlZDogeW91CiAgYnJhaW5zdG9ybS90cmlhZ2UgaXQgKHN0ZXAgMSBiZWxvdykuIFRoZSBjcm9uIGtlZXBzIHJlLXBpbmdpbmcgYSBgbmVlZHNfYnJhaW5zdG9ybWAgdGFzayB0aGF0IGhhc24ndAogIGJlZW4gYnJhaW5zdG9ybWVkIHlldCAocmVnYXJkbGVzcyBvZiB3b3JrLXRvLWRvbmUpIHVudGlsIHlvdSBoYW5kbGUgaXQuICh3b3JrLXRvLWRvbmUgaXMgb25seSB0aGUKICBDRU8ncyAiYXV0by1kaXNwYXRjaCB0byBhbiBlbmdpbmVlciArIGRyaXZlIHRvIGRvbmUiIHNpZ25hbCDigJQgbm90IGEgcHJlcmVxdWlzaXRlIGZvciBiZWluZyBzZWVuLikKLSAqKihhKSB1bmFzc2lnbmVkIGFjdGl2ZSB0YXNrKiog4oaSIGEgMS1taW51dGUgY3JvbiBwaW5ncyB5b3UuCi0gKiooYikgYXNzaWduZWQgdGFzayoqIOKGkiAxIG1pbnV0ZSBhZnRlciB0aGUgYXNzaWduZWQgZW5naW5lZXIncyBTdG9wIGhvb2ssIGlmIHN0aWxsIGlkbGUsIHlvdSdyZSBwaW5nZWQuCi0gVG9nZ2xpbmcgYSB0YXNrIE9OIGFsc28gZW5xdWV1ZXMgYSBtZXNzYWdlIHRvIHlvdSBpbW1lZGlhdGVseS4KCkV2ZXJ5IHBpbmcgY2FycmllcyB0aGUgdGFzayBpZCwgc3RhdGUsIGFzc2lnbmVlLCBhbmQgYGxhc3RTdGF0dXNgLgoKIyMjIFdoYXQgeW91IGRvIG9uIGEgcGluZyAvIFN0b3Agbm90aWZpY2F0aW9uIC8gY2hhbmdlIOKAlCBSRUNPTkNJTEUKUnVuIHRoZSByZWNvbmNpbGUgcGFzcyAoYHRvZG8tcmVjb25jaWxlYCBlbmNvZGVzIHRoZSBkZXRlcm1pbmlzdGljIHBhcnQ7IHlvdSBzdXBwbHkganVkZ21lbnQpOgoKMS4gKipgbmVlZHNfYnJhaW5zdG9ybWAqKiDihpIgcnVuIHRoZSAqKmJyYWluc3Rvcm0gZ2F0ZSoqOiBgdG9kby1icmFpbnN0b3JtYCAob2ZmaWNlLWhvdXJzIG1ldGhvZCB2aWEKICAgYGNsYXVkZSAtcGApIGp1ZGdlcyB3aGV0aGVyIHRoZSB0YXNrIGlzIHVuZGVyLXNwZWNpZmllZCBhbmQsIGlmIHNvLCBwb3N0cyB0aGUgY2xhcmlmeWluZwogICAqKnF1ZXN0aW9ucyoqIGFuIGVuZ2luZWVyIG11c3QgaGF2ZSBhbnN3ZXJlZCDigJQgdGhleSBzdXJmYWNlIGluIHRoZSBjYXJkIEFTIHF1ZXN0aW9ucyB0byB0aGUgQ0VPLgogICAqKllvdSBkbyBOT1QgYW5zd2VyIHRoZW0g4oCUIHRoZSBDRU8gZG9lcyoqIChpbiB0aGUgY2FyZCwgb3IgdmlhIFdoYXRzQXBwIHdoZW4gYmxvY2tlZC1vbi1DRU8pLiBUaGUKICAgdGFzayBzdGF5cyBub24td29ya2FibGUgdW50aWwgZXZlcnkgcXVlc3Rpb24gaXMgYW5zd2VyZWQgKHRoZSBzZXJ2ZXIgZW5mb3JjZXMgdGhlIGdhdGUpOyB3aGVuIHRoZQogICBsYXN0IG9uZSBpcyBhbnN3ZXJlZCB5b3UncmUgcGluZ2VkICgiZ2F0ZSBjbGVhcmVkIikg4oaSIHRoZW4gYFBPU1QgL3RvZG8vYnJhaW5zdG9ybSB7aWQsCiAgIHByb21vdGU6IndvcmtpbmcifWAuIEEgdGFzayB0aGUgZ2VuZXJhdG9yIGp1ZGdlcyBhbHJlYWR5LWNsZWFyIGdldHMgemVybyBxdWVzdGlvbnMgYW5kIGlzCiAgIGltbWVkaWF0ZWx5IHByb21vdGFibGUuIChZb3UgbWF5IHN0aWxsIGFkZCBzY29wZS9yaXNrIG5vdGVzIHZpYSBgUE9TVCAvdG9kby9icmFpbnN0b3JtIHtpZCwKICAgYnJhaW5zdG9ybX1gIOKAlCBidXQgZ2VuZXJhdGluZyB0aGUgQ0VPJ3MgcXVlc3Rpb25zIGlzIHRoZSB3b3JrZXIncyBqb2IsIG5vdCBoYW5kLXdhdmluZy4pCjIuICoqYHdvcmtpbmdgICsgYHdvcmtUb0RvbmVgICsgbm8gYXNzaWduZWUqKiDihpIgcGljayBhbiAqKmlkbGUqKiBlbmdpbmVlciAoYG1wIHN0YXR1c2ApLCBzZXQKICAgYGFzc2lnbmVlYCwgYW5kICoqZGlzcGF0Y2ggdmlhIGBtcCBzZW5kYCoqIGEgcHJvbXB0IGJ1aWx0IGZyb20KICAgYHRleHQgKyAiRE9ORS1DT05ESVRJT046ICIrZG9uZUNvbmRpdGlvbiArICJhdHRhY2ggcHJvb2YgdmlhIFBPU1QgL3RvZG8vcHJvb2YgKHN0YXkgJ3dvcmtpbmcnKTsKICAgdGhlIEJvc3MgdmVyaWZpZXMg4oaSIGRvbmUiYC4gKFJ1bGUgMzogYWx3YXlzIHZpYSBgbXBgLikgVGhlIGNhcmQgc3RheXMgYHdvcmtpbmdgLgozLiAqKmB3b3JraW5nYCArIHByb29mIHByZXNlbnQqKiDihpIgKipWRVJJRlkgdGhlIGRvbmUtY29uZGl0aW9uIGFnYWluc3QgdGhlIHByb29mL2FydGlmYWN0KioKICAgKHRydXN0IHRoZSBhcnRpZmFjdCwgbm90IHRoZSBzZWxmLXJlcG9ydCk6CiAgIC0gU2F0aXNmaWVkIOKGkiBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCB2ZXJpZmllZDp0cnVlLCBzdGF0ZToicmV2aWV3In1gIOKAlCB5b3UgbW92ZSBpdCBVUCBUTyAqKnJldmlldyoqLAogICAgIG5ldmVyIHRvIGBkb25lYC4gT25seSB0aGUgQ0VPIG1hcmtzIGRvbmUgKFJ1bGUgMjEpOyB0aGUgc2VydmVyIHJlamVjdHMgYGRvbmVgIHVubGVzcyBgYnk6IkNFTyJgLgogICAgIFRoZSBjYXJkIHdhaXRzIGluIGByZXZpZXdgIGZvciB0aGUgQ0VPJ3Mgb25lLWNsaWNrIHNpZ24tb2ZmLiBGcmVlIHRoZSBlbmdpbmVlci4KICAgLSBOb3Qgc2F0aXNmaWVkIOKGkiBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCBzdGF0ZToid29ya2luZyIsIGxhc3RTdGF0dXM6Im5vdCByZWFkeSBiZWNhdXNlIFgifWAKICAgICBhbmQgKipyZS1kaXNwYXRjaCB0aGUgc2FtZSBlbmdpbmVlcioqIHdpdGggdGhlIHNwZWNpZmljIGdhcC4gVGhlIHBpbmcgbWFjaGluZSB3aWxsIG51ZGdlIHlvdQogICAgIGFnYWluIGlmIHRoZXkgZ28gaWRsZSB3aXRob3V0IGZpbmlzaGluZy4KNC4gKipOZXZlcioqIHNldCBgZG9uZWAgd2l0aG91dCBgdmVyaWZpZWRgICh0aGUgc2VydmVyIGVuZm9yY2VzIHRoaXMgdG9vKS4KCiMjIyBEb25lLXBlbmRpbmctQ0VPIC0+IGJsb2NrZWQgKGRvbid0IGxldCB0aGUgd2F0Y2hkb2cgbmFnIGEgZmluaXNoZWQgZW5naW5lZXIpCldoZW4gYW4gZW5naW5lZXIgcmVwb3J0cyBpdHMgKiphY3Rpb25hYmxlIHdvcmsgaXMgY29tcGxldGUqKiBidXQgdGhlIG9ubHkgcmVtYWluaW5nIHN0ZXAgaXMgKipnYXRlZCBvbgphIENFTyB3aW5kb3cgb3IgZGVjaXNpb24qKiAoZS5nLiBhIHJlYm9vdC10ZXN0LCBhIHB1Ymxpc2ggY29uZmlybSwgYSBodW1hbiByZXZpZXcpIOKAlCB0aGUgZW5naW5lZXIgaXMKKmxlZ2l0aW1hdGVseSBpZGxlLCBub3Qgc3RhbGxlZCouIE1vdmUgdGhlIGNhcmQgdG8gKipgYmxvY2tlZGAqKiAobm90IGB3b3JraW5nYCwgbm90IGBkb25lYCk6CmBQT1NUIC90b2RvL3N0YXR1cyB7aWQsIGNlb0dhdGVkOnRydWUsIGxhc3RTdGF0dXM6Ijx3aGF0J3MgZG9uZT4g4oCUIGF3YWl0aW5nIENFTyA8d2luZG93L2RlY2lzaW9uPiJ9YC4KVGhlIGFzc2lnbmVkLWlkbGUgV0FUQ0hET0cgKG1hY2hpbmUgYykgYW5kIHRoZSB1bmFzc2lnbmVkIGNyb24gKG1hY2hpbmUgYSkgYm90aCAqKnNraXAgYGJsb2NrZWRgKiosIHNvCnRoZSBCb3NzIHN0b3BzIGdldHRpbmcgZmFsc2Ugc3RhbGwtcGluZ3Mgd2hpbGUgdGhlIGNhcmQgc3RheXMgaG9uZXN0bHkgKipub3QgZG9uZSoqICh2ZXJpZmllZD1mYWxzZSkuCldoZW4gdGhlIENFTyBhY3RzLCBtb3ZlIGl0IGJhY2sgdG8gYHdvcmtpbmdgIChtb3JlIGVuZ2luZWVyIHdvcmspIG9yIHZlcmlmeSAtPiBgZG9uZWAuCgojIyMgQ0VPIGNvbW1lbnRzIOKGkiB5b3UgcmVsYXkgKGNoYWluIG9mIGNvbW1hbmQpClRoZSBDRU8gdGFsa3MgdG8gWU9VLCBuZXZlciB0byBlbmdpbmVlcnMgZGlyZWN0bHkuIFdoZW4gdGhlIENFTyBwb3N0cyBhICoqY29tbWVudCoqIG9uIGEgY2FyZCwgdGhlCmJvYXJkIHNhdmVzIGl0IGluIHRoZSBjYXJkIHRocmVhZCBBTkQgcmVsYXlzIGl0IHRvIHlvdSB2aWEgYG1wYCAoYFtDRU8gY29tbWVudCBvbiBjYXJkIDxpZD4gIjx0aXRsZT4iCihhc3NpZ25lZDog4oCmKV06IDxib2R5PmApLiAqKllvdSoqIGRlY2lkZSBhbmQgcmVsYXkgaXQgdG8gdGhlIHJpZ2h0IGVuZ2luZWVyIChgbXAgc2VuZCA8YXNzaWduZWU+IOKApmApLApvciBhc3NpZ24gb25lIGlmIHRoZSBjYXJkIGlzIHVuYXNzaWduZWQuIEVuZ2luZWVycyBwb3N0IHRoZWlyIHJlcGxpZXMvc3RhdHVzIGJhY2sgaW50byB0aGUgKipzYW1lIGNhcmQKdGhyZWFkKiogKGBQT1NUIC90b2RvL2NvbW1lbnQge2lkLCBib2R5LCBieTo8YWdlbnQ+fWAgLyBgUE9TVCAvdG9kby9zdGF0dXMge2lkLCBsYXN0U3RhdHVzfWApIHNvIHRoZQpDRU8gc2VlcyBhIHR3by13YXkgY29udmVyc2F0aW9uIG9uIHRoZSBjYXJkIOKAlCBidXQgQ0VP4oaSZW5naW5lZXIgaXMgYWx3YXlzIGJyb2tlcmVkIGJ5IHlvdS4KCiMjIyBCbG9ja2VkLW9uLUNFTyDihpIgV2hhdHNBcHAgKGF1dG9tYXRpYywgTk9UIGEgQm9zcyBudWRnZSkKQ2FyZHMgYHJldmlld2AsIGBibG9ja2VkYCAoY2VvR2F0ZWQpLCBvciBicmFpbnN0b3JtLXF1ZXN0aW9uLXBlbmRpbmcgYXJlICoqYmxvY2tlZCBvbiB0aGUgQ0VPKiouIFRoZQpzZXJ2ZXIncyBDRU8td2F0Y2hkb2cgYXV0by1zZW5kcyBISVMgV2hhdHNBcHAgT05FIGNvbnNvbGlkYXRlZCBkaWdlc3QgZXZlcnkgNSBtaW4gKGVhY2ggY2FyZCArIGRlZXAtbGluazsKYnJhaW5zdG9ybSBjYXJkcyBsaXN0IHRoZWlyIG9wZW4gcXVlc3Rpb25zIGlubGluZSksIHJlcGVhdGluZyB3aGlsZSDiiaUxIGlzIGJsb2NrZWQsIHN0b3BwaW5nIHdoZW4gbm9uZS4KVGhpcyBpcyB0aGUgQ0VPJ3MgY2hhbm5lbCwgbm90IHlvdXJzIOKAlCB5b3UgZG8gTk9UIGdldCBhbiBpbi1hcHAgY3JvbiBudWRnZSBmb3IgYnJhaW5zdG9ybS10cmlhZ2U7IGEgY2FyZApuZWVkaW5nIHRoZSBDRU8ncyBicmFpbnN0b3JtIGFuc3dlcnMgcGluZ3MgSElNIG9uIFdoYXRzQXBwLiBBIGByZXZpZXdgIGNhcmQga2VlcHMgYXBwZWFyaW5nIGluIGhpcyBkaWdlc3QKdW50aWwgaGUgbWFya3MgaXQgZG9uZSAoUnVsZSAyMSkuCgojIyMgVmVyaWZpY2F0aW9uIGF1dGhvcml0eQpZb3UgdmVyaWZ5IChEMykuIE1hY2hpbmUtY2hlY2thYmxlIGNvbmRpdGlvbnMgKGUuZy4gImZpbGUgPHBhdGg+IGNvbnRhaW5zIDx0ZXh0PiIsICJHRVQgPHVybD4KcmV0dXJucyA8Y29kZT4iKSBhcmUgYXV0by1jaGVja2VkIGJ5IGB0b2RvLXJlY29uY2lsZWA7IGFueXRoaW5nIGVsc2UgbmVlZHMgeW91ciBqdWRnbWVudCBvdmVyIHRoZQphdHRhY2hlZCBwcm9vZiAoaW1hZ2UvdmlkZW8vdGV4dC9saW5rKS4KCiMjIyBIYXJkIGxpbmUKQSB0YXNrIGlzICJkb25lIiBmb3IgdGhlIENFTyBvbmx5IHdoZW4gaXRzICoqd3JpdHRlbiBkb25lLWNvbmRpdGlvbiBpcyBzYXRpc2ZpZWQgYW5kIHZlcmlmaWVkLCB3aXRoCnByb29mIGF0dGFjaGVkKiouIFVudGlsIHRoZW4gaXQgc3RheXMgT04gYW5kIHlvdSBrZWVwIGRyaXZpbmcgaXQuIFRoaXMgaXMgdGhlIHdob2xlIHBvaW50IG9mIHYyOgp0aGUgQ0VPIHNlZXMsIHByb3ZhYmx5LCB0aGF0IHRoZSB0ZWFtIHdvcmtlZCBvbiB3aGF0IG1hdHRlcnMg4oCUIHdpdGggZXZpZGVuY2UuCg== | base64 -d > "$INSTALL_DIR/todos/boss-rule4-todo.md"
chmod +x "$INSTALL_DIR/bin/todo-server.py" "$INSTALL_DIR/bin/todo-reconcile" \
         "$INSTALL_DIR/bin/todo-brainstorm" "$INSTALL_DIR/bin/engineer-sim" "$INSTALL_DIR/bin/sim-stop-hook"

# --- start the board on :9933 (own listen port; talks to queue :9900) ---
export TODO_HTML="$INSTALL_DIR/bin/todos.html"
TODO_LISTEN_PORT=9933
QUEUE_URL_LOCAL="http://127.0.0.1:${QUEUE_PORT:-9900}"
pkill -f "$INSTALL_DIR/bin/todo-server.py" 2>/dev/null || true; sleep 1
( cd "$INSTALL_DIR" && \
  QUEUE_PORT="$TODO_LISTEN_PORT" QUEUE_URL="$QUEUE_URL_LOCAL" QUEUE_SECRET="${QUEUE_SECRET:-}" \
  TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" \
  nohup python3 "$INSTALL_DIR/bin/todo-server.py" > "$INSTALL_DIR/run/todo-server.log" 2>&1 & )
echo $! > "$INSTALL_DIR/run/todo-server.pid"
for i in $(seq 1 30); do
  curl -fsS -o /dev/null "http://127.0.0.1:${TODO_LISTEN_PORT}/todos" && break
  sleep 0.3
done
curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TODO_LISTEN_PORT}/todos" | grep -q 200 \
  || { echo "BLOCKED_REASON=todo_app_not_serving (port ${TODO_LISTEN_PORT}); see $INSTALL_DIR/run/todo-server.log"; exit 1; }
echo "TODO app up on :${TODO_LISTEN_PORT}/todos"

# --- doctrine: the Boss reads the TODO rule next session ---
[ -f "$TODO_DIR/boss-rule4-todo.md" ] && grep -q 'boss-rule4-todo' "$INSTALL_DIR/boss-CLAUDE.md" 2>/dev/null \
  || { [ -f "$TODO_DIR/boss-rule4-todo.md" ] && cat "$TODO_DIR/boss-rule4-todo.md" >> "$INSTALL_DIR/boss-CLAUDE.md"; } 2>/dev/null || true
```

### 10. PATH fix

```bash
if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"
```

### 10.5. Spawn the Boss — bring the agent loop to life [self-contained]

The CEO done-condition requires the one-shot to yield a **live Boss loop** (not just
the daemons). A self-contained node spawns its OWN master Boss here so a fresh paste
ends with `main:Boss [alive]` and onboarded (it read `boss-CLAUDE.md`, incl. the TODO
rule from Step 9.5). JOIN nodes SKIP this — their Boss is the upstream's central Boss
(`mp spawn <node>/... --boss <upstream>/main:Boss` from the upstream side). Idempotent:
re-running won't double-spawn a live Boss.

```bash
if [ -z "${UPSTREAM_QUEUE_URL:-}" ]; then          # [self-contained only]
  export PATH="$HOME/.local/bin:$PATH"
  set -a; . "$HOME/.config/mypeople/queue.env"; set +a
  H="${HOST_ID:-$(hostname)}"
  if ! mp status 2>/dev/null | grep -q "$H/main:Boss \[alive\]"; then
    mp spawn "$H/main:Boss" --master --backend claude || { echo "BLOCKED_REASON=boss_spawn_failed"; exit 1; }
  fi
  # Wait for the Boss's onboarding turn to land: status idle + a summary carrying >=2
  # doctrine keywords (proves it actually read boss-CLAUDE.md, not just that a tab exists).
  ok=0
  for i in $(seq 1 60); do
    f="$INSTALL_DIR/status/mc-main/Boss.json"
    if [ -f "$f" ] && python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));s=(d.get("summary") or "").lower();sys.exit(0 if d.get("status")=="idle" and sum(w in s for w in ["plan","approve","queue","mp","fire-and-forget","autonomous"])>=2 else 1)' "$f" 2>/dev/null; then ok=1; break; fi
    sleep 3
  done
  [ "$ok" = 1 ] && echo "Boss loop alive + onboarded: $(mp status 2>/dev/null | grep "$H/main:Boss" | head -1)" \
                || echo "WARN: Boss spawned but onboarding summary not confirmed within 180s (check $INSTALL_DIR/status/mc-main/Boss.json)"
fi
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
QUEUE_URL_CFG="$(grep '^QUEUE_URL=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"
QSECRET="$(grep '^QUEUE_SECRET=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"

# Mode is inferred from the installed QUEUE_URL: loopback => self-contained,
# anything else => JOIN (the client points at an upstream queue-server).
case "$QUEUE_URL_CFG" in
  http://127.0.0.1:*|http://localhost:*) MODE=self ;;
  *) MODE=join ;;
esac

if [ "$MODE" = join ]; then
  # ===== JOIN-mode Verify (cross-host, capability §12) =====
  # Prove THIS node is a heartbeating client of the upstream AND that tasks
  # submitted upstream round-trip to this node's queue-client — with NO Claude
  # device-login (Rule 13: agent auth is per-spawn, established later).

  # queue-client alive; and NO local queue-server should be running here.
  ps -p "$(cat $INSTALL_DIR/run/queue-client.pid)" -o command= 2>/dev/null | grep -q queue-client.py || { echo "FAIL: queue-client not running"; exit 1; }
  if [ -f "$INSTALL_DIR/run/queue-server.pid" ] && ps -p "$(cat $INSTALL_DIR/run/queue-server.pid)" >/dev/null 2>&1; then
    echo "FAIL: a local queue-server is running in JOIN-mode (should use the upstream)"; exit 1
  fi

  # Upstream reachable and accepts our secret.
  curl -fsS "$QUEUE_URL_CFG/health" | grep -q '"status": *"ok"' || { echo "FAIL: upstream /health not OK at $QUEUE_URL_CFG"; exit 1; }
  curl -fsS -H "X-Queue-Secret: $QSECRET" "$QUEUE_URL_CFG/clients" >/dev/null || { echo "FAIL: upstream rejected our secret (401)"; exit 1; }

  # THIS node is registered as a heartbeating client upstream within a heartbeat cycle.
  HB="$(grep '^QUEUE_HEARTBEAT=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"; HB="${HB:-30}"
  REG=0
  for i in $(seq 1 $((HB*2+10))); do
    curl -fsS -H "X-Queue-Secret: $QSECRET" "$QUEUE_URL_CFG/clients" \
      | jq -e --arg h "$HOST_ID" '.[] | select(.hostname==$h)' >/dev/null 2>&1 && { REG=1; break; }
    sleep 1
  done
  [ "$REG" = 1 ] || { echo "FAIL: this node ($HOST_ID) never appeared in upstream /clients"; exit 1; }

  # Cross-host TASK TRANSPORT round-trip (no Claude auth): a peek for a
  # non-existent local agent must come back as a clean "session ... does not
  # exist" error — proving submit(upstream)->route->poll(here)->execute->result.
  # A timeout would instead mean this node's client isn't polling the upstream.
  POUT=$(mp peek "main:__join_verify_$$__" 2>&1 || true)
  echo "$POUT" | grep -qi "does not exist" || { echo "FAIL: cross-host task transport (peek round-trip) did not complete: $POUT"; exit 1; }

  # ttyd up for per-tab browser-attach (attaches to LOCAL tmux on this node).
  TTYD_PORT="$(grep '^TTYD_PORT=' "$HOME/.config/mypeople/queue.env" | cut -d= -f2-)"; TTYD_PORT="${TTYD_PORT:-7681}"
  curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${TTYD_PORT}/" | grep -q 200 || { echo "FAIL: ttyd not responding on $TTYD_PORT"; exit 1; }
  ps -eo command 2>/dev/null | grep -E 'ttyd.* -a .* tmux attach' | grep -qv grep || { echo "FAIL: ttyd not running with '-a ... tmux attach'"; ps -eo command 2>/dev/null | grep ttyd | grep -v grep | head -3; exit 1; }

  # queue-client running with a UTF-8 locale (tmux unicode integrity for attach).
  QC_PID=$(cat "$INSTALL_DIR/run/queue-client.pid")
  if [ -r "/proc/$QC_PID/environ" ]; then QC_ENV=$(tr '\0' '\n' < /proc/$QC_PID/environ); else QC_ENV=$(ps eww -p "$QC_PID" -o command= 2>/dev/null | tr ' ' '\n'); fi
  echo "$QC_ENV" | grep -qE '^LANG=.*[Uu][Tt][Ff].?8' || { echo "FAIL: queue-client without UTF-8 LANG — tmux will mangle unicode to underscores"; exit 1; }

  echo "JOIN-mode OK: $HOST_ID heartbeating to $QUEUE_URL_CFG; cross-host task transport confirmed; ttyd live."
  echo "VERIFY_OK"
  exit 0
fi

# ===== self-contained Verify (original) =====

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

# --- mp peek reports TRUE live activity (BUSY vs IDLE), not a stale buffer ---
# Deterministic classifier gate: the busy/idle verdict must come from the live
# footer ("esc to interrupt" = a turn is running), and a queued message in the
# composer must NOT spoof an idle read.
python3 - "$INSTALL_DIR/bin/queue-client.py" <<'PY' || { echo "FAIL: peek_state classifier wrong"; exit 1; }
import importlib.util, sys
spec = importlib.util.spec_from_file_location("qc", sys.argv[1])
qc = importlib.util.module_from_spec(spec); spec.loader.exec_module(qc)
busy = "● Running install…\n────\n❯ go install the thing\n────\n  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt\n"
idle = "✻ Cooked for 17s\n────\n❯ \n────\n  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← for agents\n"
assert qc.peek_state(busy)[0] == "BUSY", qc.peek_state(busy)
assert qc.peek_state(idle)[0] == "IDLE", qc.peek_state(idle)
print("peek_state OK: busy->BUSY, idle->IDLE (queued composer text did not spoof)")
PY

# --- _composer_draft predicate gate (the mp-send-reliability fix) ---
# The send verifier must distinguish an EMPTY idle composer ('none') from an
# un-submitted draft. Regression: the separator RULE drawn under the composer
# must NOT read as draft content (the always-stuck bug that left agents idle
# with text they never submitted). Drives off live `tmux capture-pane`, so stub
# tmux_run with canned frames instead of a real pane.
python3 - "$INSTALL_DIR/bin/queue-client.py" <<'PY' || { echo "FAIL: _composer_draft classifier wrong"; exit 1; }
import importlib.util, sys, types
spec = importlib.util.spec_from_file_location("qc", sys.argv[1])
qc = importlib.util.module_from_spec(spec); spec.loader.exec_module(qc)
def frame(s):
    qc.tmux_run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=s, stderr="")
RULE = "─" * 40
# empty idle composer (rule below) -> none  (the regression that masked everything)
frame(f"✻ Cooked for 9s\n{RULE}\n❯ \n{RULE}\n  ⏵⏵ bypass permissions on · ← for agents\n")
assert qc._composer_draft("t", "claude") == "none", "empty composer must be 'none'"
# literal un-submitted draft -> literal
frame(f"{RULE}\n❯ go do the thing\n\n{RULE}\n  ⏵⏵ bypass permissions on (shift+tab to cycle)\n")
assert qc._composer_draft("t", "claude") == "literal", "literal draft must be 'literal'"
# collapsed paste chip -> chip (recovery must Enter, never BSpace)
frame(f"{RULE}\n❯ [Pasted text #1 +40 lines]\n{RULE}\n  ⏵⏵ bypass permissions on\n")
assert qc._composer_draft("t", "claude") == "chip", "paste chip must be 'chip'"
print("_composer_draft OK: empty->none (rule not draft), text->literal, chip->chip")
PY

# Live IDLE gate: the worker finished its turn above, so peek must say IDLE.
mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=IDLE' || { echo "FAIL: peek of idle worker didn't report IDLE"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }

# Live BUSY gate: hand the worker a slow tool call; while it runs, peek must say
# BUSY (this is the exact defect — a working agent must never read as idle).
mp send "main:worker-1" "Run this bash command now, nothing else: sleep 8; echo SLOWDONE" >/dev/null
PEEK_BUSY=0
for i in $(seq 1 12); do
  if mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=BUSY'; then PEEK_BUSY=1; break; fi
  sleep 1
done
[ "$PEEK_BUSY" = 1 ] || { echo "FAIL: peek of a working agent never reported BUSY"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }

# --- AskUserQuestion notifies the Boss, and `mp answer` unblocks the agent ---
# A question form is a BLOCKED turn — the Stop hook never fires for it, so without
# this the agent hangs silently. The PreToolUse/AskUserQuestion hook must notify
# the Boss with the question + offered options, and the Boss must be able to
# answer remotely (mp answer) to actually submit the form and let the agent
# proceed. (AskUserQuestion is a core tool in the in-container Claude — this check
# belongs to the fresh-container Verify.)
for i in $(seq 1 20); do mp peek "main:worker-1" 2>&1 | head -1 | grep -q 'state=IDLE' && break; sleep 1; done
QMARK="QOPT-$RANDOM"
mp send "main:worker-1" "Call the AskUserQuestion tool now — header 'Pick', question 'Which one?' — with exactly two options labelled 'First $QMARK' and 'Second $QMARK'. Invoke the tool; do not answer it yourself." >/dev/null

# 1) DETECT — the PreToolUse hook fired for AskUserQuestion.
PRE_OK=0
for i in $(seq 1 90); do
  grep -q '"event":"PreToolUse"' "$INSTALL_DIR/run/hook-events.log" 2>/dev/null && { PRE_OK=1; break; }
  sleep 1
done
[ "$PRE_OK" = 1 ] || { echo "FAIL: AskUserQuestion produced no PreToolUse hook event (tool not invoked / hook not firing)"; tail -5 "$INSTALL_DIR/run/hook-events.log"; exit 1; }

# 2) NOTIFY — the Boss pane received [AGENT QUESTION] with the offered options.
for i in $(seq 1 30); do
  tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT QUESTION\].*worker-1" && break; sleep 1
done
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -qE "\[AGENT QUESTION\].*worker-1" || { echo "FAIL: Boss never received [AGENT QUESTION]"; exit 1; }
tmux capture-pane -t mc-main:Boss -p -S -300 | grep -q "$QMARK" || { echo "FAIL: question notification missing the offered options ($QMARK)"; exit 1; }

# 3) ANSWER — Boss selects option 2 via mp; the agent must UNBLOCK (form submits,
#    the turn resumes and finishes → a fresh idle Stop status appears).
rm -f "$INSTALL_DIR/status/mc-main/worker-1.json"
mp answer "main:worker-1" 2 >/dev/null || { echo "FAIL: mp answer errored"; exit 1; }
UNBLOCKED=0
for i in $(seq 1 90); do
  if jq -e '.status=="idle"' "$INSTALL_DIR/status/mc-main/worker-1.json" >/dev/null 2>&1; then UNBLOCKED=1; break; fi
  sleep 1
done
[ "$UNBLOCKED" = 1 ] || { echo "FAIL: agent stayed blocked after mp answer (form never submitted)"; mp peek "main:worker-1" 2>&1 | head -1; exit 1; }
# Soft check that the SELECTED option (2 = 'Second') reached the agent, not just any submit.
jq -r .summary "$INSTALL_DIR/status/mc-main/worker-1.json" | grep -qiE "Second|option *2|2nd" \
  || echo "WARN: post-answer summary didn't obviously reflect option 2 — review: $(jq -r .summary "$INSTALL_DIR/status/mc-main/worker-1.json" | head -c 200)"

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

# --- heartbeat-based liveness: zombie agents auto-prune ---
# Prove the reaper on a throwaway instance with tiny thresholds so the test is
# ~5s, not QUEUE_DEAD_AFTER long, and never touches the real :9900 server.
( export QUEUE_SECRET=verifyprune QUEUE_PORT=9971 QUEUE_DEAD_AFTER=2 QUEUE_REAP_INTERVAL=1 QUEUE_HEARTBEAT=1
  python3 -u "$INSTALL_DIR/bin/queue-server.py" >/tmp/v-prune.log 2>&1 &
  TPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:9971/health >/dev/null 2>&1 && break; sleep 0.1; done
  PH(){ curl -fsS -H "X-Queue-Secret: verifyprune" "$@"; }
  PH -X POST -H 'Content-Type: application/json' -d '{"hostname":"livehost"}' http://127.0.0.1:9971/heartbeat >/dev/null
  PH -X POST -H 'Content-Type: application/json' -d '{"agent_id":"livehost/main:w","backend":"claude"}' http://127.0.0.1:9971/agents/register >/dev/null
  PH -X POST -H 'Content-Type: application/json' -d '{"agent_id":"deadhost/main:w","backend":"claude"}' http://127.0.0.1:9971/agents/register >/dev/null
  # keep livehost heartbeating across the dead window; deadhost goes silent
  for i in 1 2 3 4; do sleep 1; PH -X POST -H 'Content-Type: application/json' -d '{"hostname":"livehost"}' http://127.0.0.1:9971/heartbeat >/dev/null; done
  AGENTS=$(PH http://127.0.0.1:9971/agents)
  kill $TPID 2>/dev/null
  echo "$AGENTS" | jq -e '.[] | select(.agent_id=="livehost/main:w")' >/dev/null || { echo "FAIL: reaper killed a still-heartbeating agent"; exit 1; }
  echo "$AGENTS" | jq -e '.[] | select(.agent_id=="deadhost/main:w")' >/dev/null && { echo "FAIL: zombie agent on a dead host was NOT reaped"; exit 1; }
) || exit 1

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

# --- registry SURVIVES a queue-server restart (durability) ---
# The registry is in-memory and agents only register at spawn, so a server
# restart used to empty the HUD while every agent kept running. The client
# re-announces its agents each heartbeat, so the server must rebuild the live
# set itself within a heartbeat cycle — no manual re-registration.
QSECRET=$(grep ^QUEUE_SECRET= ~/.config/mypeople/queue.env | cut -d= -f2-)
HB=$(grep ^QUEUE_HEARTBEAT= ~/.config/mypeople/queue.env | cut -d= -f2-); HB=${HB:-30}
BEFORE=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
[ "$BEFORE" -ge 1 ] || { echo "FAIL: no agents registered before restart"; exit 1; }
kill "$(cat $INSTALL_DIR/run/queue-server.pid)" 2>/dev/null
for i in $(seq 1 20); do curl -fsS http://127.0.0.1:9900/health >/dev/null 2>&1 || break; sleep 0.1; done
set -a; . ~/.config/mypeople/queue.env; set +a
nohup python3 -u "$INSTALL_DIR/bin/queue-server.py" >> "$INSTALL_DIR/run/queue-server.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/queue-server.pid"
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:9900/health >/dev/null 2>&1 && break; sleep 0.2; done
EMPTY=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
REPOP=0
for i in $(seq 1 $((HB*2+10))); do
  N=$(curl -fsS -H "X-Queue-Secret: $QSECRET" http://127.0.0.1:9900/agents | jq 'length')
  [ "$N" -ge "$BEFORE" ] && { REPOP=1; break; }
  sleep 1
done
[ "$REPOP" = 1 ] || { echo "FAIL: registry did not repopulate after server restart (empty=$EMPTY, want>=$BEFORE)"; exit 1; }
echo "durability OK: $BEFORE agents → restart (empty=$EMPTY) → re-announced back to >=$BEFORE within a heartbeat cycle"

# Cleanup
mp kill "main:worker-1" >/dev/null 2>&1 || true
mp kill "main:Boss" >/dev/null 2>&1 || true

echo "VERIFY_OK"
```

## Failure modes


**`mp spawn --backend codex` says it spawned codex, but `ps` shows the pane running `claude`** → the registry label is NOT proof; the running process is. Two causes, both fixed in this seed:
  1. **Stale daemon.** The codex exec branch lives in `queue-client.py`, but a *long-running* queue-client holds its bytecode in memory — editing the file does NOT reload an already-running interpreter. If you add/change the codex path, you MUST restart the queue-client (`pkill -f bin/queue-client.py` then relaunch with the queue.env exported) or every spawn keeps using the OLD handler. Verify the restart took: `ps -o lstart= -p "$(cat run/queue-client.pid)"` is newer than the file's mtime, and the pid file matches the live pid.
  2. **Silent relabel on idempotent re-spawn.** When the target window already exists, `execute_spawn` reuses it and re-registers under the *requested* backend. Before the fix it did this WITHOUT checking the running process — so `--backend codex` onto a window already holding a `claude` pane flipped the registry to `codex` and returned success while claude kept running (every "codex" agent was a mislabeled claude). The fix: `_pane_backend()` reads the pane's `#{pane_pid}` command line (+ children) and the reuse path REFUSES a backend mismatch (`window … already runs backend='claude'; refusing to relabel … kill it first`). Reuse is allowed only when the live process matches.
  Always prove a codex agent by the process, never the label: `ps -o command= -p "$(tmux list-panes -t mc-<sess>:<tab> -F '#{pane_pid}')"` must show `codex --dangerously-bypass-approvals-and-sandbox`, whose child is the `@openai/codex-darwin-arm64/.../codex` binary. (R14: the seed is the artifact and the running *process* is the proof — a registry/gate label is a false green.)

**`mp spawn` fails with `claude TUI didn't show 'bypass permissions on' banner within 30s` — but `claude` launches fine by hand.** → the spawn execs `claude --dangerously-skip-permissions --settings '…' --plugin-dir <plugindir>`; an **old claude** rejects `--plugin-dir` with `error: unknown option '--plugin-dir'` and exits before any banner, and the readiness probe only reports the generic timeout. Surfaced live on a Raspberry Pi whose pre-installed claude was **2.0.5** (`--plugin-dir` landed in 2.1.x). Confirm with `claude --help | grep -- --plugin-dir` (empty = too old) and reproduce the real error with `claude --dangerously-skip-permissions --plugin-dir <plugindir> -p hi`. Fix: upgrade claude (Step 1 now does this automatically — `claude update` / `sudo npm install -g @anthropic-ai/claude-code@latest` / `claude install latest`), which preserves `~/.claude/.credentials.json` (no re-auth). NOTE the version skew this exposes: the seed is authored against whatever claude the dev box runs (e.g. 2.1.177); a node provisioned earlier can be far behind — always normalize the claude version at install, never assume "claude is installed" means "claude is current."

**`mp spawn <remote-host>/…` fails with `Spawn FAILED: cwd does not exist on this host: '<submitter-path>'`.** → `mp spawn` defaults `--cwd` to the SUBMITTER's current directory, but the agent runs on the TARGET host where that path may not exist (e.g. spawning from a Mac at `/Users/you` onto a Linux Pi that has no `/Users`). For any cross-host spawn, pass an explicit `--cwd` that exists on the TARGET (e.g. `--cwd /home/<user>` or `--cwd "$INSTALL_DIR"`). The Verify's local spawns use `--cwd "$HOME"` because submitter==target there; cross-host callers must set a target-valid cwd.

**A JOIN node has `claude` installed but every spawned agent 401s / never finishes a turn.** → `command -v claude` succeeding does NOT mean the node is authenticated. A node provisioned earlier can carry a **stale/expired** credential (`claude -p hi` → `API Error: 401 … Please run /login`). Rule 13 forbids copying a token from another node, so each JOIN node that will host claude agents needs its **own fresh per-node login**. With no interactive human at the node, mint the login non-interactively and approve it through the browser-auth flow: run `claude setup-token` on the node (it prints an OAuth URL and waits at `Paste code here`), authorize that URL in the CEO's already-authed Chrome via the Codex pilot (`~/.claude-chrome-cdp/authorize_claude.py '<url>'` → `code#state`), inject the `code#state` back into the node's `setup-token` prompt. `setup-token` writes a 1-year token to `~/.claude/.credentials.json`, after which spawned agents authenticate with no env var. (Canonical procedure + failure catalog: `seedlab/seeds/claude-browser-auth.seed.md`. NOTE that flow's docs say `claude auth login`; current claude — 2.0.5 through 2.1.177 — has **no `auth` subcommand**, only `claude setup-token`. `authorize_claude.py` handles the setup-token URL shape — `code=true` decoy + `console.anthropic.com` callback — unchanged.)

**Status file never written** → Stop hook didn't fire. Check `$INSTALL_DIR/run/hook-events.log` for any entries; if empty, the plugin didn't load — verify `--plugin-dir` was on the spawned `claude` command line and `hooks.json` parses.

**Status file exists but `summary` is empty** → claude didn't actually emit a last_assistant_message before stopping. Either the worker hit an error early or claude's Stop hook payload schema changed. Inspect `hook-events.log` and the worker's pane.

**Notification never lands in Boss pane** → check that `BOSS_ID` env var was set on the worker (`tmux capture-pane -t mc-main:worker-1 -p -S -100 | grep BOSS_ID`); check queue-client log for the inbound send task targeting Boss; check queue-server log for the POST from emit-event.

**`--backend codex` spawn fails or hangs / no codex notification** → first confirm codex auth is VALID (not just present): `codex login status` reports "Logged in" even on a stale/rotated token, but turns 401 with `token_expired` and the composer is delayed by failed MCP init — which can trip the readiness probe. Peek the pane (`tmux capture-pane -t mc-<sess>:<tab> -p -S -120`) for `token_expired` / "sign in again"; if present, re-auth codex (`codex login`, or `printenv OPENAI_API_KEY | codex login --with-api-key`). If the agent runs but the Boss never hears about turn-end, confirm the exec line carried `-c notify=[...codex-notify...]` (peek scrollback), that `codex-notify` is executable in `plugins/tmux-boss-hooks/hooks/`, and that `hook-events.log` shows an `agent-turn-complete` line. Codex turn-end uses `notify` (argv[1], hyphenated keys), NOT a Stop hook — there is no `--plugin-dir` involvement on the codex path.

**Pane in copy-mode swallowed our send** → the target pane was scrolled (mouse wheel, manual entry, etc.) which puts tmux in copy/view-mode (`#{pane_in_mode}=1`). In that state `send-keys` types INTO copy-mode commands instead of the TUI's input buffer — silent failure. `tmux_send_text` auto-exits via `send-keys -X cancel` before every paste, AND mirrors the check after Enter so the pane is returned to text-editing mode for any human who picks it up next. Invariant: `pane_in_mode == 0` on every successful return of `tmux_send_text`. Keep both halves of this defense.

**`mp send` delivers the text but the agent sits IDLE with it un-submitted (turn never fires)** → the message was pasted into the composer but never became a turn, so a worker can sit idle for 40+ minutes on dispatched work it never started. Root cause was the verification predicate, not the keystrokes. The old `_composer_stuck` scanned the composer region from the prompt glyph down to the *footer* (`bypass permissions on`) — which swallowed the horizontal separator RULE (`────`) drawn just under the composer as "draft content". So it returned **True for a perfectly empty, idle composer**: the verifier could never distinguish "submitted" from "stuck". Two failures flowed from that one bug: (a) the BSpace+Enter recovery fired blindly on *every* send to a non-busy agent, and on a collapsed `[Pasted text #N]` chip a stray BSpace deletes the whole chip → the message is silently *lost*; (b) the verifier's busy-marker short-circuit (`if busy: return not-stuck`) masked a genuinely orphaned draft — a paste landing mid-turn whose Enter was absorbed becomes a draft *under* the still-running prior turn; the prior turn's busy marker made the verifier declare success, and when that turn ended the draft was left sitting idle. The fix: `_composer_draft` terminates the region at the **rule** (the true bottom edge) so an empty composer reads `none`; it classifies `literal` vs `chip` so recovery resubmits correctly (chip → Enter only, never BSpace); and `tmux_send_text` uses a **positive** success gate — capture `busy_before`, then resubmit any lingering draft and accept ONLY on our own busy-edge or a stably-empty composer (checking the draft FIRST so an orphan under a prior turn isn't masked). An `mp send` that returns ok has provably fired a turn, or fails loudly. (R14: trust the pane, not the agent's self-report — and the verifier's predicate IS part of the pane-reading; a predicate that's always-true is a false green just like a registry label.) Proof: 8 consecutive `mp send`s (7 of them landing while the agent was already busy) each fired a distinct turn, all 8 tokens processed, composer empty — see `## Verify`.

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
