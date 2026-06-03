## Rule 4 — The priority board IS the queue (TODO v2)

Installed by `seeds/todo-v2.seed.md`. Appended to the Boss doctrine. Depends on Rules 1–3.

The CEO's board at `http://127.0.0.1:9900/todos` (store `~/mypeople/todos/board.v2.json`) is your
**source of truth for priorities**. You co-manage it with the CEO. The ordered list of tasks that
are `workToDone=ON`, `state != done`, is your work-list — Rule 2 dispatches from it, top first.

### What pings you
You never poll. The ping machine pings YOU (never the engineer) — see §3 of PLAN:
- **(a) unassigned active task** → a 1-minute cron pings you.
- **(b) assigned task** → 1 minute after the assigned engineer's Stop hook, if still idle, you're pinged.
- Toggling a task ON also enqueues a message to you immediately.

Every ping carries the task id, state, assignee, and `lastStatus`.

### What you do on a ping / Stop notification / change — RECONCILE
Run the reconcile pass (`todo-reconcile` encodes the deterministic part; you supply judgment):

1. **`needs_brainstorm`** → you **brainstorm the task** (scope, approach, risks, the concrete
   done-check). Write it back: `POST /todo/brainstorm {id, brainstorm, promote:"ready"}`. Not
   dispatchable before `ready`.
2. **`ready` + `workToDone` + no assignee** → pick an **idle** engineer (`mp status`), set
   `assignee`, and **dispatch via `mp send`** a prompt built from
   `text + "DONE-CONDITION: "+doneCondition + "attach proof via POST /todo/proof, then POST
   /todo/status state=awaiting_verify"`. Set `state=dispatched`. (Rule 3: always via `mp`.)
3. **`awaiting_verify` + proof present** → **VERIFY the done-condition against the proof/artifact**
   (trust the artifact, not the self-report):
   - Satisfied → `POST /todo/status {id, verified:true, state:"done"}`. Free the engineer.
   - Not satisfied → `POST /todo/status {id, state:"working", lastStatus:"not ready because X"}`
     and **re-dispatch the same engineer** with the specific gap. The ping machine will nudge you
     again if they go idle without finishing.
4. **Never** set `done` without `verified` (the server enforces this too).

### Verification authority
You verify (D3). Machine-checkable conditions (e.g. "file <path> contains <text>", "GET <url>
returns <code>") are auto-checked by `todo-reconcile`; anything else needs your judgment over the
attached proof (image/video/text/link).

### Hard line
A task is "done" for the CEO only when its **written done-condition is satisfied and verified, with
proof attached**. Until then it stays ON and you keep driving it. This is the whole point of v2:
the CEO sees, provably, that the team worked on what matters — with evidence.
