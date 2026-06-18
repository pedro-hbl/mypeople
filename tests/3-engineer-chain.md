# 3-engineer chain test

A multi-agent orchestration test: the Boss dispatches work to two workers and verifies the result.

## Prerequisites

- Queue server running.
- Boss session running in Kimi web with `agents/boss-kimi.yaml`.

## Steps

```bash
HOST=$(hostname -s)
mp spawn "$HOST"/chain:Boss --master --cwd /tmp
mp spawn "$HOST"/chain:adder --cwd /tmp --boss "$HOST"/chain:Boss
mp spawn "$HOST"/chain:multiplier --cwd /tmp --boss "$HOST"/chain:Boss

mp send "$HOST"/chain:adder "Compute 3 + 4 and reply with just the integer result."
# Wait for adder to finish and Boss to be notified.
sleep 8

mp send "$HOST"/chain:multiplier "Multiply 7 by 5 and reply with just the integer result."
sleep 8

mp status | grep -E 'chain:(adder|multiplier).*idle'
mp peek "$HOST"/chain:Boss | grep -q "AGENT NOTIFICATION"
```

## Verify

- Both workers reach `idle` state.
- The Boss history contains `AGENT NOTIFICATION` lines for both workers.
