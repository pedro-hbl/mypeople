# Smoke test

30-second sanity check for the Kimi-native mypeople runtime.

## Prerequisites

- Queue server is running: `./scripts/start-queue-server.sh`
- `mp` is on PATH: `mp status` works.

## Steps

```bash
HOST=$(hostname -s)
mp spawn "$HOST"/smoke:w1 --cwd /tmp
mp status | grep -q 'smoke:w1.*idle'
mp send "$HOST"/smoke:w1 "Reply with the single word PONG only."
sleep 5
mp peek "$HOST"/smoke:w1 | grep -q 'state=idle'
mp kill "$HOST"/smoke:w1
mp status | grep -q 'smoke:w1.*dead'
```

## Verify

All commands exit 0 and `mp status` reflects the expected states.
