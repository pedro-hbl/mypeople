# mypeople — features (v2, Kimi)

## Core agent control

1. **spawn** — create an ACP session and register it as an agent
2. **send** — deliver a prompt to a specific agent via the queue
3. **peek** — return the agent's state, summary, and recent history
4. **kill** — cancel the agent's turn and mark it dead
5. **status** — list every agent + state

## Topology

6. **boss-tab** — designate a master agent; workers with `--boss` notify it on completion
7. **master** — mark an agent as the master/Boss session

## Lifecycle visibility

8. **stop-hook** — Kimi hook fires `Stop` / `StopFailure` / `SessionEnd` to the queue server
9. **status-files** — agent state is available via `/agents` and `/dashboard`

## Observability

10. **hud** — browser dashboard at `/dashboard` listing agents, state, summary, last activity
11. **browser-open** — dashboard links open the shared Kimi web UI with the auth token

## Backends

12. **backend-kimi** — agents run as ACP sessions under `kimi acp`

## Architectural constraint

- **Global identity** — every agent is addressed as `<host>/<session>:<tab>`. Host disambiguates agents on different machines. Short form `<session>:<tab>` is canonicalized to the current host.

## Boss doctrine

- **Plan-gate** — Boss refuses engineering work until brainstorm, PLAN, Verify, and CEO approval exist.
- **Autonomous loop** — Boss reacts to worker notifications, dispatches idle workers, and asks the CEO for direction when there is no work.

## Use cases

- **Parallel workstreams** — run multiple independent coding tasks at once.
- **CEO + Boss pattern** — human sets direction, Boss plans and dispatches workers.
- **Fire-and-forget** — send a prompt to a worker and monitor it on the HUD.
- **Background turns** — keep long-running exploration or tests running while you chat with the Boss.

## What's NOT in v2

- tmux / ttyd attach
- Claude / Codex backend
- Tailscale cross-host routing
- `mp answer` (ACP sessions auto-resolve `AskUserQuestion` with an empty answer in current Kimi versions)
- Independent per-agent browser tabs (Kimi web UI is a single shared session list)
- File attachments, voice, PR watcher, resume, disaster recovery
