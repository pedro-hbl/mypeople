# mypeople — multi-agent orchestration for Kimi Code CLI

A tiny runtime for spawning and managing multiple Kimi Code CLI sessions from a single queue server, with a browser dashboard and an `mp` CLI.

This is a Kimi-native refactor of the original Claude Code-based mypeople. It drops tmux, Claude plugins, and Tailscale as hard requirements, and is designed to run on Windows via WSL with Brave as the primary UI.

## Why this exists

Kimi Code CLI is great for long coding sessions, but it is single-threaded: one chat, one task. mypeople turns it into a small agent operating system:

- Run several independent Kimi sessions at once.
- See all of them on a live browser dashboard.
- Send prompts, check state, and kill sessions from a CLI.
- Let a Boss agent coordinate workers through the same CLI.

Use cases:

- **Parallel workstreams** — one worker writes tests, another refactors, a third explores a dependency.
- **CEO + Boss pattern** — you set direction in the Boss web UI; the Boss dispatches workers and reports back.
- **Fire-and-forget tasks** — spawn a worker, send a prompt, and watch the dashboard while you do something else.
- **Long-running background turns** — a worker can keep thinking while you chat with the Boss.

## What you get

- **Queue server** (HTTP, port `9900`) — the bus everything routes through.
- **`mp` CLI** — `spawn / send / peek / kill / status` for managing agents.
- **Boss role** — a Kimi agent file with the plan-gate + autonomous-loop doctrine.
- **Kimi hooks** — agents emit lifecycle events (`SessionStart`, `Stop`, `SessionEnd`) to the queue server.
- **Browser HUD** at `http://<wsl-ip>:9900/dashboard` — live view of all agents.
- **ACP sessions** — each agent is an independent Kimi session created via `kimi acp`.

## Requirements

- Windows 10/11 with WSL2 and a Linux distro (Ubuntu 24.04 recommended).
- [Kimi Code CLI](https://moonshotai.github.io/kimi-cli/) installed **inside WSL** and logged in (`kimi login`).
- Brave (or any browser) on Windows.
- Python 3.10+ inside WSL.
- Working DNS inside WSL (test with `ping auth.kimi.com`).

## Install

From a WSL shell:

```bash
cd "$HOME/Workspace"  # or wherever you keep repos
git clone https://github.com/pedro-hbl/mypeople.git
cd mypeople
./scripts/install.sh
```

This will:
- Create `~/.config/mypeople/queue.env` with a random secret.
- Register Kimi hooks in `~/.kimi/config.toml`.
- Symlink `mp` into `~/.local/bin`.

If you prefer to run the WSL install from Windows PowerShell as admin:

```powershell
./scripts/install.ps1
```

## Start the system

1. **Start the queue server** (in one WSL terminal):
   ```bash
   ./scripts/start-queue-server.sh
   ```

2. **Open the dashboard** in Brave on Windows:
   ```powershell
   ./scripts/start-dashboard.ps1
   ```

3. **Start the Boss** (in another WSL terminal):
   ```bash
   ./scripts/start-boss.sh
   ```

4. **Open the Boss in Brave**:
   ```powershell
   ./scripts/start-boss.ps1
   ```

## Use

Spawn agents from WSL:

```bash
mp spawn myhost/project:worker-1 --cwd ./my-project
mp spawn myhost/project:worker-2 --cwd ./my-project --boss myhost/project:Boss
mp send myhost/project:worker-1 "List the files in this directory"
mp status
mp peek myhost/project:worker-1
mp kill myhost/project:worker-1
```

The Boss receives a notification prompt when a worker with `--boss` finishes a turn.

### Boss pattern example

1. Start the Boss and open it in Brave.
2. Tell the Boss: "We need to add OAuth to the API."
3. The Boss writes `plans/oauth/PLAN.md`, asks you to approve.
4. After approval, the Boss spawns workers:
   ```bash
   mp spawn myhost/oauth:explore --cwd ./my-project --boss myhost/oauth:Boss
   mp spawn myhost/oauth:coder --cwd ./my-project --boss myhost/oauth:Boss
   ```
5. The Boss sends prompts, checks status, and reports progress.

## Architecture

```
┌─────────────┐     HTTP      ┌──────────────┐     stdio JSON-RPC    ┌──────────┐
│   Brave     │ ◄────────────►│ queue-server │ ◄───────────────────►│ kimi acp │
│  (Boss UI)  │               │  (port 9900) │                      │ (subproc)│
└─────────────┘               └──────┬───────┘                      └────┬─────┘
                                     │ HTTP /hook                         │
                                     │                                   │
                              ┌──────▼───────┐                      ┌────▼────┐
                              │  Kimi hooks  │                      │ Agents  │
                              │ (~/.kimi/    │                      │ (ACP    │
                              │  config.toml)│                      │ sessions)│
                              └──────────────┘                      └─────────┘
```

- The queue server owns the single `kimi acp` subprocess.
- `mp spawn` creates a new ACP session and registers it.
- `mp send` calls ACP `session/prompt`.
- Kimi hooks POST lifecycle events back to `/hook`.
- The Boss is a normal Kimi web session loaded with `agents/boss-kimi.yaml`.

For the full architecture, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Important differences from the original Claude version

- **No tmux.** Agents are ACP sessions, not tmux panes.
- **No Claude plugin.** Lifecycle hooks use Kimi's native hook system.
- **No Tailscale by default.** Everything is local to the WSL host. Cross-host can be added later.
- **ACP sessions use the default Kimi agent.** Workers pick up project-local `.kimi/skills/` and `AGENTS.md` from their working directory. The Boss is launched manually with `--agent-file agents/boss-kimi.yaml`.

## Security

- The queue server and Boss web UI share a secret stored in `~/.config/mypeople/queue.env`.
- Do not expose ports `9900` or `5494` to the public internet.
- The Boss web UI runs with `--network` but is LAN-only by default.
- See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#security-model) for details.

## Troubleshooting

### `mp send` fails with "Authentication required"

Run `kimi login` in WSL and authorize the device.

### WSL DNS fails (`ping auth.kimi.com`)

If `/etc/resolv.conf` is empty, set a nameserver:

```bash
sudo rm -f /etc/resolv.conf
printf "nameserver 8.8.8.8\nnameserver 1.1.1.1\n" | sudo tee /etc/resolv.conf
sudo chmod 644 /etc/resolv.conf
```

### Boss web UI shows "Session Error Unauthorized"

Use `./scripts/start-boss.ps1` (Windows) or open the URL with `?token=<secret>`.

### `kimi web` cannot find `--agent-file`

Use `./scripts/start-boss.sh`; it places `--agent-file` before the `web` subcommand.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture.
- [`docs/USE_CASES.md`](docs/USE_CASES.md) — concrete orchestration examples.
- [`KIMI.md`](KIMI.md) — engineer handbook.
- [`AGENTS.md`](AGENTS.md) — conventions for agents and skills.
- [`plans/features.md`](plans/features.md) — feature list.
- [`plans/capabilities.md`](plans/capabilities.md) — testable spec.

## License

(none yet — set one before public adoption.)
