#!/usr/bin/env python3
# Assemble seeds/todo.seed.md from the tested artifacts (base64-embedded so the
# container gets byte-identical files — no heredoc escaping drift).
import base64, pathlib
D = pathlib.Path(__file__).resolve().parent
OUT = D.parent / "seeds" / "todo.seed.md"
def b64(p): return base64.b64encode((D / p).read_bytes()).decode()

FILES = {  # dest-in-runtime : source
    "$INSTALL_DIR/bin/todo-server.py": "todo-server.py",
    "$INSTALL_DIR/bin/todos.html":        "todos.html",
    "$INSTALL_DIR/bin/todo-reconcile":    "bin/todo-reconcile",
    "$INSTALL_DIR/bin/engineer-sim":      "bin/engineer-sim",
    "$INSTALL_DIR/bin/sim-stop-hook":     "bin/sim-stop-hook",
    "$INSTALL_DIR/todos/boss-rule4-todo.md": "boss-rule4-todo.md",
}
writes = []
for dest, src in FILES.items():
    writes.append(f'echo {b64(src)} | base64 -d > "{dest}"')
WRITE_BLOCK = "\n".join(writes)

SEED = f'''# SEED — TODO ("Priorities") · MyPeople sibling seed

> A *seed*: a portable spec + the exact install. Paste into a mypeople runtime (or a clean
> container) and it stands up the CEO's priority board that **is the Boss's work queue**:
> per-task done-condition (required) + work-to-done toggle + attachable proof + a ping state
> machine that always pings the Boss, + the Rule 4 doctrine that makes the Boss dispatch & verify.
>
> **Done = a clean container one-shots this seed and the `## Verify` block prints `VERIFY_OK`.**
> (mypeople doctrine: the seed is the artifact; the running system + Verify is the proof.)

## What it installs
- `bin/todo-server.py` — HTTP API + shared store (`board.v2.json`) + the PING STATE MACHINE.
  Endpoints: `GET /health /todos /todo/board`, `POST /todo/update /todo/brainstorm /todo/proof
  /todo/status /hook/stop`. Served at **:9900/todos**.
- `bin/todos.html` — the v2 board UI (live client; done-condition field, gated toggle, brainstorm,
  proof, live status).
- `bin/todo-reconcile` — the deterministic mechanics of Boss Rule 4 (assign+dispatch working/ON/
  unassigned; auto-verify machine-checkable done-conditions against proof; re-ping on fail).
- `bin/engineer-sim`, `bin/sim-stop-hook` — used ONLY by `## Verify` (a real runtime uses real
  `mp` engineers + the real Stop hook).
- `todos/boss-rule4-todo.md` — the Boss doctrine addendum (append to the Boss's CLAUDE.md).

## Data model & invariants (enforced server-side)
`Task{{ text, doneCondition(REQUIRED to enable toggle/done), brainstorm, workToDone, assignee,
state: needs_brainstorm->working->blocked->done (4-state; in-progress is always `working`), verified,
lastStatus, proofs[], subs[] }}`. `workToDone` rejected without `doneCondition`; not workable
before brainstorm; `done` rejected unless `verified`.

## The ping state machine (always pings the BOSS)
- **(a) unassigned active task** → cron every `PING_CRON_SEC` (prod **120s = 2 min**) pings the Boss.
- **(b) assigned task** → `IDLE_GRACE_SEC` (prod **60s**) after that engineer's Stop hook, if still
  idle → ping the Boss. Toggling ON also enqueues a Boss message immediately.
- **(c) assigned-but-idle WATCHDOG** → every `WATCHDOG_SEC` (60s) the server checks each
  working+assigned card's engineer. The nudge is gated on the engineer's **ACTUAL state, never
  just elapsed time.** First, the **ground-truth BUSY check** (the SAME signal `mp peek` uses):
  read the engineer's live `tmux` pane and look for the TUI busy marker `esc to interrupt`
  (Claude + Codex print it ONLY while a turn is actively running). If present → a turn is running
  RIGHT NOW → **BUSY, never nudged** — this is what stops false alarms on a deep-thinking / long
  silent turn (which burns ~no CPU and writes ~no transcript, so the older signals missed it).
  Only if NOT busy does it consider the staleness signals: mypeople `status.json` (last-Stop time),
  the Claude session transcript mtime, AND the engineer's **process tree** (`tmux` pane pid → child
  procs). Stalled := not-busy-marker AND stopped > `IDLE_STALL_SEC` (prod **180s = 3 min**) ago AND
  no transcript activity AND **no active job in the process tree** — where "active job" = a heavy
  child by name (ffmpeg/docker/git/build tools — the CLI client stays a pane child for the whole job)
  OR CPU burn **excluding the persistent MCP/browser stack**. So a 20-min silent ffmpeg render, a
  docker build, OR a long deep-thinking turn is NOT a false stall, but a genuinely-parked agent
  (turn ended, only its shell, nothing running) still is.
  Then it pings the Boss to re-engage/reassign. Unknown agent (no status file) → pinged (err toward
  nudging). This is what actually catches a parked engineer, since real engineers never POST
  `/hook/stop` (so (b) rarely fires on its own). `BUSY_CPU_PCT` / `BUSY_NAMES` tune the job check.
  **Respawn-aware:** idle-time is capped by the live session's age (the agent's `claude` process
  age via `ps etime`), so a re-spawned agent reusing a name isn't judged by the dead session's
  stale stop-timestamp (no "idle 1212m" false stall on a brand-new session).
- **`blocked` is exempt** — machines (a) and (c) both skip `blocked` cards. When an engineer's
  actionable work is done but the card is gated on a CEO window/decision, it signals
  `POST /todo/status {{id, ceoGated:true, lastStatus:"…"}}` → the card moves to `blocked` (still
  **not done**), so the Boss isn't false-nagged while it honestly waits on the human.

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
chmod +x "$INSTALL_DIR/bin/todo-server.py" "$INSTALL_DIR/bin/todo-reconcile" \\
         "$INSTALL_DIR/bin/engineer-sim" "$INSTALL_DIR/bin/sim-stop-hook"
```

## Step 2 — start the server
```bash
export TODO_HTML="$INSTALL_DIR/bin/todos.html"
# prod cadence: unassigned-card cron = 120s (2 min), idle-post-stop-hook = 60s (1 min).
pkill -f todo-server.py 2>/dev/null || true ; sleep 1
( cd "$INSTALL_DIR" && QUEUE_PORT="$QUEUE_PORT" TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" \\
    nohup python3 "$INSTALL_DIR/bin/todo-server.py" >"$INSTALL_DIR/todo.log" 2>&1 & )
sleep 1 ; curl -fs "127.0.0.1:$QUEUE_PORT/health" | grep -q '"ok"' && echo "todo up on :$QUEUE_PORT/todos"
```

## Step 3 — install the doctrine
Append `todos/boss-rule4-todo.md` to the Boss's `CLAUDE.md` (the Boss reads it next session):
```bash
cat "$TODO_DIR/boss-rule4-todo.md" >> "$INSTALL_DIR/boss-CLAUDE.md" 2>/dev/null || true
```

---

## Verify  (self-contained E2E — run from an independent shell; clean-container one-shot)
Proves: brainstorm gate, toggle⇒Boss-msg, ping machine (cron-unassigned + idle-post-stophook),
reconcile dispatch, proof-gated verify with a re-ping on bad proof, and the done-without-verified
invariant. Uses fast cadence + the sim engineer (a real runtime swaps in real `mp` engineers).
```bash
set -euo pipefail
INSTALL_DIR="${{INSTALL_DIR:-$HOME/mypeople}}"; BIN="$INSTALL_DIR/bin"
export TODO_DIR=/tmp/todo-verify QUEUE_PORT=9933 QUEUE_SECRET="" TODO_HOST=127.0.0.1:9933
export TODO_HTML="$BIN/todos.html" PING_CRON_SEC=2 IDLE_GRACE_SEC=2 WATCHDOG_SEC=999 TODO_TEST_SINK=1
rm -rf "$TODO_DIR"; pkill -f todo-server.py 2>/dev/null || true; sleep 1
( QUEUE_PORT=9933 TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" PING_CRON_SEC=2 IDLE_GRACE_SEC=2 WATCHDOG_SEC=999 \\
  TODO_TEST_SINK=1 QUEUE_SECRET="" nohup python3 "$BIN/todo-server.py" >/tmp/tv2.log 2>&1 & )
sleep 1
H=127.0.0.1:9933; J(){{ python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }}
G(){{ curl -fs $H/todo/board | python3 -c "import sys,json;print(json.load(sys.stdin)['tasks']['$1']['$2'])"; }}
RECON(){{ DISPATCH=sim ENGINEER_POOL=sim:eng-1 ENGINEER_SIM="$BIN/engineer-sim" TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-reconcile" >/dev/null; }}
RECONN(){{ DISPATCH=none ENGINEER_POOL=sim:eng-1 TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-reconcile" >/dev/null; }}  # assign-only (no async sim worker)
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
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$TID\\",\\"brainstorm\\":\\"write it\\",\\"promote\\":\\"working\\"}}" $H/todo/brainstorm >/dev/null
ck "$(G $TID state)" working "promote to working (4-state: no 'ready')"
RECONN; ck "$(G $TID assignee)" sim:eng-1 "reconcile assigns idle engineer (working+unassigned)"
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

# ── (c) assigned-but-idle WATCHDOG: a stalled assignee must ping the Boss (real engineers never POST /hook/stop) ──
WSTAT=/tmp/tv2-wd-status; WPROJ=/tmp/tv2-wd-proj; rm -rf "$WSTAT" "$WPROJ" /tmp/tv2-wd-board; mkdir -p "$WSTAT/mc-t" "$WPROJ/p"
printf '{{"agent_id":"t/eng-stalled","status":"idle","timestamp":"2020-01-01T00:00:00Z","session_id":"s1"}}' > "$WSTAT/mc-t/eng-stalled.json"
( QUEUE_PORT=9935 TODO_DIR=/tmp/tv2-wd-board TODO_HTML="$TODO_HTML" QUEUE_SECRET="" TODO_TEST_SINK=1 \\
  STATUS_DIR="$WSTAT" PROJECTS_DIR="$WPROJ" IDLE_STALL_SEC=2 WATCHDOG_SEC=1 STALL_REPING_SEC=1 \\
  PING_CRON_SEC=999 IDLE_GRACE_SEC=999 nohup python3 "$BIN/todo-server.py" >/tmp/tv2-wd.log 2>&1 & )
sleep 1; WH=127.0.0.1:9935
WTID=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"WD"}}' $WH/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$WTID\\",\\"doneCondition\\":\\"x\\"}}" $WH/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$WTID\\",\\"brainstorm\\":\\"b\\",\\"promote\\":\\"working\\"}}" $WH/todo/brainstorm >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$WTID\\",\\"workToDone\\":true,\\"assignee\\":\\"t/eng-stalled\\"}}" $WH/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$WTID\\",\\"state\\":\\"working\\"}}" $WH/todo/update >/dev/null
sleep 4
grep -q WATCHDOG /tmp/tv2-wd-board/boss-inbox.log || {{ echo "FAIL: watchdog did not ping for a stalled assignee"; exit 1; }}
[ "$(curl -fs $WH/todo/board | J "['tasks']['$WTID']['pingsToBoss']")" -gt 1 ] || {{ echo "FAIL: watchdog ping not incrementing"; exit 1; }}
# done-pending-CEO -> blocked: even with a STALLED assignee, a ceoGated/blocked card must NOT be nagged
WTID2=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"WD-blocked"}}' $WH/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$WTID2\\",\\"doneCondition\\":\\"x\\"}}" $WH/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$WTID2\\",\\"brainstorm\\":\\"b\\",\\"promote\\":\\"working\\"}}" $WH/todo/brainstorm >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$WTID2\\",\\"workToDone\\":true,\\"assignee\\":\\"t/eng-stalled\\"}}" $WH/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$WTID2\\",\\"ceoGated\\":true,\\"lastStatus\\":\\"done-pending-CEO\\"}}" $WH/todo/status | J "['state']" | grep -qx blocked || {{ echo "FAIL: ceoGated did not move card to blocked"; exit 1; }}
sleep 4
[ "$(grep -c "$WTID2.*WATCHDOG" /tmp/tv2-wd-board/boss-inbox.log)" -eq 0 ] || {{ echo "FAIL: watchdog nagged a blocked (ceoGated) card"; exit 1; }}

pkill -f todo-server.py 2>/dev/null || true
echo "VERIFY_OK: todo — board drives Boss dispatch, ping machine (cron-unassigned + idle-post-stophook + assigned-idle WATCHDOG -> Boss), proof-gated verify, re-ping. SEED one-shot in a clean container."
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
