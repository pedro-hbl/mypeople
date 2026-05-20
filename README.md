# mypeople

A tiny multi-agent orchestration runtime for Claude Code. Spawn agents, send messages, watch a HUD, all reachable across machines via Tailscale.

The whole thing ships as one file: [`seeds/mypeople.seed.md`](seeds/mypeople.seed.md). Paste it into your claude (host or container) and you have a working system.

Optional sibling seeds layer extra features on top (paste them AFTER mypeople is installed):

- [`seeds/pr-autoapprove.seed.md`](seeds/pr-autoapprove.seed.md) — GitHub PR watcher + `/<user>-approve` auto-approval. Pushes new comments/reviews/mentions to the Boss via the mypeople queue.

## What you get

- **Queue server** (HTTP, port 9900) — the bus everything routes through.
- **`mp` CLI** — `spawn / send / peek / kill / status` for managing agents.
- **Boss role** — an agent with an installed doctrine (plan-gate, autonomous loop, fire-and-forget). `mp spawn --master` bootstraps it.
- **Per-spawn Claude Code hooks plugin** — agents emit lifecycle events; status files written; notifications routed to the Boss's pane.
- **HUD** at `http://<container>:9900/dashboard` — live browser view of all agents.
- **ttyd attach** at `http://<container>:7681/?arg=-t&arg=mc-<sess>:<tab>` — open any agent's tmux pane in your browser.
- **Tailscale tailnet join** — everything reachable via stable hostnames from any tailnet node (your mac, phone, another container).

## Install

```bash
# 1. Run a fresh Debian-12 container with claude installed, plus
#    --cap-add=NET_ADMIN --device /dev/net/tun:/dev/net/tun and a
#    TS_AUTHKEY env var (mint at https://login.tailscale.com/admin/settings/keys).
# 2. Inside the container, start claude:
claude --dangerously-skip-permissions
# 3. Paste the contents of seeds/mypeople.seed.md.
```

The seed asks for any missing inputs at Step 0 Interview, then runs to completion (~5 minutes). When you see `SEED_RESULT=DONE`, the runtime is up.

## Use

```bash
# after install:
mp spawn main:Boss --master --backend claude        # the Boss, with doctrine
mp spawn main:worker-1 --backend claude --boss main:Boss
mp send main:worker-1 "find me primes under 100"
mp status
mp peek main:worker-1
mp kill main:worker-1
```

The HUD shows everything. Click an agent's "attach" link to open its claude pane in the browser.

## Verify it actually works

After install, paste one of these into the Boss's claude pane:

- [`tests/smoke.md`](tests/smoke.md) — 30s sanity check (2 workers, 2 messages)
- [`tests/3-engineer-chain.md`](tests/3-engineer-chain.md) — 3-5 min orchestration test (2 turns × 3 engineers, deterministic math chain)

See [`tests/README.md`](tests/README.md) for how to attach to the Boss.

## Docs

- `seeds/mypeople.seed.md` — the runtime itself
- `plans/boss-claude.md` — Boss doctrine (also inlined into the seed)
- `plans/features.md` — feature list
- `plans/capabilities.md` — testable spec per capability
- `CLAUDE.md` — engineer handbook for working on mypeople

## License

(none yet — set one before public adoption.)
