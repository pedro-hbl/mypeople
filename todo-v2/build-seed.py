#!/usr/bin/env python3
# Assemble seeds/todo-v2.seed.md from the tested artifacts (base64-embedded so the
# container gets byte-identical files — no heredoc escaping drift).
import base64, pathlib
D = pathlib.Path(__file__).resolve().parent
OUT = D.parent / "seeds" / "todo-v2.seed.md"
def b64(p): return base64.b64encode((D / p).read_bytes()).decode()

FILES = {  # dest-in-runtime : source
    "$INSTALL_DIR/bin/todo-v2-server.py": "todo-v2-server.py",
    "$INSTALL_DIR/bin/todos.html":        "todos.html",
    "$INSTALL_DIR/bin/todo-reconcile":    "bin/todo-reconcile",
    "$INSTALL_DIR/bin/engineer-sim":      "bin/engineer-sim",
    "$INSTALL_DIR/bin/sim-stop-hook":     "bin/sim-stop-hook",
    "$INSTALL_DIR/todos/boss-rule4-todo-v2.md": "boss-rule4-todo-v2.md",
}
writes = []
for dest, src in FILES.items():
    writes.append(f'echo {b64(src)} | base64 -d > "{dest}"')
WRITE_BLOCK = "\n".join(writes)

SEED = f'''# SEED — TODO v2 ("Priorities") · MyPeople sibling seed

> A *seed*: a portable spec + the exact install. Paste into a mypeople runtime (or a clean
> container) and it stands up the CEO's priority board that **is the Boss's work queue**:
> per-task done-condition (required) + work-to-done toggle + attachable proof + a ping state
> machine that always pings the Boss, + the Rule 4 doctrine that makes the Boss dispatch & verify.
>
> **Done = a clean container one-shots this seed and the `## Verify` block prints `VERIFY_OK`.**
> (mypeople doctrine: the seed is the artifact; the running system + Verify is the proof.)

## What it installs
- `bin/todo-v2-server.py` — HTTP API + shared store (`board.v2.json`) + the PING STATE MACHINE.
  Endpoints: `GET /health /todos /todo/board`, `POST /todo/update /todo/brainstorm /todo/proof
  /todo/status /hook/stop`. Served at **:9900/todos**.
- `bin/todos.html` — the v2 board UI (live client; done-condition field, gated toggle, brainstorm,
  proof, live status).
- `bin/todo-reconcile` — the deterministic mechanics of Boss Rule 4 (assign+dispatch ready/ON/
  unassigned; auto-verify machine-checkable done-conditions against proof; re-ping on fail).
- `bin/engineer-sim`, `bin/sim-stop-hook` — used ONLY by `## Verify` (a real runtime uses real
  `mp` engineers + the real Stop hook).
- `todos/boss-rule4-todo-v2.md` — the Boss doctrine addendum (append to the Boss's CLAUDE.md).

## Data model & invariants (enforced server-side)
`Task{{ text, doneCondition(REQUIRED to enable toggle/done), brainstorm, workToDone, assignee,
state: needs_brainstorm->ready->dispatched->working->blocked->awaiting_verify->done, verified,
lastStatus, proofs[], subs[] }}`. `workToDone` rejected without `doneCondition`; not dispatchable
before `ready`; `done` rejected unless `verified`.

## The ping state machine (always pings the BOSS)
- **(a) unassigned active task** → cron every `PING_CRON_SEC` (prod **120s = 2 min**) pings the Boss.
- **(b) assigned task** → `IDLE_GRACE_SEC` (prod **60s**) after that engineer's Stop hook, if still
  idle → ping the Boss. Toggling ON also enqueues a Boss message immediately.

---

## Step 0 — env
```bash
export INSTALL_DIR="${{INSTALL_DIR:-$HOME/mypeople}}"
export TODO_DIR="$INSTALL_DIR/todos"
export QUEUE_PORT="${{QUEUE_PORT:-9900}}"
mkdir -p "$INSTALL_DIR/bin" "$TODO_DIR/proofs"
command -v python3 >/dev/null || {{ echo "need python3"; exit 1; }}
command -v curl    >/dev/null || {{ echo "need curl"; exit 1; }}
```

## Step 1 — write files (byte-exact, base64)
```bash
{WRITE_BLOCK}
chmod +x "$INSTALL_DIR/bin/todo-v2-server.py" "$INSTALL_DIR/bin/todo-reconcile" \\
         "$INSTALL_DIR/bin/engineer-sim" "$INSTALL_DIR/bin/sim-stop-hook"
```

## Step 2 — start the server
```bash
export TODO_HTML="$INSTALL_DIR/bin/todos.html"
# prod cadence: unassigned-card cron = 120s (2 min), idle-post-stop-hook = 60s (1 min).
pkill -f todo-v2-server.py 2>/dev/null || true ; sleep 1
( cd "$INSTALL_DIR" && QUEUE_PORT="$QUEUE_PORT" TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" \\
    nohup python3 "$INSTALL_DIR/bin/todo-v2-server.py" >"$INSTALL_DIR/todo-v2.log" 2>&1 & )
sleep 1 ; curl -fs "127.0.0.1:$QUEUE_PORT/health" | grep -q '"ok"' && echo "todo-v2 up on :$QUEUE_PORT/todos"
```

## Step 3 — install the doctrine
Append `todos/boss-rule4-todo-v2.md` to the Boss's `CLAUDE.md` (the Boss reads it next session):
```bash
cat "$TODO_DIR/boss-rule4-todo-v2.md" >> "$INSTALL_DIR/boss-CLAUDE.md" 2>/dev/null || true
```

---

## Verify  (self-contained E2E — run from an independent shell; clean-container one-shot)
Proves: brainstorm gate, toggle⇒Boss-msg, ping machine (cron-unassigned + idle-post-stophook),
reconcile dispatch, proof-gated verify with a re-ping on bad proof, and the done-without-verified
invariant. Uses fast cadence + the sim engineer (a real runtime swaps in real `mp` engineers).
```bash
set -euo pipefail
INSTALL_DIR="${{INSTALL_DIR:-$HOME/mypeople}}"; BIN="$INSTALL_DIR/bin"
export TODO_DIR=/tmp/todo-v2-verify QUEUE_PORT=9933 QUEUE_SECRET="" TODO_HOST=127.0.0.1:9933
export TODO_HTML="$BIN/todos.html" PING_CRON_SEC=2 IDLE_GRACE_SEC=2 TODO_TEST_SINK=1
rm -rf "$TODO_DIR"; pkill -f todo-v2-server.py 2>/dev/null || true; sleep 1
( QUEUE_PORT=9933 TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" PING_CRON_SEC=2 IDLE_GRACE_SEC=2 \\
  TODO_TEST_SINK=1 QUEUE_SECRET="" nohup python3 "$BIN/todo-v2-server.py" >/tmp/tv2.log 2>&1 & )
sleep 1
H=127.0.0.1:9933; J(){{ python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }}
G(){{ curl -fs $H/todo/board | python3 -c "import sys,json;print(json.load(sys.stdin)['tasks']['$1']['$2'])"; }}
RECON(){{ DISPATCH=sim ENGINEER_POOL=sim:eng-1 ENGINEER_SIM="$BIN/engineer-sim" TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-reconcile" >/dev/null; }}
ck(){{ [ "$1" = "$2" ] || {{ echo "FAIL: $3 (got '$1' want '$2')"; exit 1; }}; }}

curl -fs $H/health | grep -q '"ok"'
curl -fs $H/todos  | grep -qi priorities
TID=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"E2E"}}' $H/todo/update | J "['id']")
COND="file /tmp/tv2-proof.txt contains OK-SEED"; rm -f /tmp/tv2-proof.txt
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"workToDone\\":true}}" $H/todo/update | J "['error']" | grep -qi doneCondition  # gated
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"doneCondition\\":\\"$COND\\"}}" $H/todo/update >/dev/null
RECON; ck "$(G $TID state)" needs_brainstorm "brainstorm gate blocks dispatch"
P0=$(G $TID pingsToBoss)
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"workToDone\\":true}}" $H/todo/update | J "['bossEnqueued']" | grep -qi true  # toggle->boss msg
sleep 5; [ "$(G $TID pingsToBoss)" -gt "$P0" ] || {{ echo "FAIL: cron didn't ping boss (unassigned)"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$TID\\",\\"brainstorm\\":\\"write it\\",\\"promote\\":\\"ready\\"}}" $H/todo/brainstorm >/dev/null
ck "$(G $TID state)" ready "promote to ready"
RECON; ck "$(G $TID state)" dispatched "reconcile assigned+dispatched"
# bad proof -> re-ping, not done
SIM_FAIL=1 TODO_HOST=$H python3 "$BIN/engineer-sim" $TID; sleep 1; RECON
ck "$(G $TID verified)" False "bad proof not verified"; [ "$(G $TID state)" != done ] || {{ echo FAIL bad-proof-done; exit 1; }}
G $TID lastStatus | grep -qi "not ready"
# idle-post-stophook pings the boss for the assigned task
B0=$(G $TID pingsToBoss); "$BIN/sim-stop-hook" sim:eng-1 --idle >/dev/null; sleep 4
[ "$(G $TID pingsToBoss)" -gt "$B0" ] || {{ echo "FAIL: idle-post-stophook didn't ping"; exit 1; }}
# good proof -> verify -> done
TODO_HOST=$H python3 "$BIN/engineer-sim" $TID; sleep 1; RECON
ck "$(G $TID state)" done "verified->done"; ck "$(G $TID verified)" True "verified flag"
# invariant
curl -fs $H/todo/board | python3 -c "import sys,json;b=json.load(sys.stdin);exit(0 if not [t for t in b['tasks'].values() if t['state']=='done' and not t['verified']] else 1)"
pkill -f todo-v2-server.py 2>/dev/null || true
echo "VERIFY_OK: todo-v2 — board drives Boss dispatch, ping machine (cron+idle->Boss), proof-gated verify, re-ping. SEED one-shot in a clean container."
```

## Failure modes folded in
- Writes 403 → a `QUEUE_SECRET` is set; the browser page gets it injected at `/todos` serve time;
  API clients must send `X-Queue-Secret`. (Verify runs with an empty secret.)
- `done` won't set without `verified`; toggle won't enable without `doneCondition` — by design.
- Real runtime: set `TODO_TEST_SINK` unset and ensure `mp` is on PATH so Boss pings use
  `mp send main:Boss`; dispatch uses real engineers (`DISPATCH=mp`).
'''

OUT.write_text(SEED)
print(f"wrote {OUT} ({len(SEED)} bytes)")
