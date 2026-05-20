# Post-install verification

After running the seed and seeing `SEED_RESULT=DONE`, run **one** of these against the Boss to prove the system actually orchestrates a team. Each test is a single prompt you paste into the Boss's claude pane.

The seed's own `## Verify` block already proves plumbing (queue alive, hooks fire, notifications routed, Tailscale up). These tests prove **role behavior** — that the Boss can actually drive a team end-to-end.

## Smoke (30 seconds)

Fastest sanity check. Two engineers, one message each. Paste into Boss:

[`tests/smoke.md`](smoke.md)

Expect: Boss spawns two workers, sends each a one-word task, receives both notifications, summarizes, kills.

## 3-engineer chain (3–5 minutes)

Real orchestration test. Two turns × three engineers = six dependent round-trips. Each step's output feeds the next, math is deterministic, eyeball-verifiable.

[`tests/3-engineer-chain.md`](3-engineer-chain.md)

Expect: Boss spawns three workers in `/tmp/mypeople-chain-test`, runs the two-turn chain, prints the final TOTAL, recomputes the math itself to flag inconsistencies, kills all three and removes the tmp dir.

## Parallel fan-out (2–3 minutes)

Orthogonal to the chain test: five engineers, five independent tasks, dispatched in parallel. Proves out-of-order notification handling and aggregation.

[`tests/parallel-fanout.md`](parallel-fanout.md)

Expect: Boss spawns five workers in `/tmp/mypeople-fanout-test`, fires all five sends without waiting, collects notifications as they arrive (likely out of order), prints a single aggregated results block, cleans up.

## How to attach to the Boss

After install:
```bash
# host on the tailnet: open the HUD, click Boss row's attach link
http://<TS_HOSTNAME>.<tailnet>.ts.net:9900/dashboard

# or attach in a local terminal:
tmux attach -t mc-main      # if you're on the same host as the Boss
```

Paste the test prompt. Watch the HUD as workers come and go.
