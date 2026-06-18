# AGENTS.md — mypeople

Conventions for working on and with mypeople.

## Project layout

```
.
├── src/mypeople/          # runtime (queue server, ACP client, mp CLI)
├── hooks/                 # Kimi lifecycle hooks
├── agents/                # Kimi agent definitions
├── scripts/               # install / launch scripts
├── docs/                  # architecture, security, usage
├── plans/                 # features and capabilities specs
├── archive/               # old Claude-based code (reference only)
├── README.md
├── KIMI.md
└── AGENTS.md              # this file
```

## How to run tests / verify

1. Start the queue server: `./scripts/start-queue-server.sh`
2. Run the smoke test: `./scripts/verify.sh`
3. Run the capability checks in `plans/capabilities.md`.
4. Open `http://<wsl-ip>:9900/dashboard` in Brave.

## Agent files

- `agents/boss-kimi.yaml` — Boss agent. Load with `kimi --agent-file agents/boss-kimi.yaml web`.
- `agents/worker-coder.yaml` — focused implementation agent.
- `agents/worker-explore.yaml` — read-only exploration agent.
- `agents/worker-plan.yaml` — planning and architecture agent.

## Hooks

`hooks/mypeople-hook.py` is registered globally in `~/.kimi/config.toml`. It must remain lightweight and never block the Kimi session.

## Coding style

- Python 3.10+ with type hints.
- Prefer stdlib; avoid extra dependencies for the queue server.
- Keep the ACP client thin and protocol-agnostic above the JSON-RPC layer.
- Never commit secrets or generated local state (see `.gitignore`).
