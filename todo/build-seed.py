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
    "$INSTALL_DIR/bin/todo-brainstorm":   "bin/todo-brainstorm",
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
- `bin/todo-server.py` — HTTP API + shared store (`board.v2.json`) + the PING STATE MACHINE +
  the **WhatsApp last-hop drain** (slice e). Endpoints: `GET /health /todos /todo/board /todo/attach
  /todo/wa`, `POST /todo/update /todo/brainstorm /todo/proof /todo/status /todo/comment /todo/answer
  /todo/wa/test /todo/wa/drain /hook/stop`. Served at **:9900/todos**.
- `bin/todos.html` — the board UI (live client; done-condition field, gated toggle, brainstorm,
  live status; **filter + sort by status**; **watchable proof on the board** — mp4 proofs play
  inline via a `<video controls>` player served Range-aware from `/todo/proof/<tid>/<file>`, png
  screenshots shown inline). **Issue-style card view**: click a task (the ⤢ control, or the card
  body) to open a GitHub-issue-style modal with the FULL durable message history for that task —
  the opening event, AI/engineer + CEO comments, engineer status updates, state transitions, the
  brainstorm artifact (pinned), and image/video proofs, all merged by timestamp. The card streams
  new activity live and has a CEO comment composer. **Unread/new-message indication**: the board
  shows a separate `new` count when non-CEO timeline events (engineer/AI comments, status/state
  events, or proofs) arrive after the CEO's last read/open of that card; opening the issue card
  marks those events read in the CEO browser, independent of review/blocked/done state. Every engineer status
  update and state change is appended to the durable `comments[]` thread automatically (so the
  history survives, unlike `lastStatus` which is overwritten); the CEO/AI post free-text via
  `POST /todo/comment {{task_id, body, by}}`. **Click-the-linked-engineer → attach**: the assignee
  chip (on the board card AND in the issue card's header) is clickable — it opens that engineer's
  LIVE terminal in a new tab via ttyd, the SAME effect as the HUD attach. `GET /todo/attach?agent=
  <host/session:tab>` resolves the tmux target (`mc-<session>:<tab>`) and the host's ttyd
  `attach_base` from the mypeople queue-server's `/clients` (server-side, so the queue secret never
  reaches the browser); the page assembles `<base>/?arg=-t&arg=mc-<session>:<tab>` with the SAME
  `<location.hostname>:7681` fallback the HUD uses for a host that advertises no base. Needs the
  mypeople queue reachable at `QUEUE_URL` (default `http://127.0.0.1:9900`); without it, attach
  falls back to the local ttyd.
- `bin/todo-reconcile` — the deterministic mechanics of Boss Rule 4 (assign+dispatch working/ON/
  unassigned; auto-verify machine-checkable done-conditions against proof; re-ping on fail).
- `bin/todo-brainstorm` — the **brainstorm-gate generator**. For each `needs_brainstorm` task not
  yet brainstormed, it runs a REAL brainstorm (headless `claude -p`, YC office-hours method) that
  judges whether the task is under-specified and, if so, emits the clarifying QUESTIONS an engineer
  must have answered before starting; these post to the card and the task stays non-workable until
  the CEO answers them. A task judged already-clear gets zero questions → immediately promotable.
  The Boss runs it on the `needs_brainstorm` ping, like `todo-reconcile`. `BRAINSTORM_CMD=stub`
  gives a deterministic offline generator (used by `## Verify`); `BRAINSTORM_CMD`/`BRAINSTORM_MODEL`
  tune the real one.
- `bin/engineer-sim`, `bin/sim-stop-hook` — used ONLY by `## Verify` (a real runtime uses real
  `mp` engineers + the real Stop hook).
- `todos/boss-rule4-todo.md` — the Boss doctrine addendum (append to the Boss's CLAUDE.md).

## Data model & invariants (enforced server-side)
`Task{{ text, doneCondition(REQUIRED to enable toggle/done), brainstorm, questions[], brainstormAsked,
workToDone, assignee, state: needs_brainstorm->working->review->done (+blocked side-exit; in-progress is
always `working`; `review` = engineer done + Boss-verified, awaiting CEO sign-off, Rule 21 — engineer-nudge-exempt),
verified, lastStatus, proofs[], comments[], subs[] }}`. `workToDone` rejected without `doneCondition`.
**`done` is CEO-only (Rule 21):** only `by:"CEO"` may set `done` — one click, from ANY state, and it
auto-sets `verified`. The AI/engineer can move a card UP TO `review` (for CEO sign-off) but the server
REJECTS `done` from any non-CEO writer (the gate stops the AI auto-closing unready work, never the CEO).
`comments[]` is the durable issue-style thread (`kind`: comment |
status | state | brainstorm) the card view renders — append-only; the server auto-appends an event on
every engineer status update, state transition, and brainstorm save.

**WhatsApp last-hop drain + CEO-watchdog (slice e).** A `whatsapp` queue PARTICIPANT lives in the
server. **Blocked-on-CEO** = `state==review` (awaiting the CEO's DONE) OR `state==blocked` (ceoGated —
awaiting a CEO decision/answers) OR a `needs_brainstorm` task with unanswered questions (awaiting the
CEO's answers). ALL of these ping the CEO's WhatsApp (brainstorm cards list their open questions inline);
the in-app cron does NOT nudge the Boss for brainstorm-triage — that hands off to this WhatsApp ping. The **CEO-watchdog** (cron, every
`WA_WATCHDOG_SEC`=**5 min** — no busy-gate; it IS the CEO) sends the CEO's **personal WhatsApp** ONE
**consolidated digest** listing every blocked card — grouped *Review — needs your DONE* /
*Brainstorm — needs your answers*, each line = the card title + a tappable **deep-link**
(`WA_BOARD_URL#card/<id>`, which opens that exact card on the board). It fires only while ≥1 card is
blocked, **repeats every 5 min**, **updates as cards clear**, and **stops** when none remain (no
per-card spam, no "how to stop" text). `WA_REPING_SEC`=270 (just under the tick) guarantees one digest
per tick even if a mutation also triggers a reconcile. A **drain loop** hands the digest to the **LAST
HOP** — the containerized Hermes bridge (`WA_SEND_CMD` posts `{{chatId: WA_CHAT_JID, message}}` to
Hermes `/send`, default `docker exec -i hermes-wa curl … /send -d @-`) — and records the returned
`messageId`. The board UI deep-links: opening `…/todos#card/<id>` opens that card directly. `WA_DRAIN=0`
disables the last hop (Verify uses a stub send). `POST /todo/wa/test {{text}}` enqueues a one-off;
`GET /todo/wa` inspects the outbox. The board is the source of truth; WhatsApp is just the final hop.

**Brainstorm gate (slice d).** A new task starts `needs_brainstorm` and is NOT workable. `bin/todo-brainstorm`
generates clarifying `questions[]` (office-hours method, via `claude -p`) which surface in the card AS
questions to the CEO. The CEO answers each via `POST /todo/answer {{task_id, qid, answer}}`; the resolved
Q&A folds into the durable brainstorm artifact. `POST /todo/brainstorm {{id, promote:"working"}}` is REJECTED
until every question is answered (or, for a clear task, a brainstorm artifact exists) — so an under-specified
task can never be silently worked. When the last question is answered the Boss is pinged ("gate cleared").

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
         "$INSTALL_DIR/bin/todo-brainstorm" "$INSTALL_DIR/bin/engineer-sim" "$INSTALL_DIR/bin/sim-stop-hook"
```

## Step 2 — start the server
```bash
export TODO_HTML="$INSTALL_DIR/bin/todos.html"
# prod cadence: unassigned-card cron = 120s (2 min), idle-post-stop-hook = 60s (1 min).
# WhatsApp digest deep-links (slice e): expose the board over HTTPS at the *.ts.net MagicDNS name via
# `tailscale serve`. This is the ONLY form verified to BOTH render as a tappable link in WhatsApp AND
# actually open in a browser: a raw IP:port does not linkify, and plain http://<name>:<port> often
# fails to open (browser HTTPS-upgrade / secure-DNS bypassing MagicDNS). `tailscale serve` gives a
# valid-cert HTTPS URL on 443 (no port) that resolves + opens. Fall back to http://<host>:<port> only
# if serve/HTTPS is unavailable (then verify reachability before trusting it).
# PORT ISOLATION (do not clobber): the board OWNS `tailscale serve` on :443 (tailnet-only — its /todos
# injects the QUEUE_SECRET, so it must never be Funnel-exposed). Any co-located PUBLIC service (e.g. a
# brain webhook) must use its OWN Funnel port (8443 or 10000), NEVER Funnel :443 — a Funnel on :443
# replaces the board's serve handler AND would expose the secret. serve/funnel are per-port, so the
# board (:443 serve) and a brain (:8443 funnel) coexist without a shared config.
TSHOST="$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null)"
if [ -n "$TSHOST" ]; then
  tailscale serve --bg "$QUEUE_PORT" >/dev/null 2>&1 || true   # https://$TSHOST/ -> 127.0.0.1:$QUEUE_PORT
  tailscale cert "$TSHOST" >/dev/null 2>&1 || true             # provision the cert (first issuance)
  if curl -fsS --max-time 25 "https://$TSHOST/health" >/dev/null 2>&1; then
    export WA_BOARD_URL="${{WA_BOARD_URL:-https://$TSHOST/todos}}"        # verified: renders AND opens
  else
    export WA_BOARD_URL="${{WA_BOARD_URL:-http://$TSHOST:$QUEUE_PORT/todos}}"
  fi
else
  TSIP="$(tailscale ip -4 2>/dev/null | head -1)"
  [ -n "$TSIP" ] && export WA_BOARD_URL="${{WA_BOARD_URL:-http://$TSIP:$QUEUE_PORT/todos}}"
fi
pkill -f todo-server.py 2>/dev/null || true ; sleep 1
( cd "$INSTALL_DIR" && QUEUE_PORT="$QUEUE_PORT" TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" WA_BOARD_URL="${{WA_BOARD_URL:-}}" \\
    nohup python3 "$INSTALL_DIR/bin/todo-server.py" >"$INSTALL_DIR/todo.log" 2>&1 & )
sleep 1 ; curl -fs "127.0.0.1:$QUEUE_PORT/health" | grep -q '"ok"' && echo "todo up on :$QUEUE_PORT/todos${{WA_BOARD_URL:+ (digest links -> $WA_BOARD_URL)}}"
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
# slice e: exercise the WhatsApp participant with a STUB last-hop (no Hermes/docker needed offline)
export WA_DRAIN=1 WA_DRAIN_SEC=1 WA_WATCHDOG_SEC=2 WA_REPING_SEC=1 WA_BOARD_URL="http://board.test/todos" WA_CHAT_JID="15550000000@s.whatsapp.net"
export WA_SEND_CMD="cat >/dev/null; printf '{{\\"success\\":true,\\"messageId\\":\\"verify\\"}}'"
rm -rf "$TODO_DIR"; pkill -f todo-server.py 2>/dev/null || true; sleep 1
( QUEUE_PORT=9933 TODO_DIR="$TODO_DIR" TODO_HTML="$TODO_HTML" PING_CRON_SEC=2 IDLE_GRACE_SEC=2 WATCHDOG_SEC=999 \\
  TODO_TEST_SINK=1 QUEUE_SECRET="" WA_DRAIN=1 WA_DRAIN_SEC=1 WA_WATCHDOG_SEC=2 WA_REPING_SEC=1 WA_BOARD_URL="$WA_BOARD_URL" WA_CHAT_JID="$WA_CHAT_JID" WA_SEND_CMD="$WA_SEND_CMD" \\
  nohup python3 "$BIN/todo-server.py" >/tmp/tv2.log 2>&1 & )
# wait for the server to actually answer (a loaded/slow container needs more than a fixed 1s)
for i in 1 2 3 4 5 6 7 8 9 10; do curl -fs "127.0.0.1:9933/health" >/dev/null 2>&1 && break; sleep 1; done
H=127.0.0.1:9933; J(){{ python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }}
G(){{ curl -fs $H/todo/board | python3 -c "import sys,json;print(json.load(sys.stdin)['tasks']['$1']['$2'])"; }}
RECON(){{ DISPATCH=sim ENGINEER_POOL=sim:eng-1 ENGINEER_SIM="$BIN/engineer-sim" TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-reconcile" >/dev/null; }}
RECONN(){{ DISPATCH=none ENGINEER_POOL=sim:eng-1 TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-reconcile" >/dev/null; }}  # assign-only (no async sim worker)
ck(){{ [ "$1" = "$2" ] || {{ echo "FAIL: $3 (got '$1' want '$2')"; exit 1; }}; }}

curl -fs $H/health | grep -q '"ok"'
curl -fs $H/todos  | grep -qi priorities
TID=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"E2E"}}' $H/todo/update | J "['id']")
# a CREATED task pings the Boss immediately (no work-to-done needed) — it must never sit silently unworked
[ "$(G $TID pingsToBoss)" -ge 1 ] || {{ echo "FAIL: creating a task did not ping the Boss (would sit silently dead)"; exit 1; }}
grep -q "new task created" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: create did not enqueue a brainstorm/triage ping to the Boss"; exit 1; }}
# test/demo/proof fixtures are EXEMPT — a [test]-prefixed card fires NO create-ping (no Boss noise)
XT=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"[test] fixture"}}' $H/todo/update | J "['id']")
[ "$(G $XT pingsToBoss)" -eq 0 ] || {{ echo "FAIL: a [test] fixture pinged the Boss on create (exemption broken)"; exit 1; }}
XT2=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"flagged fixture","test":true}}' $H/todo/update | J "['id']")
[ "$(G $XT2 pingsToBoss)" -eq 0 ] || {{ echo "FAIL: a test:true fixture pinged the Boss on create (exemption broken)"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$XT\\"}}" $H/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$XT2\\"}}" $H/todo/update >/dev/null
echo "  (create+exempt) OK: real task -> Boss pinged on create; [test]/test:true fixture -> NO ping"
COND="file /tmp/tv2-proof.txt contains OK-SEED"; rm -f /tmp/tv2-proof.txt
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"workToDone\\":true}}" $H/todo/update | J "['error']" | grep -qi doneCondition  # gated
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"doneCondition\\":\\"$COND\\"}}" $H/todo/update >/dev/null
RECON; ck "$(G $TID state)" needs_brainstorm "brainstorm gate blocks dispatch"
P0=$(G $TID pingsToBoss)
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"workToDone\\":true}}" $H/todo/update | J "['bossEnqueued']" | grep -qi true  # toggle->boss msg
sleep 5; [ "$(G $TID pingsToBoss)" -gt "$P0" ] || {{ echo "FAIL: cron didn't ping boss (unassigned)"; exit 1; }}
# work-to-done debounce (server side): a REDUNDANT workToDone:true (already ON) must NOT re-ping the Boss
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$TID\\",\\"workToDone\\":true}}" $H/todo/update | J "['bossEnqueued']" | grep -qx False || {{ echo "FAIL: redundant work-to-done ON re-pinged the Boss (no debounce/transition-guard)"; exit 1; }}
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
# good proof -> AI verifies + moves UP TO review (never done); CEO signs off -> done in one click
TODO_HOST=$H python3 "$BIN/engineer-sim" $TID; sleep 1; RECON
ck "$(G $TID state)" review "reconcile verifies -> review (AI can move up to review, never done)"; ck "$(G $TID verified)" True "verified flag"
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$TID\\",\\"state\\":\\"done\\"}}" $H/todo/status | J "['error']" | grep -qi "only the CEO" || {{ echo "FAIL: AI/engineer was able to set done (no by:CEO)"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$TID\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
ck "$(G $TID state)" done "CEO sign-off -> done (one click)"; ck "$(G $TID verified)" True "verified flag"
# invariant
curl -fs $H/todo/board | python3 -c "import sys,json;b=json.load(sys.stdin);exit(0 if not [t for t in b['tasks'].values() if t['state']=='done' and not t['verified']] else 1)"

# ── (b) two-way comments: a CEO comment is relayed to the BOSS (chain of command); engineer replies thread back ──
CT=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"comment routing card"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$CT\\",\\"assignee\\":\\"main:eng-7\\"}}" $H/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$CT\\",\\"body\\":\\"prioritize the mobile layout\\",\\"by\\":\\"CEO\\"}}" $H/todo/comment | J "['routed']" | grep -qi boss || {{ echo "FAIL: CEO comment not routed to the Boss"; exit 1; }}
grep -qF "MP_SEND -> main:Boss :: [CEO comment on card $CT" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: Boss inbox missing the relayed CEO comment"; exit 1; }}
BEFORE=$(grep -cF "CEO comment on card $CT" "$TODO_DIR/boss-inbox.log")
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$CT\\",\\"body\\":\\"on it — mobile first\\",\\"by\\":\\"main:eng-7\\"}}" $H/todo/comment >/dev/null
curl -fs $H/todo/board | python3 -c "import sys,json;cs=json.load(sys.stdin)['tasks']['$CT']['comments'];exit(0 if any(c['by']=='main:eng-7' and 'mobile first' in c['body'] for c in cs) else 1)" || {{ echo "FAIL: engineer reply did not thread back into the card"; exit 1; }}
[ "$(grep -cF "CEO comment on card $CT" "$TODO_DIR/boss-inbox.log")" -eq "$BEFORE" ] || {{ echo "FAIL: engineer reply wrongly relayed to the Boss (engineer replies should only thread)"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$CT\\"}}" $H/todo/update >/dev/null   # tidy the test card (else the (d) brainstorm sweep would gate it)
echo "  (b) two-way comments OK: CEO->Boss relay (chain of command); engineer reply threads back into the card; engineer reply not re-relayed"

# ── (b2) comment-on-review = MORE WORK: a CEO comment on a 'review' card auto-kicks it review->working (still relays to Boss) ──
KR=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"review kick card"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$KR\\",\\"verified\\":true}}" $H/todo/status >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$KR\\",\\"state\\":\\"review\\"}}" $H/todo/status >/dev/null
ck "$(G $KR state)" review "card is in review"
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$KR\\",\\"body\\":\\"needs another pass on X\\",\\"by\\":\\"CEO\\"}}" $H/todo/comment | J "['kicked']" | grep -qi true || {{ echo "FAIL: CEO comment on review card did not report kicked"; exit 1; }}
ck "$(G $KR state)" working "CEO comment on review -> auto-kicked to working"
grep -qF "CEO comment on card $KR" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: kicked comment not relayed to Boss"; exit 1; }}
# an engineer comment on a review card does NOT kick it (only the CEO's does)
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$KR\\",\\"verified\\":true}}" $H/todo/status >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$KR\\",\\"state\\":\\"review\\"}}" $H/todo/status >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$KR\\",\\"body\\":\\"status note\\",\\"by\\":\\"main:eng-2\\"}}" $H/todo/comment >/dev/null
ck "$(G $KR state)" review "engineer comment does NOT kick a review card"
# edge case (d) no-thrash: a CEO comment kicks review->working ONCE; a 2nd CEO comment doesn't re-kick (already working)
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$KR\\",\\"body\\":\\"first CEO note\\",\\"by\\":\\"CEO\\"}}" $H/todo/comment >/dev/null
ck "$(G $KR state)" working "1st CEO comment kicks review->working"
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$KR\\",\\"body\\":\\"second CEO note\\",\\"by\\":\\"CEO\\"}}" $H/todo/comment | J "['kicked']" | grep -qi false || {{ echo "FAIL: 2nd CEO comment re-kicked (thrash)"; exit 1; }}
ck "$(G $KR state)" working "2nd CEO comment on a working card does NOT thrash state"
# edge case (a) CEO comment on a non-review card (working) stays working BUT still relays to the Boss
BEFOREK=$(grep -cF "CEO comment on card $KR" "$TODO_DIR/boss-inbox.log")
curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$KR\\",\\"body\\":\\"more direction\\",\\"by\\":\\"CEO\\"}}" $H/todo/comment >/dev/null
ck "$(G $KR state)" working "CEO comment on a working card leaves it working"
[ "$(grep -cF "CEO comment on card $KR" "$TODO_DIR/boss-inbox.log")" -gt "$BEFOREK" ] || {{ echo "FAIL: CEO comment on a working card was not relayed to the Boss"; exit 1; }}
# ── manual status-change control (what the card dropdown posts): move a card BACK review->working ──
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$KR\\",\\"state\\":\\"working\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
ck "$(G $KR state)" working "manual status control moves review->working"
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$KR\\"}}" $H/todo/update >/dev/null
# CEO marks done in ONE click from ANY state (working/needs_brainstorm/blocked/review); AI/engineer NEVER can
for ST in working needs_brainstorm blocked review; do
  CD=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"done-from"}}' $H/todo/update | J "['id']")
  curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$CD\\",\\"state\\":\\"$ST\\"}}" $H/todo/status >/dev/null
  ck "$(G $CD state)" "$ST" "seeded in $ST"
  curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$CD\\",\\"state\\":\\"done\\",\\"by\\":\\"main:eng-1\\"}}" $H/todo/status | J "['error']" | grep -qi "only the CEO" || {{ echo "FAIL: AI/engineer set done from $ST (must be blocked)"; exit 1; }}
  ck "$(G $CD state)" "$ST" "AI done-attempt left state unchanged ($ST)"
  curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$CD\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status | J "['state']" | grep -qx done || {{ echo "FAIL: CEO could not mark done from $ST in one click"; exit 1; }}
  ck "$(G $CD state)" done "CEO one-click done from $ST"
  ck "$(G $CD verified)" True "CEO done auto-verifies from $ST"
  curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$CD\\"}}" $H/todo/update >/dev/null
done
echo "  (b2) status control OK: CEO comment on review auto-kicks ->working; manual review->working; CEO marks done ONE-CLICK from working/needs_brainstorm/blocked/review; AI/engineer can NEVER set done (review max)"

# ── (f) AUTO-RETIRE on CEO DONE: when the CEO marks a card DONE, the card's ASSIGNEE engineer has finished its
#     task and is retired (`mp kill <assignee>`) + the Boss is told it finished. Offline (TEST_SINK) the kill is
#     audit-only, so we assert the retire HOOK: the boss-inbox RETIRE line, the Boss event, the threaded card comment.
#     Edge cases proven: fires ONLY on ->done (not other transitions); transition-guarded (no re-fire on re-save);
#     never targets a non-assignee (only the card's assignee); no-assignee done = clean no-op (no kill).
RT=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"retire-me"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$RT\\",\\"assignee\\":\\"sim:eng-9\\"}}" $H/todo/update >/dev/null
ck "$(G $RT assignee)" sim:eng-9 "retire card carries the assignee"
# negative: a NON-done transition (->review) must NOT retire the assignee
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$RT\\",\\"state\\":\\"review\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
! grep -qF "RETIRE task $RT" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: a non-done transition retired the assignee (must fire ONLY on ->done)"; exit 1; }}
# the CEO marks DONE -> retire fires exactly once, targeting THIS card's assignee, and tells the Boss
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$RT\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
ck "$(G $RT state)" done "CEO marks the retire card done"
grep -qF "RETIRE task $RT DONE -> mp kill sim:eng-9" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: ->done did not fire the auto-retire (mp kill) for the card's assignee"; exit 1; }}
grep -qF "auto-retired assignee sim:eng-9" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: the Boss was not told the task finished + who was retired"; exit 1; }}
curl -fs $H/todo/board | python3 -c "import sys,json;cs=json.load(sys.stdin)['tasks']['$RT']['comments'];exit(0 if any('auto-retire' in c['body'] and 'sim:eng-9' in c['body'] for c in cs) else 1)" || {{ echo "FAIL: the retirement was not threaded into the card history"; exit 1; }}
# transition-guarded: re-saving an ALREADY-done card must NOT re-retire (only the ->done transition fires)
RC1=$(grep -cF "RETIRE task $RT DONE" "$TODO_DIR/boss-inbox.log")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$RT\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
[ "$(grep -cF "RETIRE task $RT DONE" "$TODO_DIR/boss-inbox.log")" -eq "$RC1" ] || {{ echo "FAIL: re-saving an already-done card re-fired the retire (not transition-guarded)"; exit 1; }}
# edge: a card with NO assignee marked done -> clean no-op (no kill), logged as such
NR=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"no-assignee done"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$NR\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
grep -qF "RETIRE task $NR marked DONE but had no assignee" "$TODO_DIR/boss-inbox.log" || {{ echo "FAIL: done with no assignee did not log a clean no-op"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$RT\\"}}" $H/todo/update >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$NR\\"}}" $H/todo/update >/dev/null
echo "  (f) auto-retire OK: CEO ->done retires the card's assignee (mp kill; audit-only offline) + tells the Boss + threads the card; non-done transition does NOT retire; re-save doesn't re-fire; no-assignee done = clean no-op"

# ── (d) BRAINSTORM GATE: under-specified task -> generated questions -> NON-workable until answered ──
BTID=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"make the dashboard better"}}' $H/todo/update | J "['id']")
BRAINSTORM_CMD=stub TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-brainstorm" >/dev/null   # real runtime: BRAINSTORM_CMD='claude -p'
ck "$(G $BTID brainstormAsked)" True "brainstorm worker ran"
NQ=$(curl -fs $H/todo/board | python3 -c "import sys,json;print(len(json.load(sys.stdin)['tasks']['$BTID']['questions']))")
[ "$NQ" -ge 1 ] || {{ echo "FAIL: under-specified task generated no questions"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$BTID\\",\\"promote\\":\\"working\\"}}" $H/todo/brainstorm | J "['error']" | grep -qi unanswered || {{ echo "FAIL: gate did not block promote while unanswered"; exit 1; }}
for q in $(curl -fs $H/todo/board | python3 -c "import sys,json;print(' '.join(x['id'] for x in json.load(sys.stdin)['tasks']['$BTID']['questions']))"); do
  curl -fs -H 'Content-Type: application/json' -d "{{\\"task_id\\":\\"$BTID\\",\\"qid\\":\\"$q\\",\\"answer\\":\\"because reasons\\"}}" $H/todo/answer >/dev/null
done
ck "$(curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$BTID\\",\\"promote\\":\\"working\\"}}" $H/todo/brainstorm | J "['state']")" working "gate promotes after all answered"
curl -fs $H/todo/board | python3 -c "import sys,json;exit(0 if 'clarifications' in json.load(sys.stdin)['tasks']['$BTID']['brainstorm'] else 1)" || {{ echo "FAIL: answered Q&A not folded into the brainstorm artifact"; exit 1; }}
# a CLEAR task (specific + checkable done-condition) gets 0 questions and is immediately promotable
CTID=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"Add a GET /health endpoint"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"set\\",\\"id\\":\\"$CTID\\",\\"doneCondition\\":\\"GET /health returns 200\\"}}" $H/todo/update >/dev/null
BRAINSTORM_CMD=stub TODO_HOST=$H QUEUE_SECRET="" python3 "$BIN/todo-brainstorm" >/dev/null
ck "$(curl -fs $H/todo/board | python3 -c "import sys,json;print(len(json.load(sys.stdin)['tasks']['$CTID']['questions']))")" 0 "clear task gets zero questions"
ck "$(curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$CTID\\",\\"promote\\":\\"working\\"}}" $H/todo/brainstorm | J "['state']")" working "clear task immediately promotable"
echo "  (d) brainstorm gate OK: under-specified->questions->blocked->answered->promoted (+Q&A folded); clear->0q->promotable"

# ── (e) WhatsApp CEO-watchdog: ONE consolidated digest of all blocked-on-CEO cards (w/ deep-links), repeats, updates, stops ──
DG(){{ curl -fs $H/todo/wa | python3 -c "import sys,json;print(next((e['text'] for e in reversed(json.load(sys.stdin)['queue']) if e.get('sentAt') and e.get('kind')=='digest'),''))"; }}  # latest SENT digest text
NDG(){{ curl -fs $H/todo/wa | python3 -c "import sys,json;print(sum(1 for e in json.load(sys.stdin)['queue'] if e.get('sentAt') and e.get('kind')=='digest'))"; }}  # count of sent digests
R1=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"WA review card ONE"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R1\\",\\"verified\\":true}}" $H/todo/status >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R1\\",\\"state\\":\\"review\\"}}" $H/todo/status >/dev/null
sleep 5
D1=$(DG); echo "$D1" | grep -q "need you" || {{ echo "FAIL: no consolidated digest sent for a blocked card"; exit 1; }}
echo "$D1" | grep -qF "#card/$R1" || {{ echo "FAIL: digest missing the deep-link to the blocked card"; exit 1; }}
echo "$D1" | grep -qi "Review" || {{ echo "FAIL: digest not grouped (Review)"; exit 1; }}
# a ceoGated 'blocked' card is blocked-on-CEO too -> it must appear in the digest ("Blocked on you")
BLK=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"WA blocked card"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$BLK\\",\\"ceoGated\\":true,\\"lastStatus\\":\\"awaiting CEO decision\\"}}" $H/todo/status >/dev/null
ck "$(G $BLK state)" blocked "ceoGated -> blocked"
sleep 5; DB=$(DG); echo "$DB" | grep -qF "#card/$BLK" || {{ echo "FAIL: a blocked (ceoGated) card is not in the CEO WhatsApp digest"; exit 1; }}
echo "$DB" | grep -qi "Blocked on you" || {{ echo "FAIL: digest missing the 'Blocked on you' group"; exit 1; }}
curl -fs -H 'Content-Type: application/json' -d "{{\\"op\\":\\"del\\",\\"id\\":\\"$BLK\\"}}" $H/todo/update >/dev/null; sleep 5   # clean up so the later 'stops when none blocked' check holds
N1=$(NDG)
# add a 2nd review card -> next digest UPDATES to list BOTH
R2=$(curl -fs -H 'Content-Type: application/json' -d '{{"op":"add","text":"WA review card TWO"}}' $H/todo/update | J "['id']")
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R2\\",\\"verified\\":true}}" $H/todo/status >/dev/null
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R2\\",\\"state\\":\\"review\\"}}" $H/todo/status >/dev/null
sleep 5
D2=$(DG); echo "$D2" | grep -qF "#card/$R1" && echo "$D2" | grep -qF "#card/$R2" || {{ echo "FAIL: digest didn't update to list BOTH blocked cards"; exit 1; }}
[ "$(NDG)" -gt "$N1" ] || {{ echo "FAIL: CEO-watchdog did not REPEAT the digest each tick"; exit 1; }}
# CEO acts on one -> digest UPDATES to drop it
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R1\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
sleep 5
D3=$(DG); echo "$D3" | grep -qF "#card/$R2" && ! echo "$D3" | grep -qF "#card/$R1" || {{ echo "FAIL: digest didn't update as a card cleared"; exit 1; }}
# CEO clears the last one -> digest STOPS
curl -fs -H 'Content-Type: application/json' -d "{{\\"id\\":\\"$R2\\",\\"state\\":\\"done\\",\\"by\\":\\"CEO\\"}}" $H/todo/status >/dev/null
sleep 5; STOPN=$(NDG); sleep 6                                                            # settle any in-flight, then confirm no further digests
[ "$(NDG)" -eq "$STOPN" ] || {{ echo "FAIL: digest did not STOP when no cards are blocked on the CEO"; exit 1; }}
echo "  (e) WhatsApp CEO-watchdog OK: ONE consolidated digest (grouped, deep-links) -> repeats -> updates as cards clear -> STOPS when none blocked"

# ── (c) assigned-but-idle WATCHDOG: a stalled assignee must ping the Boss (real engineers never POST /hook/stop) ──
WSTAT=/tmp/tv2-wd-status; WPROJ=/tmp/tv2-wd-proj; rm -rf "$WSTAT" "$WPROJ" /tmp/tv2-wd-board; mkdir -p "$WSTAT/mc-t" "$WPROJ/p"
printf '{{"agent_id":"t/eng-stalled","status":"idle","timestamp":"2020-01-01T00:00:00Z","session_id":"s1"}}' > "$WSTAT/mc-t/eng-stalled.json"
( QUEUE_PORT=9935 TODO_DIR=/tmp/tv2-wd-board TODO_HTML="$TODO_HTML" QUEUE_SECRET="" TODO_TEST_SINK=1 \\
  STATUS_DIR="$WSTAT" PROJECTS_DIR="$WPROJ" IDLE_STALL_SEC=2 WATCHDOG_SEC=1 STALL_REPING_SEC=1 \\
  PING_CRON_SEC=999 IDLE_GRACE_SEC=999 nohup python3 "$BIN/todo-server.py" >/tmp/tv2-wd.log 2>&1 & )
for i in 1 2 3 4 5 6 7 8 9 10; do curl -fs "127.0.0.1:9935/health" >/dev/null 2>&1 && break; sleep 1; done
WH=127.0.0.1:9935
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
echo "VERIFY_OK: todo — board drives Boss dispatch, ping machine (cron-unassigned + idle-post-stophook + assigned-idle WATCHDOG -> Boss), brainstorm gate (questions->answers->promote), proof-gated verify, re-ping. SEED one-shot in a clean container."
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
