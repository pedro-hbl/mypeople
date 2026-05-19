# mypeople — SEED increment plan

5 seeds. Each is pastable into a fresh container with claude only. Each one's `## Verify` proves the listed capabilities work from the pane (not from agent self-report). Don't move to N+1 until N's Verify passes from a clean container.

| SEED | Theme | Capabilities added | Verify (pane truth) |
|---|---|---|---|
| **1** | Foundation — runtime alive (no agents yet) | install `tmux python3 jq git`; clone repo; write `queue.env`; launch queue-server + queue-client | `curl 127.0.0.1:9900/health` 200; `mp status` → "No active agents" |
| **2** | Core agent loop (single-agent, local) | **#1 spawn**, **#11 backend-claude**, **#2 send**, **#3 peek**, **#4 kill**, **#5 status** | spawn `w1`; send "echo MARK"; capture-pane contains MARK; status shows w1 idle; kill; status shows no w1 |
| **3** | Lifecycle notifications | **#6 boss-tab**, **#7 stop-hook**, **#8 status-files** | spawn Boss + w1 (boss=Boss); send w1 "reply PONG"; `status/mc-test/w1.json` shows summary=PONG; Boss pane has `[AGENT NOTIFICATION] w1 ... PONG` |
| **4** | Observability | **#9 hud**, **#10 browser-attach** | `curl /dashboard` 200; `/agents` API lists spawned agent; `curl :7681` 200 |
| **5** | Cross-host via Tailscale | **#12 cross-host** | two containers joined to same Tailnet, queue-server on A; spawn on B; tab exists on B (not A); message sent from A lands in B's pane; stop notification routes back to A's Boss |

## Why this order

- **1 before 2** — can't spawn agents without the queue running.
- **2 before 3** — boss-tab is a special spawn flag; need spawn proven first. Notifications need agents to notify.
- **3 before 4** — HUD is read-only over data that the stop-hook + status-files produce; testing dashboard with zero agents is meaningless.
- **5 last** — needs everything else proven on a single host first, then scales sideways. Adds Tailscale auth as a new Input.

## Anti-goals (each SEED MUST NOT)

- Use OS package installs the seed didn't declare (beloved-engineer rule)
- Self-report DONE without the Verify script exiting 0
- Depend on artifacts from the host (everything inside the container)
- Skip the Interview (Step 0 must collect inputs before any state change)

## What's required outside the SEEDs (one-time, host-side)

- The tmux-boss source needs to be fetchable from inside the container. SEED 1's `## Inputs` will collect a `tmux_boss_source` (git URL or tarball URL or mounted path) at Step 0 Interview.
- For SEED 5: a Tailscale auth key (collected in that SEED's Inputs).
