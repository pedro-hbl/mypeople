# PLAN — TODO v2 ("Priorities") — the CEO's board as the Boss's source of truth

> Status: **DRAFT FOR CEO FINAL APPROVAL** — Rule 1 plan-gate. No code is written until the CEO
> types "approved/go". This file is the plan + the drafted E2E `## Verify`. v1 (`stream-todos`,
> static HTML + localStorage) stays as-is; v2 is a new, MyPeople-connected app.
> **Deliverable is a SEED** (`seeds/todo-v2.seed.md`), validated mypeople-style (clean-container
> one-shot + passing `## Verify`) — not just code. See §9.

## 0. One-line

The CEO's to-do board becomes the **single source of truth** for what the Boss makes the team work
on. Every task carries a written **done-condition**, a **"work-to-done" toggle**, and **attachable
proof**. The Boss co-manages the board **with the CEO** and reads the live HTML/board. A task that
hasn't been brainstormed is first **brainstormed by the Boss** (result written into the task) until
it's **ready**. A central **ping state machine always pings the Boss** (never the engineer
directly): pre-assignment by a **1-minute cron**, post-assignment **idle-driven** (1 min after the
assigned engineer's Stop hook, if still idle). A task is never **done** until its condition is
satisfied **and** independently verified, with proof attached.

## 1. Why (user pain)

Today the Boss's priority list lives in its head / in `plans/*/PLAN.md`. The CEO cannot see, at a
glance, what the team is working on, whether it's actually done, or the proof. v1 todos are
browser-private (localStorage) — the Boss can't read them. The CEO wants ONE board he controls that
*is* the work queue, that the Boss can read and update, so the team provably works on what matters.

## 2. User journey

1. CEO opens the v2 board at a local URL (`http://127.0.0.1:9900/todos`, also on the tailnet). The
   **Boss can open the same page / reads the same board** — they co-manage it.
2. CEO adds a task. The **done-condition is required** — until he writes "how to verify it's done",
   the **work-to-done toggle is disabled** (greyed). The task starts in **`needs_brainstorm`**.
3. **Brainstorm (Boss-led).** If the task hasn't been brainstormed, the **Boss brainstorms it** —
   clarifies scope/approach/risks — and **writes the result into the task** (`brainstorm` field).
   The CEO can edit/accept. When good, the task is promoted **`needs_brainstorm` → `ready`** (it is
   not dispatchable before `ready`).
4. CEO flips **work-to-done ON**. This **inserts a message into the Boss's queue** ("task T is ON —
   drive it to done"), so the Boss picks it up immediately (not only via passive board polling). He
   may pin an engineer; otherwise the Boss auto-assigns from the idle pool. List order = dispatch
   priority.
5. The Boss dispatches the (ready) task to the engineer via the queue (`mp send`).
6. Engineer works, **attaches proof** (screenshot / image / video / text / link), reports status.
7. The Boss **verifies the done-condition against the proof/artifact** (trust the artifact, not the
   self-report — mypeople doctrine).
   - Satisfied → task flips to **done** (green), proof shown, engineer freed.
   - Not satisfied → board shows **"not ready because X"**; the task stays ON, and the ping machine
     (below) keeps nudging the Boss, who **re-dispatches the same engineer** with the specific gap.
8. CEO watches live status + proof, reorders priorities anytime; reordering re-orders the queue.

## 3. The central PING STATE MACHINE (the heart of v2)

**Invariant: every ping goes to the BOSS.** The machine never pings an engineer; the Boss is the
one who reasons and then acts on engineers via `mp`. A task is "active" when `workToDone=ON` and
`state != done`. For each active task:

- **(a) Pre-assignment — time-based, 1-minute CRON.** If the task has **no engineer assigned**
  (incl. `needs_brainstorm`, or `ready` but unassigned), a **cron pings the Boss every 1 minute**
  *(changed from the previous 5-minute cadence to 1 minute)*. Ping payload tells the Boss what's
  needed: *brainstorm this*, or *ready+unassigned → assign & dispatch*.
- **(b) Post-assignment — idle-driven, NOT a time cron.** Once an engineer is assigned, the trigger
  is **that engineer's Stop hook**: after the Stop hook fires, **wait 1 minute**; if the engineer is
  **still IDLE** (status.json = idle / not working) → **ping the Boss** ("engineer E idle 1 min
  after stop on task T; not done because <lastStatus>"). If the engineer picked up new work (not
  idle) within the minute → **no ping**.
- **(c) Summary:** pre-assign = **cron 1 min (time)**; post-assign = **idle-driven (1 min after the
  assigned engineer's Stop hook, if still idle)**. Always pings the **Boss**.

On any ping, the Boss reconciles: brainstorm if `needs_brainstorm`; assign+dispatch if
`ready`+unassigned; verify proof if `awaiting_verify`; re-dispatch the engineer with the gap if not
done. Never marks `done` without `verified`.

Tunables (default 60 s in production; lowered in `## Verify` to keep tests fast):
`PING_CRON_SEC` (a) and `IDLE_GRACE_SEC` (b).

## 4. Architecture & MyPeople connection

**Problem:** v1's localStorage is browser-private; the Boss (a separate process) can't see it. v2's
store must be shared between the browser and the Boss, and the Boss must be able to read the HTML.

**Recommended (idiomatic to mypeople — "sibling seed layers a feature on top"):** ship v2 as a
sibling seed `seeds/todo-v2.seed.md`, pasted AFTER mypeople is installed, adding four pieces:

1. **Shared store** — `~/mypeople/todos/board.v2.json` (source of truth), proofs under
   `~/mypeople/todos/proofs/<task_id>/`. Single-writer-safe via the queue-server process (same
   pattern as agent status files), so both the CEO's browser and the Boss read/write it.
2. **Todo API on the existing queue-server** (extend `queue-server.py`; no second daemon):
   - `GET  /todos`       → serves the v2 HTML page (Boss & CEO open the same URL).
   - `GET  /todo/board`  → returns `board.v2.json` (the page polls this ~1s, like the HUD polls
     `/agents`; the Boss also reads it as its work-list).
   - `POST /todo/update` → upsert/reorder/edit/toggle a task or sub; **toggling `workToDone:true`
     also enqueues a Boss message** (server-side `mp send main:Boss …` / queue task).
   - `POST /todo/brainstorm` → Boss writes the brainstorm result + promotes `needs_brainstorm→ready`.
   - `POST /todo/proof`  → attach proof (multipart image/video, or text/link) to a task.
   - `POST /todo/status` → Boss/engineer write `state` + `lastStatus` + `verified` back.
   (Writes secret-guarded like other endpoints; `/todos` page public like `/dashboard`.)
3. **Ping state machine** (§3) wired into mypeople's existing machinery:
   - **(a) cron 1 min** — a periodic reconcile tick (queue-client cron / systemd-timer-style loop)
     scans the board for active **unassigned** tasks and posts a Boss ping. This is the cadence the
     CEO asked to change **5 min → 1 min**.
   - **(b) idle-post-stop-hook** — extend the `tmux-boss-hooks` plugin: on an **assigned** engineer's
     Stop, schedule a one-shot **+`IDLE_GRACE_SEC`** check that reads that engineer's `status.json`;
     if still idle, post a Boss ping. Idle-driven, not a timer cron.
4. **Boss doctrine addendum** `plans/boss-claude.md` → new **Rule 4 — Priority board is the queue**:
   - The board (ordered; `workToDone=ON`; `state != done`) IS the work-list Rule 2 dispatches from.
   - **Brainstorm gate:** a `needs_brainstorm` task is brainstormed by the Boss (writes `brainstorm`,
     promotes to `ready`) **before** any dispatch.
   - On a ping / engineer Stop: reconcile — assign if unassigned & ready; **verify the done-condition
     against the attached proof**; satisfied → `done`+`verified`; else `lastStatus="not ready because
     X"` and re-dispatch the same engineer with the gap.
   - Never set `done` without `verified`. All engineer actions go through `mp` (Rule 3 preserved).

Data flow (both directions):
```
CEO browser ──POST /todo/update (+toggle ON ⇒ enqueue Boss msg)──► queue-server ──► board.v2.json
                                        ▲                                              │
v2 page ◄──GET /todo/board (poll ~1s)───┘            Boss ALSO opens /todos & reads ───┤
                                                                                       ▼
PING MACHINE ──(a)cron 1min unassigned / (b)idle 1min post stop-hook──► [ping BOSS]    │
                                                                          │            │
Boss ──brainstorm / mp send dispatch / re-dispatch──► Engineer ──POST /todo/proof,/status──► board
  ▲                                                                                    │
  └──────────────── [AGENT NOTIFICATION] on Stop + GET /todo/board ─────────────────────┘
```
Runs local; CEO & Boss reach it on `127.0.0.1:9900/todos` or the tailnet hostname (same as the HUD).

**Alternative considered (decoupled):** a standalone `todo-bridge` daemon on :9910. Rejected for
v2.0 — extending the one local HTTP bus the Boss already speaks is simpler and matches the
HUD/status pattern. Kept as fallback if we ever want v2 to run without mypeople.

## 5. Data model (`board.v2.json`)

```
Board { version: "v2", order: [task_id...], tasks: { <id>: Task } }

Task {
  id, text,
  doneCondition: string,        // REQUIRED non-empty to enable workToDone & to allow done
  brainstorm: string,           // Boss-written; empty while needs_brainstorm
  workToDone: bool,             // "work to the end" toggle; ON ⇒ a Boss-queue msg is enqueued
  assignee: agent_id | null,    // mp agent; null => Boss auto-assigns
  state: 'needs_brainstorm'|'ready'|'dispatched'|'working'|'blocked'|'awaiting_verify'|'done',
  verified: bool,               // done-condition checked against proof
  lastStatus: string,           // "not ready because X" (engineer/Boss)
  proofs: [ Proof ],
  subs: [ Sub ],                // one level
  assignedAt, lastStopTs,       // feed the idle-post-stop-hook timer (machine b)
  created, updated
}
Sub  { id, text, done, doneCondition?: string, created }   // see Decision D1
Proof{ id, type: 'image'|'video'|'text'|'link', ref, caption, by, ts }
```

Invariants (enforced server-side, not just UI):
- `workToDone=true` rejected if `doneCondition` is empty.
- A task is **not dispatchable** until `state='ready'` (brainstorm done).
- `state='done'` rejected unless `verified=true`.
- Parent task is not `done` until its condition is verified **and** all subs are done.

## 6. Decisions for the CEO (revised)

- **D1 — Sub-items:** subs are checklist steps; the **parent** holds the binding done-condition
  (optional per-sub condition). *Proposal stands.*
- **D2 — Auto-assign:** when ready+unassigned & ON, the Boss auto-assigns round-robin from the idle
  pool; CEO can pin to override. *Proposal stands.*
- **D3 — Verification authority:** the **Boss** verifies the done-condition against the proof
  (engineer supplies proof; Boss decides done). *Proposal stands.*
- **D4 — Ping cadence: RESOLVED by the CEO.** Pre-assign = **cron every 1 min** (was 5); post-assign
  = **idle-driven, 1 min after the assigned engineer's Stop hook if still idle**; **ping always to
  the Boss.** (Now spec'd in §3; no longer open.)
- **D5 — Page location now:** served at `:9900/todos` by the queue-server (works over tailnet; Boss
  can open it too). *Proposal stands.*
- **D6 — Brainstorm promotion (NEW):** who flips `needs_brainstorm → ready`? *Proposal: the Boss
  proposes `ready` after writing the brainstorm; if `workToDone` is ON the Boss may auto-promote and
  proceed; CEO can edit the brainstorm or send it back. Confirm, or require explicit CEO promotion.*

## 7. Future (explicitly not now)

The v2 page lives **inside** the MyPeople HUD, next to the live agent view — one screen: priorities
left, agents/HUD right. v2.0 ships the standalone `/todos` page; embedding is a later slice.

## 8. Agents that will do the work (once approved)

- `eng-todo-api` — extend `queue-server.py` with `/todo/*` endpoints + store + proof storage +
  the toggle-ON⇒enqueue-Boss-message behavior.
- `eng-ping-machine` — (a) the 1-min reconcile cron for unassigned active tasks; (b) the
  `tmux-boss-hooks` extension for the idle-1min-post-stop-hook check. Both ping the Boss.
- `eng-todo-ui` — the v2 HTML page (fork v1 visuals; required done-condition field, gated
  work-to-done toggle, brainstorm display/edit, proof attach + render, live status).
- `eng-boss-doctrine` — Rule 4 addendum (brainstorm gate + reconcile/verify loop).
- `eng-seed-packager` — fold all of the above into `seeds/todo-v2.seed.md` and run the seed
  validation loop (§9). Orchestrated by the Boss; each slice has its own Verify before merge.

## 9. Deliverable = a validated SEED (mypeople doctrine)

The final artifact is **`seeds/todo-v2.seed.md`** — a single sibling seed that, pasted into a clean
mypeople runtime, stands up the whole v2 (store + API + ping machine + UI + Rule 4) and **passes its
own `## Verify`**. Per the mypeople handbook: *the seed is the artifact; the running system is the
proof; a seed without a passing Verify from a brand-new container is a draft.* So v2 is "done" only
when a **clean container one-shots the seed** and the §Verify below passes from an independent shell
(`docker exec`), with **zero ad-hoc fixes** — every bug folded back into the seed text.

## Verify (E2E — this is the seed's own Verify; run from an independent shell after a clean paste)

```bash
set -euo pipefail
H=127.0.0.1:9900 ; S="$QUEUE_SECRET"
hdr=(-H "X-Queue-Secret: $S" -H "Content-Type: application/json")
# tests run with fast cadence so we don't wait real minutes:
export PING_CRON_SEC=3 IDLE_GRACE_SEC=3     # production defaults = 60

# 0. runtime + todo API up, page served, Boss can read board
curl -fs "http://$H/health" | jq -e '.status=="ok"'
curl -fs "http://$H/todos" | grep -qi "priorities\|to-do"
curl -fs "http://$H/todo/board" | jq -e '.version=="v2"'

# 1. done-condition REQUIRED to enable the toggle
TID=$(curl -fs "${hdr[@]}" -d '{"op":"add","text":"smoke task"}' "http://$H/todo/update" | jq -r .id)
curl -fs "http://$H/todo/board" | jq -e --arg t "$TID" '.tasks[$t].state=="needs_brainstorm"'
curl -s  "${hdr[@]}" -d "{\"op\":\"set\",\"id\":\"$TID\",\"workToDone\":true}" "http://$H/todo/update" \
  | jq -e '.error|test("doneCondition")'                       # rejected without condition

# 2. add condition; BRAINSTORM gate — not dispatchable until ready
curl -fs "${hdr[@]}" -d "{\"op\":\"set\",\"id\":\"$TID\",\"doneCondition\":\"file /tmp/PROOF.txt contains OK\"}" "http://$H/todo/update" | jq -e '.ok'
curl -fs "http://$H/todo/board" | jq -e --arg t "$TID" '.tasks[$t].state=="needs_brainstorm"'

# 3. PING MACHINE (a): active + UNASSIGNED ⇒ Boss is pinged by the 1-min cron (here 3s).
#    (count Boss-directed pings before/after; expect an increase.)
P0=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
curl -fs "${hdr[@]}" -d "{\"op\":\"set\",\"id\":\"$TID\",\"workToDone\":true}" "http://$H/todo/update" | jq -e '.bossEnqueued==true'   # toggle ON enqueues a Boss msg (refinement #3)
sleep 5
P1=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
[ "$P1" -gt "$P0" ]                                            # cron pinged the Boss while unassigned

# 4. Boss brainstorms ⇒ ready; then assign an engineer
curl -fs "${hdr[@]}" -d "{\"id\":\"$TID\",\"brainstorm\":\"approach: write OK to /tmp/PROOF.txt\",\"promote\":\"ready\"}" "http://$H/todo/brainstorm" | jq -e '.ok'
curl -fs "http://$H/todo/board" | jq -e --arg t "$TID" '.tasks[$t].state=="ready"'
curl -fs "${hdr[@]}" -d "{\"op\":\"set\",\"id\":\"$TID\",\"assignee\":\"main:eng-1\"}" "http://$H/todo/update" | jq -e '.ok'
mp spawn main:eng-1 --backend claude --boss main:Boss || true

# 5. PING MACHINE (b): simulate the ASSIGNED engineer's Stop hook while still IDLE ⇒ Boss pinged
#    after IDLE_GRACE_SEC. And the inverse: if the engineer is working, NO ping.
B0=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
"$INSTALL_DIR/bin/sim-stop-hook" main:eng-1 --idle   # fires Stop hook; engineer stays idle
sleep 5
B1=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
[ "$B1" -gt "$B0" ]                                            # idle-1min(=3s)-post-stop ⇒ Boss pinged
"$INSTALL_DIR/bin/sim-stop-hook" main:eng-1 --working ; B2a=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
sleep 5 ; B2b=$(curl -fs "http://$H/todo/board" | jq -r --arg t "$TID" '.tasks[$t].pingsToBoss // 0')
[ "$B2b" -eq "$B2a" ]                                          # engineer working ⇒ NO ping

# 6. NEGATIVE: result without satisfying proof ⇒ "not ready because X", not done
curl -fs "${hdr[@]}" -d "{\"id\":\"$TID\",\"state\":\"awaiting_verify\",\"lastStatus\":\"partial\"}" "http://$H/todo/status"
curl -fs "http://$H/todo/board" | jq -e --arg t "$TID" '.tasks[$t].verified==false and (.tasks[$t].lastStatus|test("not ready|because|partial"))'

# 7. POSITIVE: satisfy condition + attach proof ⇒ Boss verifies ⇒ done
echo OK > /tmp/PROOF.txt
curl -fs "${hdr[@]}" -F "task_id=$TID" -F "type=text" -F "ref=@/tmp/PROOF.txt" "http://$H/todo/proof" | jq -e '.ok'
for i in $(seq 1 30); do curl -fs "http://$H/todo/board" | jq -e --arg t "$TID" \
   '.tasks[$t].state=="done" and .tasks[$t].verified==true and (.tasks[$t].proofs|length>=1)' && break; sleep 2; done

# 8. INVARIANTS: no done-without-verified; nothing dispatched before ready
curl -fs "http://$H/todo/board" | jq -e '[.tasks[]|select(.state=="done" and .verified!=true)]|length==0'
curl -fs "http://$H/todo/board" | jq -e '[.tasks[]|select((.state|test("dispatched|working")) and (.brainstorm==""))]|length==0'
echo "VERIFY_OK: todo-v2 seed — brainstorm gate, toggle⇒Boss-msg, ping machine (cron 1m unassigned + idle-1m-post-stophook assigned, always to Boss), proof-gated verify. Validate by one-shotting the seed in a CLEAN mypeople container, then run this from docker exec."
```
