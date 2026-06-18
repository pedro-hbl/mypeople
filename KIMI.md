# mypeople — engineer's handbook

Read this before modifying mypeople or running it in production.

## The product

mypeople is a small runtime for orchestrating Kimi Code CLI sessions via an HTTP queue. One queue server owns one `kimi acp` subprocess; the `mp` CLI and a browser dashboard interact with it; Kimi hooks keep the queue server informed of session lifecycle.

## The runtime

| Component | Path | Purpose |
|---|---|---|
| Queue server | `src/mypeople/queue_server.py` | HTTP control plane + ACP client owner |
| `mp` CLI | `src/mypeople/mp` | Human / Boss interface to the queue |
| ACP client | `src/mypeople/acp_client.py` | JSON-RPC over `kimi acp` stdio |
| Kimi hook | `hooks/mypeople-hook.py` | Receives Kimi lifecycle events and POSTs to `/hook` |
| Boss agent | `agents/boss-kimi.yaml` + `agents/boss-kimi.md` | Doctrine for the Boss session |
| Dashboard | Embedded in `queue_server.py` | Browser HUD at `/dashboard` |

## Development rules

1. **WSL-first.** `kimi web` has known Unicode issues on native Windows in this environment. Run the queue server and `kimi web` inside WSL; use Brave on Windows as the viewer.
2. **The queue server is the source of truth for agent state.** Do not manage ACP sessions outside it.
3. **Keep the ACP client thin.** It speaks JSON-RPC over stdio. If Kimi's ACP protocol changes, update `acp_client.py` first.
4. **Fail open on hooks.** A hook failure must never block the user's Kimi session.
5. **Document limitations.** ACP `session/new` cannot load a custom `--agent-file`. If that changes in a future Kimi release, update the architecture.

## Local testing

```bash
# Terminal 1: start the queue server
./scripts/start-queue-server.sh

# Terminal 2: run smoke checks
./scripts/verify.sh

# Terminal 3: test a real prompt
mp spawn $(hostname)/test:w1 --cwd /tmp
mp send $(hostname)/test:w1 "Say hello"
mp status
mp kill $(hostname)/test:w1
```

## Adding a feature

1. Capture the idea in `plans/<feature>/PLAN.md`.
2. Add capabilities to `plans/capabilities.md`.
3. Implement the smallest slice.
4. Update `docs/ARCHITECTURE.md` and `README.md` if behavior changes.
5. Run `./scripts/verify.sh`.

## Where old Claude code lives

The original seed-based Claude runtime is preserved under `archive/` for reference but is no longer part of the supported install path.
