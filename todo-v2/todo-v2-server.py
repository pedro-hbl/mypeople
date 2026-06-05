#!/usr/bin/env python3
"""todo-v2 server — the CEO's priority board as the Boss's source of truth.

Slice: API + shared store + PING STATE MACHINE. Designed to be inlined (heredoc)
into seeds/todo-v2.seed.md and to run either:
  - standalone in a clean container (boss pings go to a file sink; TODO_TEST_SINK=1), or
  - on top of a live mypeople runtime (boss pings go through `mp send main:Boss`).

Store : $TODO_DIR/board.v2.json   proofs: $TODO_DIR/proofs/<task_id>/
Env   : QUEUE_PORT(9900) QUEUE_SECRET('') TODO_DIR(~/mypeople/todos)
        PING_CRON_SEC(60) IDLE_GRACE_SEC(60) TODO_HTML(<dir>/todos.html)
        TODO_TEST_SINK(0)  BOSS_AGENT(main:Boss)
"""
import http.server, json, os, threading, time, uuid, base64, subprocess, shutil, datetime
from pathlib import Path

PORT        = int(os.environ.get("QUEUE_PORT", "9900"))
SECRET      = os.environ.get("QUEUE_SECRET", "")
TODO_DIR    = Path(os.environ.get("TODO_DIR", str(Path(__file__).resolve().parent / "data")))  # durable, beside the server (NOT /tmp)
PROOF_DIR   = TODO_DIR / "proofs"
BOARD_PATH  = TODO_DIR / "board.v2.json"
INBOX_LOG   = TODO_DIR / "boss-inbox.log"
PING_CRON   = float(os.environ.get("PING_CRON_SEC", "120"))   # unassigned-card cron (CEO: 2 min)
IDLE_GRACE  = float(os.environ.get("IDLE_GRACE_SEC", "60"))    # assigned idle-post-stop-hook (1 min)
IDLE_STALL  = float(os.environ.get("IDLE_STALL_SEC", "300"))   # assigned-but-idle WATCHDOG threshold (5 min)
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

DISPATCHABLE_FROM = {"ready"}
ACTIVE = lambda t: t.get("workToDone") and t.get("state") != "done"
_lock = threading.RLock()
# per-agent last stop-hook state: agent_id -> "idle" | "working"
_hook_state = {}

def now(): return int(time.time() * 1000)
def uid(): return uuid.uuid4().hex[:12]

def _default_board(): return {"version": "v2", "order": [], "tasks": {}}

def load():
    try:
        b = json.loads(BOARD_PATH.read_text())
        if not isinstance(b, dict) or b.get("version") != "v2": return _default_board()
        b.setdefault("order", []); b.setdefault("tasks", {})
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
            "verified": False, "lastStatus": "", "proofs": [], "subs": [],
            "pingsToBoss": 0, "assignedAt": None, "lastStopTs": None,
            "created": now(), "updated": now()}

# ── Boss ping: the ONLY thing the ping machine does. Always targets the Boss. ──
def boss_ping(task_id, reason):
    with _lock:
        b = load()
        t = b["tasks"].get(task_id)
        if not t: return
        t["pingsToBoss"] = t.get("pingsToBoss", 0) + 1
        t["updated"] = now()
        save(b)
        msg = f"[todo-v2] task {task_id} ({t.get('text','')!r}): {reason}. " \
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
            if t and ACTIVE(t) and not t.get("assignee") and t.get("state") != "blocked":
                reason = "needs brainstorm" if t["state"] == "needs_brainstorm" \
                         else "ready & unassigned — assign+dispatch"
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

def assignee_idle_secs(agent_id):
    """Idle seconds if the assigned agent looks parked/stalled, else None (active/grace/busy-job)."""
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
                if not t or not (t.get("workToDone") and t.get("state") in ("dispatched", "working") and t.get("assignee")):
                    continue
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
    with _lock:
        b = load()
        if op == "add":
            t = new_task(d.get("text", "")); b["tasks"][t["id"]] = t; b["order"].insert(0, t["id"])
            save(b); return {"ok": True, "id": t["id"]}
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
            if d.get("workToDone") is True:
                if not (t.get("doneCondition") or "").strip():
                    return {"error": "doneCondition required before workToDone"}
                t["workToDone"] = True
                # refinement #3: turning the toggle ON enqueues a message to the Boss
                t["updated"] = now(); save(b)
                boss_ping(tid, "work-to-done toggled ON — drive to done"); boss_enqueued = True
                b = load(); t = b["tasks"][tid]
            elif d.get("workToDone") is False:
                t["workToDone"] = False
            if "state" in d:
                if d["state"] == "done" and not t.get("verified"):
                    return {"error": "cannot set done without verified"}
                if d["state"] in ("dispatched", "working") and t["state"] == "needs_brainstorm":
                    return {"error": "not dispatchable before ready (brainstorm gate)"}
                t["state"] = d["state"]
            t["updated"] = now(); save(b)
            return {"ok": True, "bossEnqueued": boss_enqueued}
        return {"error": f"unknown op {op!r}"}

def apply_brainstorm(d):
    with _lock:
        b = load(); t = b["tasks"].get(d.get("id"))
        if not t: return {"error": "no such task"}
        t["brainstorm"] = d.get("brainstorm", t.get("brainstorm", ""))
        if d.get("promote") == "ready" and t["state"] == "needs_brainstorm" and t["brainstorm"].strip():
            t["state"] = "ready"
        t["updated"] = now(); save(b)
        return {"ok": True, "state": t["state"]}

def apply_status(d):
    with _lock:
        b = load(); t = b["tasks"].get(d.get("id"))
        if not t: return {"error": "no such task"}
        if "lastStatus" in d: t["lastStatus"] = d["lastStatus"]
        if "verified" in d: t["verified"] = bool(d["verified"])
        if "state" in d:
            if d["state"] == "done" and not t.get("verified"):
                return {"error": "cannot set done without verified"}
            t["state"] = d["state"]
        if d.get("ceoGated"):           # engineer signals done-pending-CEO -> blocked (CEO window/decision gates it)
            t["state"] = "blocked"      # the watchdog + unassigned cron skip 'blocked' -> no false stall-nag
        t["updated"] = now(); save(b)
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Queue-Secret")
        self.end_headers(); self.wfile.write(body)
    def _auth(self):
        return (not SECRET) or self.headers.get("X-Queue-Secret", "") == SECRET
    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        try: return json.loads(self.rfile.read(n) or b"{}")
        except Exception: return {}
    def do_OPTIONS(self): self._send(204, b"", "text/plain")
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/health": return self._send(200, {"status": "ok", "service": "todo-v2"})
        if p in ("/todos", "/todos/", "/"):
            try:
                html = HTML_PATH.read_text().replace("__QUEUE_SECRET__", SECRET)
                return self._send(200, html, "text/html; charset=utf-8")
            except Exception as e: return self._send(500, {"error": f"html: {e}"})
        if p.startswith("/todo/proof/"):     # serve proof binaries (public, so <img src> works)
            seg = p[len("/todo/proof/"):].strip("/").split("/")
            if len(seg) == 2 and seg[1] and ".." not in seg[0] and ".." not in seg[1]:
                fp = PROOF_DIR / seg[0] / seg[1]
                try:
                    data = fp.read_bytes()
                    ext = fp.suffix.lower().lstrip(".")
                    ctype = {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","gif":"image/gif",
                             "webp":"image/webp","svg":"image/svg+xml","mp4":"video/mp4","webm":"video/webm",
                             "mov":"video/quicktime"}.get(ext, "application/octet-stream")
                    return self._send(200, data, ctype)
                except Exception: return self._send(404, {"error": "no such proof"})
            return self._send(404, {"error": "bad proof path"})
        if p == "/todo/board":
            if not self._auth(): return self._send(403, {"error": "unauthorized"})
            with _lock: b = migrate_proofs(load())
            return self._send(200, b)
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
        return self._send(404, {"error": "not found"})

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True; allow_reuse_address = True

if __name__ == "__main__":
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    if not BOARD_PATH.exists(): save(_default_board())
    threading.Thread(target=cron_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop, daemon=True).start()
    print(f"todo-v2 :{PORT}  store={BOARD_PATH}  cron={PING_CRON}s grace={IDLE_GRACE}s "
          f"stall={IDLE_STALL}s/scan{WATCHDOG}s sink={'file' if TEST_SINK else 'mp'}", flush=True)
    Server(("0.0.0.0", PORT), H).serve_forever()
