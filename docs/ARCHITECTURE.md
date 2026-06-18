# mypeople v2 — Architecture

This document describes the Kimi-native rewrite of mypeople. It replaces the original Claude/tmux/Tailscale runtime with a thin external queue that drives multiple Kimi Code CLI sessions through the **ACP (Agent Control Protocol)** multi-session backend.

## Goals

- Run many independent Kimi sessions from one control plane.
- Let a human CEO and a Boss agent coordinate workers without raw tmux or browser tabs.
- Keep the runtime small, stdlib-only, and easy to audit.
- Work on Windows via WSL + Brave.

## High-level layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Windows host                                    │
│  ┌──────────────┐     HTTP      ┌──────────────────────────────────────┐   │
│  │ Brave / HUD  │ ◄────────────►│  mypeople queue server (port 9900)   │   │
│  │              │               │  Runs inside WSL                     │   │
│  └──────────────┘               │  - HTTP control plane                │   │
│                                 │  - owns one `kimi acp` subprocess    │   │
│                                 └──────────────┬───────────────────────┘   │
│                                                │ stdio JSON-RPC            │
│                                 ┌──────────────▼──────────────┐            │
│                                 │  `kimi acp` multi-session   │            │
│                                 │  backend                    │            │
│                                 └──────────────┬──────────────┘            │
│                                                │ one ACP session per agent │
│                                 ┌──────────────▼──────────────┐            │
│                                 │  Kimi agent workers / Boss  │            │
│                                 └─────────────────────────────┘            │
│                                                                            │
│  Kimi lifecycle hooks in ~/.kimi/config.toml                               │
│  POST SessionStart / Stop / StopFailure / SessionEnd / PreToolUse          │
│  ─────────────────────────────────────────────► /hook on queue server      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Queue server (`src/mypeople/queue_server.py`)

A single-process Python HTTP server built on `http.server`. It is the source of truth for agent state.

Responsibilities:
- Spawn ACP sessions (`/task/submit` action `spawn`).
- Deliver prompts (`/task/submit` action `send`).
- Report state (`/agents`, `/dashboard`, `/task/submit` action `peek`).
- Cancel / reap agents (`/task/submit` action `kill`).
- Receive Kimi lifecycle hooks (`POST /hook`).
- Notify the Boss when a worker finishes.

Security:
- All mutating and state endpoints require a shared secret via `X-Queue-Secret` or `Authorization: Bearer <secret>`.
- The dashboard can be viewed with `?secret=<secret>` in the URL.
- The secret is generated at install time and stored in `~/.config/mypeople/queue.env`.

Concurrency:
- The ACP client runs in a dedicated background asyncio thread.
- Agent state is protected by a `threading.Lock`.
- HTTP requests are handled by `ThreadingHTTPServer`.

### 2. ACP client (`src/mypeople/acp_client.py`)

A minimal async JSON-RPC client over `kimi acp` stdio. It speaks exactly the subset of ACP needed by mypeople:

- `initialize`
- `session/new`
- `session/list`
- `session/prompt`
- `session/cancel` (notification)

Streaming `session/update` notifications are routed to a callback so the queue server can update agent state in real time.

### 3. `mp` CLI (`src/mypeople/mp`)

Thin Python CLI. Reads `~/.config/mypeople/queue.env` and calls `/task/submit`.

Verbs:
- `status`
- `spawn <agent-id> [--cwd PATH] [--boss AGENT] [--master]`
- `send <agent-id> "<prompt>"`
- `peek <agent-id>`
- `kill <agent-id>`

Agent IDs are canonicalized to `<host>/<session>:<tab>` using `HOST_ID` from the env file (defaults to `hostname`).

### 4. Kimi lifecycle hook (`hooks/mypeople-hook.py`)

A global hook registered in `~/.kimi/config.toml`. It reads a JSON payload from stdin and POSTs it to `QUEUE_URL/hook`.

Forwarded events:
- `SessionStart` → agent state becomes `idle`.
- `Stop` → agent state becomes `idle`; if the agent has a `boss_id`, the Boss receives a notification prompt.
- `StopFailure` → agent state becomes `dead`; Boss is notified.
- `SessionEnd` → agent state becomes `dead`.
- `PreToolUse` with `tool_name == AskUserQuestion` → agent state becomes `blocked`.

The hook is fail-open: any network or parsing error is logged to `~/.config/mypeople/hook-errors.log` but never blocks the Kimi session.

### 5. Boss agent (`agents/boss-kimi.yaml` + `agents/boss-kimi.md`)

A Kimi agent loaded into a `kimi web` session. Its system prompt encodes three rules:

1. **Plan gate** — no engineering until brainstorm, `plans/<feature>/PLAN.md`, a Verify block, and explicit CEO approval exist.
2. **Autonomous loop** — react to worker notifications, dispatch idle workers, ask the CEO when no work remains.
3. **Fire-and-forget through `mp`** — never bypass the queue server.

The Boss is started manually with `./scripts/start-boss.sh` and viewed in Brave via `./scripts/start-boss.ps1`.

### 6. Worker agents (`agents/worker-*.yaml`)

ACP `session/new` currently does not accept an `--agent-file` parameter, so spawned workers run Kimi's default agent plus whatever project-local `.kimi/skills/` and `AGENTS.md` exist in their working directory. The `worker-*.yaml` files are kept for forward compatibility and can be referenced by the Boss's subagent list.

## Data flow

### Spawning a worker

1. `mp spawn host/project:w1 --cwd ./project` → POST `/task/submit` action `spawn`.
2. Queue server calls ACP `session/new` with the cwd.
3. ACP returns a `sessionId`.
4. Queue server registers `{agent_id, session_id, cwd, state: idle}`.
5. Hook may later fire `SessionStart` and confirm `idle`.

### Sending a prompt

1. `mp send host/project:w1 "Write tests"` → POST `/task/submit` action `send`.
2. Queue server marks the agent `working`.
3. Queue server calls ACP `session/prompt`.
4. ACP streams `session/update` chunks; the queue server records the latest text as a summary.
5. When the turn ends, ACP returns a `stopReason`; the queue server marks the agent `idle`.
6. Kimi hook fires `Stop`; the queue server optionally notifies the Boss.

### Boss notification

1. Worker `w1` has `boss_id = host/project:Boss`.
2. When `w1` finishes, `_notify_boss_locked` runs `session/prompt` on the Boss session with a short notification.
3. The Boss sees the notification in its Kimi web UI and reacts (plan-gate, dispatch next task, ask CEO).

## Agent state machine

```
starting ──SessionStart──► idle ◄──────┐
                              │        │
                              ▼        │ Stop
                           working ────┘
                              │
                              │ AskUserQuestion
                              ▼
                           blocked
                              │
                              │ kill / SessionEnd / StopFailure
                              ▼
                             dead
```

Agents are also marked `dead` if silent for more than `AGENT_DEAD_AFTER` seconds (default 300).

## Security model

| Layer | Mechanism | Notes |
|-------|-----------|-------|
| Queue HTTP | shared secret header / bearer token | generated per install |
| Boss web UI | `--auth-token` reuse of queue secret | LAN only by default |
| ACP backend | Kimi OAuth | handled by `kimi login` |
| Hooks | secret header | same secret as queue |

Important assumptions:
- Everything runs on a private LAN (WSL ↔ Windows).
- The queue secret is the same token used for the Boss web UI. Do not expose port 9900 or 5494 to the public internet.
- The `--network` and `--dangerously-omit-auth` paths were rejected; we use `--auth-token` instead.

## Compatibility

| Requirement | Version / detail |
|-------------|------------------|
| OS | Windows 10/11 with WSL2 |
| Linux distro | Ubuntu 24.04 tested |
| Kimi Code CLI | 1.30.0+ |
| Python | 3.10+ |
| Browser | Brave / Chrome / Edge |

Known limitations:
- ACP `session/new` cannot load a custom `--agent-file`. Workers use Kimi's default agent.
- Each ACP session is single-turn-per-prompt; there is no persistent tmux pane.
- Cross-host orchestration is not implemented in v2 (Tailscale removed).
- File attachments, voice, PR watcher, resume, and disaster recovery are not implemented.

## Files and responsibilities

| Path | Purpose |
|------|---------|
| `src/mypeople/queue_server.py` | HTTP control plane + ACP owner |
| `src/mypeople/acp_client.py` | JSON-RPC client for `kimi acp` |
| `src/mypeople/mp` | CLI for humans and the Boss |
| `hooks/mypeople-hook.py` | Kimi lifecycle → queue server |
| `agents/boss-kimi.yaml` | Boss agent definition |
| `agents/boss-kimi.md` | Boss doctrine |
| `agents/worker-*.yaml` | Worker agent definitions (future use) |
| `scripts/install.sh` | WSL install + hook registration |
| `scripts/install.ps1` | Windows prerequisite check |
| `scripts/start-queue-server.sh` | Start queue server |
| `scripts/start-boss.sh` | Start Boss web UI in WSL |
| `scripts/start-boss.ps1` | Open Boss in Brave |
| `scripts/start-dashboard.ps1` | Open dashboard in Brave |
| `scripts/verify.sh` | Control-plane smoke test |

## Why this architecture

1. **No tmux** — ACP sessions are lightweight and do not require pane management.
2. **No Claude plugin** — Kimi's native hook system gives us lifecycle events.
3. **No Tailscale hard requirement** — everything is local to the WSL host.
4. **Single source of truth** — the queue server owns all ACP sessions, so state is always consistent.
5. **Thin protocol layer** — if Kimi's ACP changes, only `acp_client.py` needs updates.
