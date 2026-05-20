# 3-engineer chain test — 3-5 min

Two turns across three engineers, six strict-dependency round-trips. Each step depends on the previous output. Math is deterministic so you can eyeball the final TOTAL.

Paste this whole block into the Boss's claude pane:

---

First, create a fresh tmp working dir for this test:
  `mkdir -p /tmp/mypeople-chain-test`

Spawn three engineers (`--boss yourself`, `--cwd /tmp/mypeople-chain-test`): eng-1, eng-2, eng-3. We will run TWO turns across all three engineers, six round-trips total. Each step depends on the previous output. Wait for each [AGENT NOTIFICATION] before sending the next message. Strict order:

**TURN 1**
- T1:A1 → eng-1: pick an integer between 10 and 99. Reply with ONLY the number. → call this N1.
- T1:A2 → eng-2: given N1=<N1>, compute N1 * 2. Reply with ONLY the number. → call this N2.
- T1:A3 → eng-3: given N2=<N2>, reverse the digits of N2 (e.g. 84 → 48; 100 → 001 i.e. 1). Reply with ONLY the number. → call this N3.

**TURN 2**
- T2:A1 → eng-1 (same instance): given N3=<N3>, add the sum of digits of N3 to N3 itself. Reply with ONLY the number. → call this N4.
- T2:A2 → eng-2 (same instance): given N4=<N4>, multiply N4 by 3. Reply with ONLY the number. → call this N5.
- T2:A3 → eng-3 (same instance): given N1..N5 = <N1>, <N2>, <N3>, <N4>, <N5>, return their sum. Reply with ONLY the number. → call this TOTAL.

After T2:A3, summarize the full chain in one block:
```
N1=<>, N2=<>, N3=<>, N4=<>, N5=<>, TOTAL=<>
```
Verify by recomputing the math yourself; flag any inconsistency.

Then kill all three engineers and `rm -rf /tmp/mypeople-chain-test`.

---

PASS if:
- six notifications arrived in correct order
- each step used the actual previous output (not a hallucinated value)
- TOTAL matches N1 + N2 + N3 + N4 + N5
- the three workers are killed and the tmp dir is gone
