#!/usr/bin/env python3
"""todo server — the CEO's priority board as the Boss's source of truth.

Slice: API + shared store + PING STATE MACHINE. Designed to be inlined (heredoc)
into seeds/todo.seed.md and to run either:
  - standalone in a clean container (boss pings go to a file sink; TODO_TEST_SINK=1), or
  - on top of a live mypeople runtime (boss pings go through `mp send main:Boss`).

Store : $TODO_DIR/board.v2.json   proofs: $TODO_DIR/proofs/<task_id>/
Env   : QUEUE_PORT(9900) QUEUE_SECRET('') TODO_DIR(~/mypeople/todos)
        PING_CRON_SEC(60) IDLE_GRACE_SEC(60) TODO_HTML(<dir>/todos.html)
        TODO_TEST_SINK(0)  BOSS_AGENT(main:Boss)  QUEUE_URL(http://127.0.0.1:9900)
        (QUEUE_URL = the mypeople queue-server, queried for ttyd attach_base in /todo/attach)
        WhatsApp drain (slice e): WA_DRAIN(1) WA_CHAT_JID(CEO JID) WA_SEND_CMD(Hermes last hop,
        reads {chatId,message} on stdin) WA_BOARD_URL('') WA_WATCHDOG_SEC(180) WA_DRAIN_SEC(10) WA_REPING_SEC(900)
"""
import http.server, json, os, threading, time, uuid, base64, subprocess, shutil, datetime, urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT        = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET      = os.environ.get("QUEUE_SECRET", "")
TODO_DIR    = Path(os.environ.get("TODO_DIR", str(Path(__file__).resolve().parent / "data")))  # durable, beside the server (NOT /tmp)
PROOF_DIR   = TODO_DIR / "proofs"
BOARD_PATH  = TODO_DIR / "board.v2.json"
INBOX_LOG   = TODO_DIR / "boss-inbox.log"
PING_CRON   = float(os.environ.get("PING_CRON_SEC", "120"))   # unassigned-card cron (CEO: 2 min)
IDLE_GRACE  = float(os.environ.get("IDLE_GRACE_SEC", "60"))    # assigned idle-post-stop-hook (1 min)
IDLE_STALL  = float(os.environ.get("IDLE_STALL_SEC", "180"))   # assigned-but-idle WATCHDOG threshold (3 min)
STALL_REPING= float(os.environ.get("STALL_REPING_SEC", "300")) # re-ping throttle per stalled card
WATCHDOG    = float(os.environ.get("WATCHDOG_SEC", "60"))      # watchdog scan interval
STATUS_DIR  = Path(os.environ.get("STATUS_DIR", str(Path.home() / "mypeople" / "status")))
PROJECTS_DIR= Path(os.environ.get("PROJECTS_DIR", str(Path.home() / ".claude" / "projects")))
BUSY_CPU    = float(os.environ.get("BUSY_CPU_PCT", "20"))      # watchdog: process-tree CPU% above this == busy (long job)
BUSY_NAMES  = set(n.strip() for n in os.environ.get("BUSY_NAMES",
    "ffmpeg,docker,buildkitd,containerd,rsync,scp,ssh,sftp,wget,curl,git,make,cmake,ninja,cargo,rustc,"
    "gcc,cc,clang,ld,collect2,tsc,webpack,vite,esbuild,rollup,next,vercel,bun,sox,whisper").split(",") if n.strip())
TEST_SINK   = os.environ.get("TODO_TEST_SINK", "0") == "1"
BOSS_AGENT  = os.environ.get("BOSS_AGENT", "main:Boss")
HTML_PATH   = Path(os.environ.get("TODO_HTML", str(Path(__file__).resolve().parent / "todos.html")))
QUEUE_URL   = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900").rstrip("/")  # the mypeople queue-server (for /clients attach_base; slice c)
# ── WhatsApp last-hop drain + CEO-watchdog (slice e) ─────────────────────────
# A 'whatsapp' queue participant. The CEO-watchdog (every WA_WATCHDOG_SEC = 5 min) sends the CEO
# ONE consolidated DIGEST listing every card blocked on him — grouped review-pending /
# brainstorm-pending, each line = card title + a tappable deep-link straight to that card — via the
# LAST HOP (containerized Hermes /send to his personal JID). It fires only while ≥1 card is blocked,
# repeats every 5 min, updates as cards clear, and stops when none remain. The send command is
# configurable so the seed works wherever Hermes is reachable; WA_DRAIN=0 disables the last hop.
WA_OUTBOX   = TODO_DIR / "wa-outbox.json"
WA_CHAT_JID = os.environ.get("WA_CHAT_JID", "").strip()   # CEO WhatsApp JID — REQUIRED for the drain; set via env/plist. NEVER hardcode a personal number in the published seed (privacy). e.g. <digits>@s.whatsapp.net
WA_DRAIN_ON = (os.environ.get("WA_DRAIN", "1") == "1") and bool(WA_CHAT_JID)   # no target JID -> drain stays off
WA_SEND_CMD = os.environ.get("WA_SEND_CMD",                                   # reads {chatId,message} JSON on stdin
    'docker exec -i hermes-wa curl -s -H "Host: 127.0.0.1" -H "Content-Type: application/json" '
    '-X POST http://127.0.0.1:3000/send -d @-')
WA_BOARD_URL= os.environ.get("WA_BOARD_URL", "")                             # board page URL; each card line links to <WA_BOARD_URL>#card/<id>
WA_WATCHDOG = float(os.environ.get("WA_WATCHDOG_SEC", "300"))                # CEO-watchdog: send the digest every 5 min while ≥1 card is blocked
WA_DRAIN_SEC= float(os.environ.get("WA_DRAIN_SEC", "10"))                    # drain tick
WA_REPING   = float(os.environ.get("WA_REPING_SEC", "270"))                 # min interval (s) between digests — just under the 5-min tick so each tick sends, but a mutation mid-interval can't add an extra digest
_wa_lock = threading.RLock()

VALID_STATES = {"needs_brainstorm", "working", "review", "blocked", "done", "cancelled"}   # CEO model: in-progress is 'working'; 'review' = engineer done + Boss-verified, awaiting CEO sign-off (Rule 21: only the CEO marks done); 'cancelled' = terminal side-exit (CEO abandons the task — alongside 'done', never worked/pinged again)
TERMINAL_STATES = {"done", "cancelled"}                                       # terminal: not ACTIVE, never dispatched/pinged/in the WhatsApp digest
ACTIVE = lambda t: t.get("workToDone") and t.get("state") not in TERMINAL_STATES
_lock = threading.RLock()
# per-agent last stop-hook state: agent_id -> "idle" | "working"
_hook_state = {}

def now(): return int(time.time() * 1000)
def uid(): return uuid.uuid4().hex[:12]
def _build_stamp():
    """A stable build id = mtime of the served HTML. Changes exactly once per deploy, so an open
    board reloads itself when a new todos.html ships (no manual hard-refresh / stale-JS bugs)."""
    try: return str(int(HTML_PATH.stat().st_mtime))
    except Exception: return "0"

def _default_board(): return {"version": "v2", "order": [], "tasks": {}}

def load():
    try:
        b = json.loads(BOARD_PATH.read_text())
        if not isinstance(b, dict) or b.get("version") != "v2": return _default_board()
        b.setdefault("order", []); b.setdefault("tasks", {})
        for t in b["tasks"].values():
            t.setdefault("comments", [])                 # issue-style thread (slice b)
            t.setdefault("questions", [])                # brainstorm gate (slice d)
            t.setdefault("brainstormAsked", False)
        return b
    except Exception:
        return _default_board()

def save(b):
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BOARD_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(b, indent=2)); tmp.replace(BOARD_PATH)

def _ingest_file(tid, pid, ptype, srcpath):
    """Copy a referenced local image/video into the served proof store; return its URL or None."""
    src = srcpath[7:] if srcpath.startswith("file://") else srcpath
    if not os.path.isfile(src): return None
    base = os.path.basename(src)
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ("png" if ptype == "image" else "mp4")
    PD = PROOF_DIR / tid; PD.mkdir(parents=True, exist_ok=True)
    dst = PD / f"{pid}.{ext}"
    try:
        if not dst.exists(): shutil.copyfile(src, dst)
        return f"/todo/proof/{tid}/{pid}.{ext}"
    except Exception:
        return None

def migrate_proofs(b):
    """Image/video proofs stored as a local path/file:// -> copy into the store + rewrite to a served URL."""
    changed = False
    for tid, t in b.get("tasks", {}).items():
        for pr in t.get("proofs", []):
            if pr.get("type") in ("image", "video"):
                ref = pr.get("ref", "")
                if ref and not ref.startswith("/todo/proof/"):
                    url = _ingest_file(tid, pr["id"], pr["type"], ref)
                    if url: pr["ref"] = url; changed = True
    if changed: save(b)
    return b

def new_task(text):
    return {"id": uid(), "text": text or "", "doneCondition": "", "brainstorm": "",
            "workToDone": False, "assignee": None, "state": "needs_brainstorm",
            "verified": False, "lastStatus": "", "proofs": [], "subs": [], "comments": [],
            "questions": [], "brainstormAsked": False, "test": False,
            "parent": None, "dependsOn": [], "hardGate": False,   # issue #3: parent/child hierarchy + 'blocked by' deps + optional per-card hard gate (OFF by default)
            "pingsToBoss": 0, "assignedAt": None, "lastStopTs": None,
            "created": now(), "updated": now()}

# ── subtasks + dependencies (issue #3) ──────────────────────────────────────
def _children(b, tid):                      # real child cards (parent == tid)
    return [x for x in b["tasks"].values() if x.get("parent") == tid]
def _incomplete_children(b, tid):
    return [c for c in _children(b, tid) if c.get("state") not in TERMINAL_STATES]
def _unmet_deps(b, t):                       # 'blocked by' cards not yet done/cancelled
    out = []
    for dep in (t.get("dependsOn") or []):
        d2 = b["tasks"].get(dep)
        if d2 and d2.get("state") not in TERMINAL_STATES: out.append(dep)
    return out
def _creates_cycle(b, tid, parent_id):       # would setting tid.parent=parent_id create a loop?
    seen, cur = set(), parent_id
    while cur:
        if cur == tid: return True
        if cur in seen: break
        seen.add(cur); cur = (b["tasks"].get(cur) or {}).get("parent")
    return False
def state_gate(b, t, newstate):
    """Issue #3 gates. Returns an error string to block the transition, or None to allow.
    - DONE is blocked while any subtask/dependency is still incomplete (CEO's requested guardrail).
    - WORKING is blocked only when this card's per-card hard gate is ON and a prereq is unmet (OFF by default)."""
    if newstate == "done":
        inc, un = _incomplete_children(b, t["id"]), _unmet_deps(b, t)
        if inc or un:
            parts = []
            if inc: parts.append(f"{len(inc)} subtask(s) not done/cancelled")
            if un:  parts.append(f"{len(un)} dependency(ies) not done/cancelled")
            return "cannot mark DONE — " + " and ".join(parts) + " (finish or cancel them first)"
    if newstate == "working" and t.get("hardGate"):
        un = _unmet_deps(b, t)
        if un: return f"hard gate ON — blocked by {len(un)} unfinished prerequisite(s); finish/cancel them or turn the hard gate off"
    return None

# ── test/demo/proof card EXEMPTION ───────────────────────────────────────────
# An engineer's throwaway fixture must NOT nudge the Boss/CEO: a card flagged test:true OR whose title
# starts with [demo]/[proof]/[test] fires NO create-ping, is skipped by the cron + brainstorm-triage +
# the assigned-idle watchdog, and never appears in the CEO WhatsApp digest. (Real work is never prefixed
# that way, so this can't silence a genuine task.)
_TEST_PREFIXES = ("[demo]", "[proof]", "[test]", "[demo ", "[proof ", "[test ")
def _is_test(t):
    if t.get("test") is True: return True
    return (t.get("text") or "").lstrip().lower().startswith(_TEST_PREFIXES)

# ── BRAINSTORM GATE (slice d) ────────────────────────────────────────────────
# An under-specified new task can't be worked until it's been brainstormed: the brainstorm
# worker (bin/todo-brainstorm) generates clarifying QUESTIONS (office-hours method, via headless
# claude) and posts them here; they surface in the card AS questions to the CEO; the task stays
# needs_brainstorm and non-workable until every question is answered; the resolved Q&A is folded
# into the durable brainstorm artifact. A task the generator judges already-clear gets ZERO
# questions + a one-line brainstorm → immediately promotable. (Silent-no-op surfacing already ships.)
def _unanswered(t):
    return [q for q in t.get("questions", []) if not (q.get("answer") or "").strip()]

def brainstorm_ready(t):
    """True iff the task has cleared the gate and may be promoted to working."""
    if _unanswered(t):                                  # open questions block the gate
        return False
    return bool((t.get("brainstorm") or "").strip()) or bool(t.get("questions"))

def _assemble_artifact(t):
    """Fold the answered Q&A into the durable brainstorm artifact (idempotent-ish)."""
    qs = t.get("questions", [])
    if not qs: return
    lines = ["", "── clarifications (CEO) ──"]
    for q in qs:
        lines.append(f"Q: {q.get('q','').strip()}")
        lines.append(f"A: {(q.get('answer') or '').strip()}")
    block = "\n".join(lines)
    base = (t.get("brainstorm") or "").strip()
    if "── clarifications (CEO) ──" in base:             # refresh the block rather than stack copies
        base = base.split("── clarifications (CEO) ──")[0].rstrip()
        block = "\n" + block
    t["brainstorm"] = (base + "\n" + block).strip() if base else block.strip()

# ── issue-style thread (slice b): a durable per-task comment/event timeline. ──
# Every meaningful signal (engineer status, state transition, brainstorm save, CEO/AI comment)
# is appended as an immutable event so the card shows the FULL history, GitHub-issue style —
# unlike lastStatus, which is overwritten. The card UI merges these with proofs[] by ts.
#   kind: 'comment' (CEO/engineer free text) | 'status' (engineer lastStatus) |
#         'state' (state transition) | 'brainstorm' (artifact saved/updated)
def add_comment(t, body, by, kind="comment"):
    body = (body or "").strip()
    if not body: return None
    c = {"id": uid(), "kind": kind, "body": body, "by": by or "system", "ts": now()}
    t.setdefault("comments", []).append(c)
    return c

# ── Boss ping: the ONLY thing the ping machine does. Always targets the Boss. ──
def boss_ping(task_id, reason):
    with _lock:
        b = load()
        t = b["tasks"].get(task_id)
        if not t: return
        t["pingsToBoss"] = t.get("pingsToBoss", 0) + 1
        t["updated"] = now()
        save(b)
        msg = f"[todo] task {task_id} ({t.get('text','')!r}): {reason}. " \
              f"state={t['state']} assignee={t['assignee']} lastStatus={t.get('lastStatus','')!r}"
    try:
        INBOX_LOG.parent.mkdir(parents=True, exist_ok=True)
        with INBOX_LOG.open("a") as f: f.write(f"{now()} {msg}\n")
    except Exception: pass
    if not TEST_SINK and shutil.which("mp"):
        try:
            r = subprocess.run(["mp", "send", BOSS_AGENT, msg], capture_output=True, text=True, timeout=10)
            with INBOX_LOG.open("a") as f:
                f.write(f"{now()} MP_SEND -> {BOSS_AGENT} rc={r.returncode} :: {(r.stdout or r.stderr).strip()[:140]}\n")
        except Exception as e:
            with INBOX_LOG.open("a") as f: f.write(f"{now()} MP_SEND ERROR {e}\n")

# ── ping machine (a): cron — active + UNASSIGNED tasks ping the Boss every PING_CRON ──
def cron_loop():
    while True:
        time.sleep(PING_CRON)
        for tid in list(load()["tasks"].keys()):
            t = load()["tasks"].get(tid)
            if not t or _is_test(t): continue          # test/demo/proof fixtures never nudge the Boss
            # The Boss cron only chases ACTIVE (work-to-done) + unassigned WORK to assign+dispatch.
            # Brainstorm-triage is NOT a repeated Boss nudge: a card blocked on the CEO (review / blocked /
            # needs_brainstorm-with-questions) is pinged to the CEO's WhatsApp by the CEO-watchdog (slice e),
            # and a freshly-created card gets ONE create-ping. So there's no repeated in-app brainstorm cron.
            if ACTIVE(t) and not t.get("assignee") and t["state"] not in ("blocked", "review"):
                reason = "needs brainstorm" if t["state"] == "needs_brainstorm" else "working & unassigned — assign+dispatch"
                boss_ping(tid, f"cron(unassigned): {reason}")

# ── ping machine (b): idle-driven — fired by the ASSIGNED engineer's stop hook ──
def on_stop_hook(agent_id, hook_state):
    _hook_state[agent_id] = hook_state           # latest state wins
    t_at_fire = hook_state
    def check():
        if _hook_state.get(agent_id) != "idle":  # picked up work within the grace window
            return
        for tid in list(load()["tasks"].keys()):
            t = load()["tasks"].get(tid)
            if t and ACTIVE(t) and t.get("assignee") == agent_id:
                boss_ping(tid, f"idle {IDLE_GRACE}s after {agent_id} stop-hook — not done")
    with _lock:
        b = load()
        for t in b["tasks"].values():
            if t.get("assignee") == agent_id: t["lastStopTs"] = now()
        save(b)
    if hook_state == "idle":
        threading.Timer(IDLE_GRACE, check).start()

# ── ping machine (c): ASSIGNED-BUT-IDLE WATCHDOG ─────────────────────────────
# Real engineers don't POST /hook/stop, so machine (b) often never fires. This
# watchdog actively detects an assigned engineer that has gone idle/stalled at
# its prompt and pings the Boss. Signal (mypeople-native):
#   * the agent's status.json (status='idle' + 'timestamp' = when it last STOPPED)
#   * its Claude session transcript mtime (still being written == busy in a turn)
# Stalled  := stopped > IDLE_STALL ago  AND  transcript not written in IDLE_STALL
#             (so a long silent render reads as busy, not idle — no false stall).
# Unknown agent (no status file) -> treat as stalled (err toward pinging, per CEO).
def _iso_epoch(ts):
    try: return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception: return None

def _status_for(agent_id):
    try:
        for p in STATUS_DIR.glob("*/*.json"):
            try: d = json.loads(p.read_text())
            except Exception: continue
            if d.get("agent_id") == agent_id: return d
    except Exception: pass
    return None

def _session_active_within(session_id, window):
    if not session_id: return False
    nowt = time.time()
    try:
        for p in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
            try:
                if nowt - p.stat().st_mtime < window: return True
            except Exception: continue
    except Exception: pass
    return False

# Process-level "is the engineer actually running a long job?" — covers the case where a long
# bash/tool call (ffmpeg render, docker build, npm build) makes the transcript go quiet for minutes.
def _proc_table():
    # pid -> (ppid, pcpu, comm)
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,pcpu=,comm="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    tab = {}
    for ln in out.splitlines():
        p = ln.split(None, 3)
        if len(p) < 4: continue
        try: tab[int(p[0])] = (int(p[1]), float(p[2]), os.path.basename(p[3].strip()))
        except Exception: continue
    return tab

def _etime_secs(pid):
    # portable (macOS + Linux): elapsed seconds since `pid` started, from ps etime ([[DD-]HH:]MM:SS)
    try:
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return None
    if not out: return None
    days = 0
    if "-" in out:
        d, out = out.split("-", 1)
        try: days = int(d)
        except Exception: return None
    try: parts = [int(x) for x in out.split(":")]
    except Exception: return None
    if len(parts) == 3:   h, m, s = parts
    elif len(parts) == 2: h, m, s = 0, parts[0], parts[1]
    else: return None
    return days * 86400 + h * 3600 + m * 60 + s

def _descendants(pp, tab):
    kids = {}
    for pid, v in tab.items(): kids.setdefault(v[0], []).append(pid)
    seen, stack = set(), [pp]
    while stack:
        x = stack.pop()
        for c in kids.get(x, []):
            if c not in seen: seen.add(c); stack.append(c)
    return [p for p in (seen | {pp}) if p in tab]

def _session_age(agent_id):
    """Seconds since the agent's CURRENT live session started (its claude process age), so a
    respawned agent reusing a name isn't judged by the dead session's stale stop-timestamp."""
    pp = _pane_pid(agent_id)
    if not pp: return None
    tab = _proc_table()
    claude_pids = [p for p in _descendants(pp, tab) if tab.get(p, (0, 0, ""))[2] == "claude"] if pp in tab else []
    ages = [a for a in (_etime_secs(p) for p in (claude_pids or [pp])) if a is not None]
    return min(ages) if ages else None              # youngest claude = current session; else pane shell age

def _pane_pid(agent_id):
    """tmux pane pid for agent host/session:tab -> tmux session 'mc-<session>', window '<tab>'."""
    try: sess, tab = agent_id.split("/", 1)[1].split(":", 1)
    except Exception: return None
    try:
        r = subprocess.run(["tmux", "list-panes", "-s", "-t", "mc-" + sess, "-F", "#{window_name}\t#{pane_pid}"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return None
        for ln in r.stdout.splitlines():
            w, _, pp = ln.partition("\t")
            if w == tab:
                try: return int(pp)
                except Exception: return None
    except Exception: return None
    return None

def _ignored_for_cpu(comm):
    # the persistent MCP/browser stack burns CPU regardless of whether the agent is working;
    # it must NOT count as "busy", or a parked agent with an open browser would never be flagged.
    c = comm.lower()
    return any(k in c for k in ("chrome", "node", "caffeinate", "mcp", "9222", "google"))

def agent_busy(agent_id):
    """True if the assigned engineer has an ACTIVE long-running job in its process tree.
    Two signals: (1) a heavy command by NAME (ffmpeg/docker/build tools — the docker/ffmpeg CLI
    client stays a pane child for the whole job, MCP-immune); (2) CPU burn EXCLUDING the persistent
    MCP/browser stack. Returns False if the pane can't be located (no tmux) -> transcript/timestamp decide."""
    pp = _pane_pid(agent_id)
    if not pp: return False
    tab = _proc_table()
    nodes = _descendants(pp, tab)
    by_name = any(tab[p][2] in BUSY_NAMES for p in nodes)
    cpu = sum(tab[p][1] for p in nodes if not _ignored_for_cpu(tab[p][2]))
    busy = by_name or cpu >= BUSY_CPU
    if os.environ.get("DEBUG_BUSY") == "1":
        names = sorted({tab[p][2] for p in nodes})
        print(f"[busy] {agent_id} pane={pp} cpu(excl-mcp)={cpu:.1f} by_name={by_name} -> {busy} :: {names}", flush=True)
    return busy

# Ground-truth BUSY signal — the SAME marker `mp peek` uses. Claude Code AND Codex print
# "esc to interrupt" in the TUI footer ONLY while a turn is actively running (Codex wraps it
# as "* Working (Ns * esc to interrupt)"). A deep-thinking / long-turn agent burns ~no CPU and
# writes ~no transcript mid-turn, so the CPU/transcript signals miss it and the watchdog would
# falsely nudge it. This pane read is the authoritative "is a turn running RIGHT NOW?" check.
PEEK_BUSY_MARKER = "esc to interrupt"

def agent_pane_busy(agent_id):
    """True if the agent's live tmux pane shows the busy marker (a turn is actively running),
    classified exactly like `mp peek`/peek_state: last 15 NON-BLANK lines of the frame contain
    'esc to interrupt'. Returns False if the pane can't be read (no tmux) -> other signals decide."""
    try:
        sess, tab = agent_id.split("/", 1)[1].split(":", 1)
    except Exception:
        return False
    try:
        r = subprocess.run(["tmux", "capture-pane", "-t", f"mc-{sess}:{tab}", "-p", "-S", "-200"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return False
        tail = "\n".join([l for l in r.stdout.splitlines() if l.strip()][-15:]).lower()
        busy = PEEK_BUSY_MARKER in tail
        if os.environ.get("DEBUG_BUSY") == "1":
            print(f"[pane-busy] {agent_id} mc-{sess}:{tab} marker={busy}", flush=True)
        return busy
    except Exception:
        return False

def assignee_idle_secs(agent_id):
    """Idle seconds if the assigned agent looks parked/stalled, else None (active/grace/busy-job).

    The nudge is gated on the agent's ACTUAL state, never just elapsed-time: a turn running RIGHT
    NOW (TUI busy marker, the mp-peek ground truth) is BUSY and is never nudged, even if the
    stop-hook timestamp is stale and the transcript is quiet (deep-thinking long turn). Only a
    genuinely IDLE-at-prompt agent past the threshold is reported as stalled."""
    if agent_pane_busy(agent_id): return None              # a turn is actively running NOW -> BUSY -> never a false nudge
    d = _status_for(agent_id)
    if not d: return IDLE_STALL + 1                         # no status -> can't confirm active -> stalled
    if d.get("status") != "idle": return None              # explicitly busy
    t = _iso_epoch(d.get("timestamp", ""))
    idle_for = (time.time() - t) if t else IDLE_STALL + 1
    age = _session_age(agent_id)                           # respawn-aware: a freshly re-spawned agent
    if age is not None: idle_for = min(idle_for, age)      # can't have been idle longer than its live session exists
    if idle_for < IDLE_STALL: return None                  # recently stopped/respawned -> grace
    if _session_active_within(d.get("session_id"), IDLE_STALL): return None  # transcript moving -> busy turn
    if agent_busy(agent_id): return None                   # long-running job in its process tree -> busy
    return idle_for

def watchdog_loop():
    while True:
        time.sleep(WATCHDOG)
        for tid in list(load().get("tasks", {}).keys()):
            ping = None
            with _lock:
                b = load(); t = b["tasks"].get(tid)
                if not t or _is_test(t) or not (t.get("workToDone") and t.get("state") == "working" and t.get("assignee")):
                    continue          # test/demo fixtures never trigger the stall watchdog
                idle = assignee_idle_secs(t["assignee"])
                if idle is None:
                    if t.get("stallPingTs"):                # agent recovered -> reset so next stall re-pings
                        t["stallPingTs"] = 0; save(b)
                    continue
                if (time.time() - (t.get("stallPingTs") or 0)) >= STALL_REPING:
                    t["stallPingTs"] = time.time(); save(b)
                    ping = (t["assignee"], int(idle // 60))
            if ping:
                boss_ping(tid, f"WATCHDOG: assignee {ping[0]} IDLE/stalled ~{ping[1]}m at prompt "
                               f"(no activity) — re-engage or reassign")

# ── mutations ──────────────────────────────────────────────────────────────
def apply_update(d):
    op = d.get("op")
    retire = None                       # (prev_state, task_snapshot) set on a genuine →done transition; run after the lock
    with _lock:
        b = load()
        if op == "add":
            t = new_task(d.get("text", "")); t["test"] = bool(d.get("test")) or _is_test(t)
            if d.get("parent") and d["parent"] in b["tasks"]:   # issue #3: create directly as a subtask of an existing card
                t["parent"] = d["parent"]
            b["tasks"][t["id"]] = t; b["order"].insert(0, t["id"])
            save(b)
            # a created task must NEVER silently die: ping the Boss on create so it's triaged/brainstormed
            # — UNLESS it's a test/demo/proof fixture (exempt: no Boss nudge).
            if not _is_test(t):
                boss_ping(t["id"], "new task created — brainstorm + triage it (no work-to-done toggle needed for it to be seen)")
            return {"ok": True, "id": t["id"]}
        tid = d.get("id"); t = b["tasks"].get(tid)
        if not t: return {"error": "no such task"}
        if op == "del":
            b["tasks"].pop(tid, None); b["order"] = [x for x in b["order"] if x != tid]
            save(b); return {"ok": True}
        if op == "reorder":
            b["order"] = [x for x in d.get("order", []) if x in b["tasks"]]
            save(b); return {"ok": True}
        if op == "addsub":
            t["subs"].append({"id": uid(), "text": d.get("text", ""), "done": False,
                              "doneCondition": d.get("doneCondition", ""), "created": now()})
            t["updated"] = now(); save(b); return {"ok": True}
        if op == "set":
            boss_enqueued = False
            if "doneCondition" in d: t["doneCondition"] = d["doneCondition"]
            if "text" in d: t["text"] = d["text"]
            if "assignee" in d:
                t["assignee"] = d["assignee"]; t["assignedAt"] = now() if d["assignee"] else None
            if "parent" in d:                            # issue #3: parent/child hierarchy
                pid = d["parent"] or None
                if pid and (pid not in b["tasks"] or pid == tid or _creates_cycle(b, tid, pid)):
                    return {"error": "invalid parent (missing, self, or would create a cycle)"}
                t["parent"] = pid
            if "dependsOn" in d:                         # issue #3: 'blocked by' links (existing cards, never self)
                t["dependsOn"] = [x for x in (d["dependsOn"] or []) if x in b["tasks"] and x != tid]
            if "hardGate" in d:                          # issue #3: per-card hard gate (OFF by default)
                t["hardGate"] = bool(d["hardGate"])
            if d.get("workToDone") is True:
                if not (t.get("doneCondition") or "").strip():
                    return {"error": "doneCondition required before workToDone"}
                was_on = bool(t.get("workToDone"))         # only ping on a real OFF->ON transition (idempotent ON = no duplicate ping; complements the client 500ms debounce)
                t["workToDone"] = True
                # SILENT-NO-OP FIX (slice d): the dispatcher only acts on state=='working'. A
                # needs_brainstorm card with work-to-done ON would otherwise sit silent. Surface it
                # (visible lastStatus + a distinct Boss ping) instead of doing nothing.
                if t["state"] == "needs_brainstorm":
                    t["lastStatus"] = "needs brainstorm first — work-to-done is ON but this task won't be worked until it's brainstormed/answered and promoted to working"
                    t["updated"] = now(); save(b)
                    if not was_on: boss_ping(tid, "work-to-done ON but task NEEDS BRAINSTORM — not workable yet; surface questions to the CEO"); boss_enqueued = not was_on
                else:
                    t["updated"] = now(); save(b)
                    if not was_on: boss_ping(tid, "work-to-done toggled ON — drive to done"); boss_enqueued = not was_on
                b = load(); t = b["tasks"][tid]
            elif d.get("workToDone") is False:
                t["workToDone"] = False
            if "state" in d:
                if d["state"] not in VALID_STATES:
                    return {"error": f"invalid state {d['state']!r} (allowed: {sorted(VALID_STATES)})"}
                if d["state"] == "done":                 # Rule 21: only the CEO marks done (one click, any state); AI -> review max
                    if str(d.get("by", "")).strip().upper() == "CEO":
                        t["verified"] = True
                    else:
                        return {"error": "only the CEO marks done (AI/engineer can move up to 'review', never 'done')"}
                if d["state"] == "working" and t["state"] == "needs_brainstorm":
                    return {"error": "not workable before brainstorm (brainstorm gate)"}
                _g = state_gate(b, t, d["state"])        # issue #3: subtask/dependency + hard-gate guardrails
                if _g: return {"error": _g}
                if d["state"] != t["state"]:
                    add_comment(t, f"state: {t['state']} → {d['state']}", d.get("by") or "system", "state")
                _prev_state = t["state"]
                t["state"] = d["state"]
                if d["state"] == "done" and _prev_state != "done":   # genuine CEO →done transition → retire the assignee after the lock
                    retire = (_prev_state, dict(t))
            t["updated"] = now(); save(b)
            res = {"ok": True, "bossEnqueued": boss_enqueued}
        else:
            return {"error": f"unknown op {op!r}"}
    if retire: retire_on_done(retire[0], retire[1])   # OUTSIDE _lock: runs `mp kill`, events the Boss, threads the card
    return res

def _mp_send(agent, msg):
    """Relay a message to an agent via `mp send` (chain of command). Always audit-logs to the boss
    inbox; does the real send when live (not TEST_SINK + mp on PATH). Returns True if sent live."""
    try:
        INBOX_LOG.parent.mkdir(parents=True, exist_ok=True)
        with INBOX_LOG.open("a") as f: f.write(f"{now()} MP_SEND -> {agent} :: {msg[:200]}\n")
    except Exception: pass
    if not TEST_SINK and shutil.which("mp"):
        try:
            r = subprocess.run(["mp", "send", agent, msg], capture_output=True, text=True, timeout=15)
            return r.returncode == 0
        except Exception: return False
    return False

# ── AUTO-RETIRE (card 6934e520b791): when the CEO marks a task DONE, the engineer that was
# assigned to it has finished its job — retire it (mp kill) so it stops churning. This is the
# retirement TRIGGER, fired ONLY on a genuine transition INTO 'done' (Rule 21: CEO-only).
# Server-direct kill (deterministic + directly verifiable, same mechanism as boss_ping/_mp_send),
# PLUS a structured event to the Boss so the Boss knows the task finished + who was retired.
# Edge cases: only on →done (caller passes prev_state); no assignee → no-op; never targets a
# non-assignee (we only ever pass t['assignee']); already-dead engineer → mp kill fails/timeouts,
# we catch + log "already retired (no-op)" and NEVER fail the DONE write.
def retire_on_done(prev_state, t):
    # Must be called OUTSIDE _lock (it runs slow `mp` subprocesses and reloads/saves on its own).
    if prev_state == "done":            # not a real transition (re-save of an already-done card)
        return
    assignee = (t.get("assignee") or "").strip()
    tid = t.get("id", "?")
    def _log(line):
        try:
            INBOX_LOG.parent.mkdir(parents=True, exist_ok=True)
            with INBOX_LOG.open("a") as f: f.write(f"{now()} {line}\n")
        except Exception: pass
    if not assignee:                    # nothing assigned → nothing to retire (clean no-op)
        _log(f"RETIRE task {tid} marked DONE but had no assignee — no-op")
        return
    killed = False; detail = ""
    if not TEST_SINK and shutil.which("mp"):
        try:
            r = subprocess.run(["mp", "kill", assignee], capture_output=True, text=True, timeout=15)
            killed = (r.returncode == 0)
            detail = (r.stdout or r.stderr or "").strip()[:160]
        except Exception as e:
            detail = f"exception {e}"          # already-dead host/agent → timeout/err: clean no-op
    else:
        detail = "TEST_SINK/no-mp — kill skipped (audit only)"
    note = "retired" if killed else "kill no-op (already dead / unreachable)"
    _log(f"RETIRE task {tid} DONE -> mp kill {assignee} :: {note} :: {detail}")
    # tell the Boss the task finished + who was retired (the CEO's "send an event to the boss" intent)
    _mp_send(BOSS_AGENT, f"[todo] task {tid} marked DONE by CEO — auto-retired assignee {assignee} ({note}).")
    # thread the retirement into the card's durable history for the CEO's visibility (own short lock)
    with _lock:
        b = load(); ct = b["tasks"].get(tid)
        if ct:
            add_comment(ct, f"auto-retire: engineer {assignee} {note} (task marked DONE)", "system", "status")
            ct["updated"] = now(); save(b)

def apply_comment(d):
    """Append a comment to a task's thread (slice b) AND make it a two-way channel.
    CHAIN OF COMMAND: a CEO comment is relayed to the BOSS (who redirects to the right engineer) —
    never CEO→engineer directly. Engineer/AI replies (by=<agent id>) just thread back into the card
    for the CEO's visibility (a real two-way GitHub-issue conversation)."""
    with _lock:
        b = load(); t = b["tasks"].get(d.get("task_id") or d.get("id"))
        if not t: return {"error": "no such task"}
        by = d.get("by", "CEO"); is_ceo = str(by).upper() == "CEO"
        c = add_comment(t, d.get("body", ""), by, "comment")
        if not c: return {"error": "empty comment"}
        # COMMENT-ON-REVIEW = MORE WORK: a CEO comment on a 'review' card means work remains, so it
        # auto-kicks back review -> working. Edge-case policy:
        #  (a) ONLY 'review' auto-kicks. working stays working / needs_brainstorm stays gated /
        #      blocked stays blocked / done stays done — but the comment STILL relays to the Boss in
        #      every case (we never lose the relay). Non-review states aren't force-moved (avoid
        #      bypassing the brainstorm gate or silently reopening a done card; use the status control).
        #  (b) ONLY the CEO's comment kicks — an engineer/AI status post (by != CEO) never changes state.
        #  (c) the relay to the Boss happens whether or not it kicked (see below).
        #  (d) no thrash: once kicked it's 'working' (not 'review'), so further comments don't re-kick.
        kicked = is_ceo and t.get("state") == "review"
        if kicked:
            add_comment(t, "state: review → working", by, "state")
            t["state"] = "working"
        t["updated"] = now(); save(b)
        tid = t["id"]; title = (t.get("text") or "")[:70]; assignee = t.get("assignee"); body = c["body"]
    routed = None
    if is_ceo:                                           # relay to the Boss (outside the lock)
        where = f"assigned: {assignee}" if assignee else "UNASSIGNED — assign + relay"
        kick = " [card kicked review→working — more work needed]" if kicked else ""
        sent = _mp_send(BOSS_AGENT, f"[CEO comment on card {tid} “{title}” ({where})]{kick}: {body}\n"
                                    f"→ chain of command: relay to the right engineer (do not expect the CEO to ping them directly).")
        routed = f"boss:{'sent' if sent else 'logged'}"
    wa_reconcile()                                       # if it left 'review', drop it from the CEO WhatsApp digest (slice e)
    return {"ok": True, "comment_id": c["id"], "routed": routed, "kicked": kicked}

# ── CLICK-THE-LINKED-ENGINEER → ATTACH (slice c) ─────────────────────────────
# Mirror the HUD's attach exactly: the live tmux session is `mc-<session>` window `<tab>`, and
# the browser reaches it via ttyd at `<attach_base>/?arg=-t&arg=mc-<session>:<tab>`. The per-host
# ttyd `attach_base` is advertised by each queue-client and exposed on the queue-server's /clients
# (a remote/JOIN host advertises its own tailnet ttyd; the local HUD host has none → the client
# falls back to its own `<location.hostname>:7681`). We resolve the base here (server-side, so the
# queue secret never reaches the browser and there's no cross-origin fetch) and hand the client the
# tmux target + base; the client assembles the final URL with the SAME localhost fallback the HUD uses.
_clients_cache = {"ts": 0.0, "data": []}
def _queue_clients():
    nowt = time.time()
    if nowt - _clients_cache["ts"] < 5 and _clients_cache["data"]:
        return _clients_cache["data"]
    try:
        req = urllib.request.Request(QUEUE_URL + "/clients",
                                     headers={"X-Queue-Secret": SECRET} if SECRET else {})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read() or b"[]")
        if isinstance(data, list):
            _clients_cache["ts"] = nowt; _clients_cache["data"] = data
            return data
    except Exception:
        pass
    return _clients_cache["data"] or []

def resolve_attach(agent_id):
    """Resolve an assignee (`host/session:tab` or `session:tab`) to {target, base} for ttyd attach."""
    agent_id = (agent_id or "").strip()
    host, rest = (agent_id.split("/", 1) + [""])[:2] if "/" in agent_id else (None, agent_id)
    if not rest or ":" not in rest:
        return {"ok": False, "error": f"{agent_id!r} is not an attachable agent (need host/session:tab)"}
    session, tab = rest.split(":", 1)
    if not session.strip() or not tab.strip():
        return {"ok": False, "error": f"{agent_id!r} is not an attachable agent (need host/session:tab)"}
    base = ""
    if host:
        for c in _queue_clients():
            if c.get("hostname") == host:
                base = (c.get("attach_base") or "").strip(); break
    return {"ok": True, "agent": agent_id, "host": host, "target": f"mc-{session}:{tab}", "base": base}

# ── WhatsApp last-hop drain (slice e): outbox + reconcile + drain participant ──
def wa_load():
    try:
        d = json.loads(WA_OUTBOX.read_text())
        if isinstance(d, dict): d.setdefault("queue", []); return d
    except Exception: pass
    return {"queue": []}

def wa_save(d):
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = WA_OUTBOX.with_suffix(".tmp"); tmp.write_text(json.dumps(d, indent=2)); tmp.replace(WA_OUTBOX)

def _blocked_items(b):
    """Cards blocked ON THE CEO → [(tid, kind, title, detail)]. Blocked-on-CEO (all → WhatsApp ping):
    state==review (awaiting his DONE) OR state==blocked (ceoGated — awaiting a CEO decision/answers) OR
    a needs_brainstorm card with unanswered questions (awaiting the CEO's answers)."""
    out = []
    for tid in b.get("order", list(b["tasks"].keys())):
        t = b["tasks"].get(tid)
        if not t or _is_test(t): continue              # test/demo fixtures never enter the CEO WhatsApp digest
        title = (t.get("text") or "").strip()[:80] or "(untitled)"
        st = t.get("state")
        ua = [(q.get("q") or "").strip() for q in t.get("questions", []) if not (q.get("answer") or "").strip()]
        if st == "review":
            out.append((tid, "review", title, ""))
        elif st == "needs_brainstorm" and ua:
            out.append((tid, "brainstorm", title, "\n".join(f"   {i+1}) {q}" for i, q in enumerate(ua))))
        elif st == "blocked":                           # ceoGated -> awaiting the CEO (e.g. brainstorm answers / a decision)
            out.append((tid, "blocked", title, (t.get("lastStatus") or "").strip()[:240]))
    return out

def _deeplink(tid):
    return f"{WA_BOARD_URL}#card/{tid}" if WA_BOARD_URL else f"(card {tid})"

def _build_digest(items):
    """ONE consolidated message listing every blocked-on-CEO card, grouped, each with its deep-link.
    Brainstorm cards list their open questions inline so the CEO can answer straight from the ping."""
    rev = [x for x in items if x[1] == "review"]; bs = [x for x in items if x[1] == "brainstorm"]; bl = [x for x in items if x[1] == "blocked"]
    n = len(items)
    lines = [f"🔔 {n} item{'s' if n != 1 else ''} need you:"]
    if rev:
        lines.append("\nReview — needs your DONE:")
        for tid, _, title, _d in rev: lines.append(f"• {title}\n  {_deeplink(tid)}")
    if bs:
        lines.append("\nBrainstorm — needs your answers:")
        for tid, _, title, detail in bs: lines.append(f"• {title}\n{detail}\n  {_deeplink(tid)}")
    if bl:
        lines.append("\nBlocked on you:")
        for tid, _, title, detail in bl: lines.append(f"• {title}" + (f" — {detail}" if detail else "") + f"\n  {_deeplink(tid)}")
    return "\n".join(lines)

def wa_reconcile():
    """CEO-watchdog pass: if ≥1 card is blocked on the CEO, enqueue ONE consolidated digest (throttled
    to ~one per WA_WATCHDOG tick); if none are blocked, cancel any pending digest. Idempotent."""
    if not WA_DRAIN_ON: return
    items = _blocked_items(load()); nowt = now()
    with _wa_lock:
        o = wa_load(); q = o["queue"]
        if not items:                                      # nothing blocked -> cancel any unsent digest, stop
            ch = False
            for e in q:
                if e.get("sentAt") is None and not e.get("canceled"): e["canceled"] = True; ch = True
            if ch: wa_save(o)
            return
        if any(e.get("sentAt") is None and not e.get("canceled") for e in q):
            return                                         # a digest is already pending (don't pile up)
        last = max([e.get("sentAt") or 0 for e in q] or [0])
        if last and (nowt - last) < WA_REPING * 1000:      # sent one recently -> next tick
            return
        q.append({"id": uid(), "kind": "digest", "dedupKey": "digest", "text": _build_digest(items),
                  "count": len(items), "created": nowt, "sentAt": None, "attempts": 0, "lastError": "", "canceled": False})
        o["queue"] = q[-500:]; wa_save(o)

def wa_send(text):
    """THE LAST HOP — hand the message to the containerized Hermes bridge → CEO WhatsApp.
    Builds {chatId, message} JSON and pipes it to WA_SEND_CMD on stdin. Returns (ok, info)."""
    payload = json.dumps({"chatId": WA_CHAT_JID, "message": text})
    try:
        r = subprocess.run(WA_SEND_CMD, shell=True, input=payload, capture_output=True, text=True, timeout=30)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        ok = '"success":true' in out.replace(" ", "") or '"messageid"' in out.lower()
        return ok, out[:200]
    except Exception as e:
        return False, str(e)[:200]

def wa_drain_once():
    with _wa_lock:
        pend = [dict(e) for e in wa_load()["queue"] if e.get("sentAt") is None and not e.get("canceled")]
    for e in pend:
        with _wa_lock:                                     # re-check: a reconcile may have canceled it (block cleared) since the snapshot
            cur = next((x for x in wa_load()["queue"] if x["id"] == e["id"]), None)
            if not cur or cur.get("sentAt") or cur.get("canceled"): continue
        ok, info = wa_send(e["text"])
        with _wa_lock:
            o = wa_load(); cur = next((x for x in o["queue"] if x["id"] == e["id"]), None)
            if not cur or cur.get("canceled"): continue    # canceled mid-send -> don't record as sent
            cur["attempts"] = cur.get("attempts", 0) + 1
            if ok: cur["sentAt"] = now(); cur["info"] = info
            else:  cur["lastError"] = info
            wa_save(o)

def wa_drain_loop():
    while True:
        time.sleep(WA_DRAIN_SEC)
        if WA_DRAIN_ON:
            try: wa_drain_once()
            except Exception: pass

def wa_watchdog_loop():
    while True:
        time.sleep(WA_WATCHDOG)
        try: wa_reconcile()
        except Exception: pass

def apply_brainstorm(d):
    with _lock:
        b = load(); t = b["tasks"].get(d.get("id"))
        if not t: return {"error": "no such task"}
        prev_bs, prev_state = t.get("brainstorm", ""), t["state"]
        who = d.get("by") or "brainstorm"
        # the worker posts generated clarifying questions (state stays needs_brainstorm)
        if "questions" in d and isinstance(d["questions"], list):
            t["questions"] = [{"id": uid(), "q": str(q).strip(), "answer": "",
                               "askedAt": now(), "answeredAt": None}
                              for q in d["questions"] if str(q).strip()]
            t["brainstormAsked"] = True
            n = len(t["questions"])
            add_comment(t, (f"brainstorm generated {n} clarifying question(s) — answer them in the card to unblock this task."
                            if n else "brainstorm: task is clear enough to work — no open questions."), who, "brainstorm")
            if n:
                t["lastStatus"] = f"needs brainstorm — {n} question(s) awaiting the CEO"
        if "brainstorm" in d:
            t["brainstorm"] = d.get("brainstorm", t.get("brainstorm", ""))
            if t["brainstorm"].strip() and t["brainstorm"] != prev_bs:
                add_comment(t, t["brainstorm"], who, "brainstorm")
        if d.get("promote") and t["state"] == "needs_brainstorm":
            if not brainstorm_ready(t):
                ua = len(_unanswered(t))
                return {"error": f"brainstorm gate: {ua} unanswered question(s) — answer them before promoting"
                                 if ua else "brainstorm gate: no brainstorm artifact yet"}
            _g = state_gate(b, t, "working")             # issue #3: respect the hard gate on promote→working
            if _g: return {"error": _g}
            _assemble_artifact(t)
            t["state"] = "working"; t["lastStatus"] = ""
        if t["state"] != prev_state:
            add_comment(t, f"state: {prev_state} → {t['state']}", who, "state")
        t["updated"] = now(); save(b)
        res = {"ok": True, "state": t["state"], "ready": brainstorm_ready(t), "unanswered": len(_unanswered(t))}
    wa_reconcile()                                   # questions posted (brainstorm-pending) -> enqueue WhatsApp (slice e)
    return res

def apply_answer(d):
    """CEO answers a generated brainstorm question in the card. When the last one is answered,
    the artifact is assembled and the task becomes promotable (still needs_brainstorm until promoted)."""
    with _lock:
        b = load(); t = b["tasks"].get(d.get("task_id") or d.get("id"))
        if not t: return {"error": "no such task"}
        qid, ans = d.get("qid"), (d.get("answer") or "").strip()
        q = next((x for x in t.get("questions", []) if x.get("id") == qid), None)
        if not q: return {"error": "no such question"}
        if not ans: return {"error": "empty answer"}
        q["answer"] = ans; q["answeredAt"] = now()
        add_comment(t, f"Q: {q.get('q','').strip()}\nA: {ans}", d.get("by", "CEO"), "comment")
        ua = len(_unanswered(t))
        if ua == 0:
            _assemble_artifact(t)
            t["lastStatus"] = "brainstorm answered — ready to promote to working"
        else:
            t["lastStatus"] = f"needs brainstorm — {ua} question(s) still awaiting the CEO"
        t["updated"] = now(); save(b)               # persist the answer BEFORE pinging (boss_ping reloads from disk)
    wa_reconcile()                                   # an answer may clear the brainstorm block -> cancel its WhatsApp ping (slice e)
    if ua == 0:                                      # ping outside the lock; it reloads the just-saved state
        boss_ping(d.get("task_id") or d.get("id"), "brainstorm gate cleared — all questions answered; promote to working")
    return {"ok": True, "unanswered": ua, "ready": True if ua == 0 else False}

def apply_status(d):
    with _lock:
        b = load(); t = b["tasks"].get(d.get("id"))
        if not t: return {"error": "no such task"}
        who = d.get("by") or t.get("assignee") or "engineer"
        prev_state = t["state"]
        if "lastStatus" in d:
            t["lastStatus"] = d["lastStatus"]
            add_comment(t, d["lastStatus"], who, "status")   # engineer's voice -> durable thread event
        if "verified" in d: t["verified"] = bool(d["verified"])
        if "state" in d:
            if d["state"] not in VALID_STATES:
                return {"error": f"invalid state {d['state']!r} (allowed: {sorted(VALID_STATES)})"}
            if d["state"] == "done":
                # Rule 21: ONLY the CEO marks done — his action IS the sign-off + verification, in ONE
                # step from ANY state (working / needs_brainstorm / blocked / review). The AI/engineer
                # can move a card UP TO 'review' for CEO sign-off but can NEVER set 'done' (the gate
                # exists solely to stop the AI auto-closing unready work — it must not gate the CEO).
                if str(d.get("by", "")).strip().upper() == "CEO":
                    t["verified"] = True
                else:
                    return {"error": "only the CEO marks done — AI/engineer can move a card up to 'review' for CEO sign-off, never to 'done'"}
            _g = state_gate(b, t, d["state"])            # issue #3: subtask/dependency + hard-gate guardrails
            if _g: return {"error": _g}
            t["state"] = d["state"]
        if d.get("ceoGated"):           # engineer signals done-pending-CEO -> blocked (CEO window/decision gates it)
            t["state"] = "blocked"      # the watchdog + unassigned cron skip 'blocked' -> no false stall-nag
        if t["state"] != prev_state:
            add_comment(t, f"state: {prev_state} → {t['state']}", who, "state")
        t["updated"] = now(); save(b)
        retire = (prev_state, dict(t)) if (t["state"] == "done" and prev_state != "done") else None
    wa_reconcile()                                   # CEO-blocked? (review/blocked) -> enqueue WhatsApp (slice e)
    if retire: retire_on_done(retire[0], retire[1])  # OUTSIDE _lock: CEO →done → retire the assignee (mp kill) + event the Boss
    return {"ok": True, "state": t["state"]}

def apply_proof(d):
    with _lock:
        b = load(); tid = d.get("task_id"); t = b["tasks"].get(tid)
        if not t: return {"error": "no such task"}
        ptype = d.get("type", "text"); ref = d.get("ref", ""); pid = uid()
        if ptype in ("image", "video") and d.get("data_b64"):
            PD = PROOF_DIR / tid; PD.mkdir(parents=True, exist_ok=True)
            ext = (d.get("ext") or ("png" if ptype == "image" else "mp4")).lstrip(".")
            raw = d["data_b64"]
            if raw.startswith("data:"): raw = raw.split(",", 1)[1]   # strip data-URL prefix
            fp = PD / f"{pid}.{ext}"; fp.write_bytes(base64.b64decode(raw))
            ref = f"/todo/proof/{tid}/{pid}.{ext}"   # a SERVED url, not a filesystem path
        elif ptype in ("image", "video") and ref and not ref.startswith("/todo/proof/"):
            url = _ingest_file(tid, pid, ptype, ref)   # attached by path/file:// -> copy in + serve
            if url: ref = url
        proof = {"id": pid, "type": ptype, "ref": ref, "caption": d.get("caption", ""),
                 "by": d.get("by", "engineer"), "ts": now()}
        t["proofs"].append(proof); t["updated"] = now(); save(b)
        return {"ok": True, "proof_id": pid}

# ── HTTP ───────────────────────────────────────────────────────────────────
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")  # never cache the board HTML/JSON — the CEO must always get the latest board JS (stale JS = the modal bug he kept hitting)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Queue-Secret")
        self.end_headers(); self.wfile.write(body)
    def _serve_bytes(self, data, ctype):
        """Serve a binary with HTTP Range support so <video> can seek (CEO: watch proof on the board)."""
        total = len(data); rng = self.headers.get("Range", ""); partial = False; start, end = 0, total - 1
        if rng.startswith("bytes="):
            try:
                s, _, e = rng[6:].partition("-")
                start = int(s) if s else 0
                end = int(e) if e else total - 1
                if 0 <= start <= end < total: partial = True
            except Exception: partial = False
        chunk = data[start:end + 1] if partial else data
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        if partial: self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(chunk)
        except Exception: pass
    def _auth(self):
        return (not SECRET) or self.headers.get("X-Queue-Secret", "") == SECRET
    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        try: return json.loads(self.rfile.read(n) or b"{}")
        except Exception: return {}
    def do_OPTIONS(self): self._send(204, b"", "text/plain")
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/health": return self._send(200, {"status": "ok", "service": "todo", "build": _build_stamp()})
        if p in ("/todos", "/todos/", "/"):
            try:
                html = HTML_PATH.read_text().replace("__QUEUE_SECRET__", SECRET).replace("__BUILD__", _build_stamp())
                return self._send(200, html, "text/html; charset=utf-8")
            except Exception as e: return self._send(500, {"error": f"html: {e}"})
        if p.startswith("/todo/proof/"):     # serve proof binaries (public, so <img src> works)
            seg = p[len("/todo/proof/"):].strip("/").split("/")
            if len(seg) == 2 and seg[1] and ".." not in seg[0] and ".." not in seg[1]:
                fp = PROOF_DIR / seg[0] / seg[1]
                try:
                    data = fp.read_bytes()
                except Exception: return self._send(404, {"error": "no such proof"})
                ext = fp.suffix.lower().lstrip(".")
                ctype = {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","gif":"image/gif",
                         "webp":"image/webp","svg":"image/svg+xml","mp4":"video/mp4","webm":"video/webm",
                         "mov":"video/quicktime"}.get(ext, "application/octet-stream")
                return self._serve_bytes(data, ctype)   # Range-aware -> inline video playback + seeking
            return self._send(404, {"error": "bad proof path"})
        if p == "/todo/board":
            if not self._auth(): return self._send(403, {"error": "unauthorized"})
            with _lock: b = migrate_proofs(load())
            b = dict(b); b["build"] = _build_stamp()      # client auto-reloads if the served HTML build changed (kills stale-JS bugs)
            return self._send(200, b)
        if p == "/todo/attach":               # resolve an assignee -> ttyd attach target (slice c)
            if not self._auth(): return self._send(403, {"error": "unauthorized"})
            agent = (parse_qs(urlparse(self.path).query).get("agent") or [""])[0]
            return self._send(200, resolve_attach(agent))
        if p == "/todo/wa":                   # inspect the WhatsApp outbox (slice e)
            if not self._auth(): return self._send(403, {"error": "unauthorized"})
            with _wa_lock: o = wa_load()
            pend = [e for e in o["queue"] if e.get("sentAt") is None and not e.get("canceled")]
            return self._send(200, {"jid": WA_CHAT_JID, "drain": WA_DRAIN_ON, "pending": len(pend),
                                    "queue": o["queue"][-50:]})
        return self._send(404, {"error": "not found"})
    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p == "/hook/stop":            # used by the stop-hook bridge / sim-stop-hook
            d = self._body(); on_stop_hook(d.get("agent", ""), d.get("state", "idle"))
            return self._send(200, {"ok": True})
        if not self._auth(): return self._send(403, {"error": "forbidden"})
        d = self._body()
        if p == "/todo/update":     return self._send(200, apply_update(d))
        if p == "/todo/brainstorm": return self._send(200, apply_brainstorm(d))
        if p == "/todo/status":     return self._send(200, apply_status(d))
        if p == "/todo/proof":      return self._send(200, apply_proof(d))
        if p == "/todo/comment":    return self._send(200, apply_comment(d))
        if p == "/todo/answer":     return self._send(200, apply_answer(d))
        if p == "/todo/wa/test":    # enqueue a one-off message (proof / smoke) -> drained to CEO WhatsApp
            txt = (d.get("text") or "Board test ping.").strip()
            with _wa_lock:
                o = wa_load(); o["queue"].append({"id": uid(), "task_id": None, "kind": "test",
                    "dedupKey": f"test:{uid()}", "text": txt, "created": now(), "sentAt": None,
                    "attempts": 0, "lastError": "", "canceled": False}); wa_save(o)
            return self._send(200, {"ok": True, "enqueued": txt})
        if p == "/todo/wa/drain":   threading.Thread(target=wa_drain_once, daemon=True).start(); return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True; allow_reuse_address = True

if __name__ == "__main__":
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    if not BOARD_PATH.exists(): save(_default_board())
    threading.Thread(target=cron_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop, daemon=True).start()
    if WA_DRAIN_ON:                                  # slice e: CEO-blocked watchdog + WhatsApp drain participant
        threading.Thread(target=wa_watchdog_loop, daemon=True).start()
        threading.Thread(target=wa_drain_loop, daemon=True).start()
    print(f"todo :{PORT}  store={BOARD_PATH}  cron={PING_CRON}s grace={IDLE_GRACE}s "
          f"stall={IDLE_STALL}s/scan{WATCHDOG}s sink={'file' if TEST_SINK else 'mp'} "
          f"wa={'on→'+WA_CHAT_JID if WA_DRAIN_ON else 'off'}", flush=True)
    Server(("0.0.0.0", PORT), H).serve_forever()
