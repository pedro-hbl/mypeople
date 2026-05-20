# Parallel fan-out test — 2-3 min

Five engineers, five independent tasks, dispatched in parallel. Tests that the Boss can handle out-of-order notifications and aggregate results without serializing.

Where the chain test ([`3-engineer-chain.md`](3-engineer-chain.md)) proves strict deps work, this one proves parallel fan-out works.

Paste this whole block into the Boss's claude pane:

---

Create `/tmp/mypeople-fanout-test`.

Spawn FIVE engineers (`--boss yourself`, `--cwd /tmp/mypeople-fanout-test`): eng-1 through eng-5. After all five are spawned and idle, dispatch ALL FIVE tasks IN PARALLEL — do NOT wait for one notification before sending the next. Send all five sends, THEN wait for all notifications to arrive.

Tasks (each engineer gets exactly ONE message — these are independent, no deps between engineers):

- eng-1: "in ONE sentence, name a famous mathematician and one thing they're known for"
- eng-2: "in ONE sentence, name a famous composer and one thing they're known for"
- eng-3: "in ONE sentence, name a famous athlete and one thing they're known for"
- eng-4: "in ONE sentence, name a famous chef and one thing they're known for"
- eng-5: "in ONE sentence, name a famous scientist and one thing they're known for"

As notifications arrive (possibly out of order), do NOT respond to each one individually — collect them until you have all five.

Once all five [AGENT NOTIFICATION] lines have landed, output a single block:

```
PARALLEL FAN-OUT RESULTS

mathematician (eng-1): <reply>
composer      (eng-2): <reply>
athlete       (eng-3): <reply>
chef          (eng-4): <reply>
scientist     (eng-5): <reply>

Notifications received in order: <list of eng-N in arrival order>
```

Then kill all five engineers and `rm -rf /tmp/mypeople-fanout-test`.

---

PASS if:
- All five engineers spawned successfully
- All five sends were issued before the first notification arrived (parallel dispatch, not serial)
- All five notifications were collected and correlated to the right agent
- The "Notifications received in order" line is NOT identical to "1, 2, 3, 4, 5" — different turn lengths mean out-of-order arrivals are likely
- All engineers killed and tmp dir gone
