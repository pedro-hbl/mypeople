# SEED: pr-autoapprove

> seed-format: 1

## Goal

Watch tracked GitHub repos for new PR comments / reviews / mentions, deliver them to the Boss via the mypeople queue, and **auto-approve** any PR whose comment contains a configurable approve-command (default `/<GITHUB_USER>-approve`) by running `gh pr review --approve`.

This is a sibling of [`mypeople.seed.md`](mypeople.seed.md) — a separate layer that depends on mypeople already being installed and the queue running.

After install: a `pr-autoapprove` daemon runs on this host, polls GitHub every N seconds for new events on `WATCHED_REPOS`, pushes each relevant event as an `mp send` task targeting the Boss, and auto-approves PRs where someone typed the approve-command in a comment.

## Depends on

- **mypeople** is installed and healthy on this host. The Boss agent (`<host>/main:Boss` by default) exists and is reachable via the queue. Step 0 Interview verifies with `mp status` showing the Boss alive.
- `gh` CLI installed and authenticated (`gh auth status` reports a logged-in user).

If either is missing: `BLOCKED_REASON=mypeople_not_installed` or `BLOCKED_REASON=gh_not_authed`.

## Done

- `~/mypeople/bin/gh-pr-watcher.py` exists and is executable.
- `~/.config/mypeople/gh-pr-watcher.env` contains `WATCHED_REPOS`, `SELF_USER`, `APPROVE_COMMAND`, `POLL_INTERVAL`, `BOSS_TARGET`.
- A `gh-pr-watcher` daemon process is alive (poll loop running). PID file at `~/mypeople/run/gh-pr-watcher.pid`.
- State file `~/mypeople/run/gh-pr-watcher-state.json` exists; first run initializes seen-ids without spamming.
- Smoke: comment `/<SELF_USER>-approve` on a tracked test PR → within `POLL_INTERVAL`+`gh latency` seconds:
  - `gh pr view <pr> --json reviews` shows a review by SELF_USER with state APPROVED;
  - the Boss's pane has received an `[AUTO-APPROVED] <repo>#<pr> ...` line via `mp send`.

## Inputs

| name | required | default | detect | ask |
|---|---|---|---|---|
| `SELF_USER` | yes | none | `gh api user --jq .login` returns a login | "Your GitHub username (used to (a) form the approve-command `/<user>-approve` and (b) decide what counts as 'mentions me' / 'own-PR'). Default suggestion: `$(gh api user --jq .login)`." |
| `WATCHED_REPOS` | yes | none | `[ -s ~/.config/mypeople/gh-pr-watcher.env ] && grep -q WATCHED_REPOS=` | "Comma-separated `owner/repo` list to poll (e.g. `cncorp/plow,cncorp/codel-text`). At least one." |
| `APPROVE_REPOS` | no | (same as `WATCHED_REPOS`) | env file | "Subset of WATCHED_REPOS where `/<SELF_USER>-approve` actually triggers `gh pr review --approve`. Other repos: notify-only. Default: all watched repos." |
| `APPROVE_COMMAND` | no | `/<SELF_USER>-approve` | env file | "The comment marker that triggers auto-approval. Default: `/<SELF_USER>-approve`. Word-boundary matched so near-misses like `/<user>-approve-later` don't trigger." |
| `POLL_INTERVAL` | no | `60` (seconds) | env file | "How often to poll GitHub. 60s is friendly to GH rate limits. Lower for tighter latency." |
| `BOSS_TARGET` | no | `<host>/main:Boss` | env file | "Full agent_id of the Boss to notify. Default: this host's main:Boss." |
| `IGNORED_USERS` | no | `corgea[bot]` | env file | "Comma-separated GH users to silence entirely (bots, self-reviews). Comments / reviews from these users never trigger notifications. Approve-commands from these users are still honored (intentional — a bot can post the marker after CI passes)." |
| `gh` CLI authed | yes | host-provided | `gh auth status` reports `Logged in` | `BLOCKED_REASON=gh_not_authed` — run `gh auth login` first. |
| mypeople healthy | yes | from prior seed | `mp status` lists the Boss alive | `BLOCKED_REASON=mypeople_not_installed` — install [`mypeople.seed.md`](mypeople.seed.md) first. |

## Components

| Component | Source | Notes |
|---|---|---|
| `gh-pr-watcher.py` | **inline in this seed** | polls GH, decides relevance, posts to queue, runs approve-command |
| state file | `~/mypeople/run/gh-pr-watcher-state.json` | `seen_ids[]`, `initialized_prs[]` so first run doesn't blast every existing comment |
| event archive | `~/.gh-pr-watcher/inbox/*.json` | full payloads so Boss can read more than the message snippet |
| `gh` CLI | host-provided | `gh api`, `gh pr view`, `gh pr review --approve` |

## Steps

### 0. Interview (mandatory)

Detect each `## Inputs` row. Send ONE consolidated message to the CEO listing what's satisfied, what's missing, and what defaults will be used. Wait for reply. Then run autonomously.

### 1. Verify prerequisites

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
command -v mp >/dev/null || { echo "BLOCKED_REASON=mypeople_not_installed"; exit 1; }
mp status >/dev/null 2>&1 || { echo "BLOCKED_REASON=mypeople_queue_unreachable"; exit 1; }
command -v gh >/dev/null || { echo "BLOCKED_REASON=gh_not_installed"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "BLOCKED_REASON=gh_not_authed (run: gh auth login)"; exit 1; }
```

### 2. Stop any prior watcher

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
[ -f "$INSTALL_DIR/run/gh-pr-watcher.pid" ] && kill "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/gh-pr-watcher.py" 2>/dev/null || true
```

### 3. Write `~/.config/mypeople/gh-pr-watcher.env`

```bash
mkdir -p "$HOME/.config/mypeople"
SELF_USER="${SELF_USER:?must be set}"
WATCHED_REPOS="${WATCHED_REPOS:?must be set}"
APPROVE_REPOS="${APPROVE_REPOS:-$WATCHED_REPOS}"
APPROVE_COMMAND="${APPROVE_COMMAND:-/${SELF_USER}-approve}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"
BOSS_TARGET="${BOSS_TARGET:-$(hostname -s)/main:Boss}"
IGNORED_USERS="${IGNORED_USERS:-corgea[bot]}"
cat > "$HOME/.config/mypeople/gh-pr-watcher.env" <<EOF
WATCHED_REPOS=${WATCHED_REPOS}
APPROVE_REPOS=${APPROVE_REPOS}
SELF_USER=${SELF_USER}
APPROVE_COMMAND=${APPROVE_COMMAND}
POLL_INTERVAL=${POLL_INTERVAL}
BOSS_TARGET=${BOSS_TARGET}
IGNORED_USERS=${IGNORED_USERS}
EOF
chmod 600 "$HOME/.config/mypeople/gh-pr-watcher.env"
```

### 4. Write `gh-pr-watcher.py` (inline)

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/run" "$HOME/.gh-pr-watcher/inbox"
cat > "$INSTALL_DIR/bin/gh-pr-watcher.py" <<'PY_EOF'
#!/usr/bin/env python3
"""mypeople gh-pr-watcher.

Polls open PRs in WATCHED_REPOS for new comments / reviews / inline review
comments. Two outputs per relevant event:
  1. Push an `mp send` task to the Boss via the queue.
  2. If the event body contains APPROVE_COMMAND and the repo is in
     APPROVE_REPOS, run `gh pr review --approve` and surface that to Boss
     with an [AUTO-APPROVED] line.
"""

from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "mypeople" / "gh-pr-watcher.env"
INSTALL_DIR = Path(os.environ.get("INSTALL_DIR", str(Path.home() / "mypeople")))
STATE_FILE = INSTALL_DIR / "run" / "gh-pr-watcher-state.json"
INBOX_DIR = Path.home() / ".gh-pr-watcher" / "inbox"
QUEUE_ENV = Path.home() / ".config" / "mypeople" / "queue.env"
GH_TIMEOUT = 20


def load_env(path: Path) -> dict:
    d = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


CFG = load_env(CONFIG)
QC = load_env(QUEUE_ENV)
SELF_USER = CFG.get("SELF_USER", "")
WATCHED_REPOS = [r.strip() for r in CFG.get("WATCHED_REPOS", "").split(",") if r.strip()]
APPROVE_REPOS = set(r.strip() for r in CFG.get("APPROVE_REPOS", "").split(",") if r.strip()) or set(WATCHED_REPOS)
APPROVE_COMMAND = CFG.get("APPROVE_COMMAND", f"/{SELF_USER}-approve")
POLL_INTERVAL = int(CFG.get("POLL_INTERVAL", "60"))
BOSS_TARGET = CFG.get("BOSS_TARGET", "")
IGNORED_USERS = set(u.strip() for u in CFG.get("IGNORED_USERS", "").split(",") if u.strip())

QUEUE_URL = QC.get("QUEUE_URL", "http://127.0.0.1:9900")
QUEUE_SECRET = QC.get("QUEUE_SECRET", "")

MENTION_RE = re.compile(rf"(?<![A-Za-z0-9_])@{re.escape(SELF_USER)}\b", re.IGNORECASE) if SELF_USER else None
APPROVE_RE = re.compile(rf"(?<![A-Za-z0-9_/]){re.escape(APPROVE_COMMAND)}(?![A-Za-z0-9_-])")


def mentions_self(body: str) -> bool:
    return bool(MENTION_RE and MENTION_RE.search(body or ""))


def is_approve_command(event: dict) -> bool:
    if event["repo"] not in APPROVE_REPOS:
        return False
    if event["kind"] not in ("comment", "review", "review_comment"):
        return False
    return bool(APPROVE_RE.search(event.get("body") or ""))


def approve_pr(repo: str, pr: int) -> tuple[bool, str]:
    try:
        r = subprocess.run(["gh", "pr", "review", str(pr), "--approve", "--repo", repo],
                           capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, (r.stdout or "").strip()


def notify_reason(event: dict, pr_author: str) -> str | None:
    if event["user"] in IGNORED_USERS:
        return None
    if pr_author == SELF_USER:
        return "own-PR"
    if mentions_self(event.get("body", "")):
        return "mention"
    return None


def push_to_boss(message: str) -> bool:
    if not BOSS_TARGET or "/" not in BOSS_TARGET:
        print("  ERROR: BOSS_TARGET not set or malformed", file=sys.stderr)
        return False
    target_host = BOSS_TARGET.split("/", 1)[0]
    task = {
        "action": "send",
        "target_host": target_host,
        "target_agent": BOSS_TARGET,
        "payload": {"message": message},
    }
    body = json.dumps(task).encode()
    headers = {"Content-Type": "application/json", "X-Queue-Secret": QUEUE_SECRET}
    req = urllib.request.Request(f"{QUEUE_URL}/task/submit", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read())
            print(f"  → queued task {r.get('task_id', '?')[:8]}")
            return True
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ERROR push: {e}", file=sys.stderr)
        return False


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"seen_ids": [], "initialized_prs": []}
    try:
        d = json.loads(STATE_FILE.read_text())
        d.setdefault("seen_ids", []); d.setdefault("initialized_prs", [])
        return d
    except json.JSONDecodeError:
        return {"seen_ids": [], "initialized_prs": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["seen_ids"] = state["seen_ids"][-2000:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


def gh_api(path: str, paginate: bool = True) -> list | dict:
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd.append(path)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"  gh api {path!r} failed: {e}", file=sys.stderr)
        return []
    if r.returncode != 0:
        print(f"  gh api {path!r} returncode={r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        return []
    out = r.stdout.strip()
    if not out:
        return []
    if paginate:
        # gh --paginate concatenates JSON arrays; merge them.
        merged = []
        for chunk in out.replace("][", ",").split("\n"):
            try:
                v = json.loads(chunk)
                if isinstance(v, list):
                    merged.extend(v)
                else:
                    merged.append(v)
            except json.JSONDecodeError:
                pass
        return merged
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def discover_open_prs(repos: list[str]) -> list[tuple[str, int, str]]:
    """Return [(repo, pr_number, author_login), ...] for open PRs."""
    items = []
    for repo in repos:
        prs = gh_api(f"/repos/{repo}/pulls?state=open&per_page=50", paginate=False)
        for p in prs or []:
            items.append((repo, int(p["number"]), p["user"]["login"]))
    return items


def fetch_pr_events(repo: str, pr: int) -> list[dict]:
    """Return a unified list of [{kind, id, user, body, repo, pr, extra}]."""
    events = []
    for ic in gh_api(f"/repos/{repo}/issues/{pr}/comments?per_page=100"):
        events.append({"kind": "comment", "id": ic["id"], "user": ic["user"]["login"], "body": ic.get("body") or "", "repo": repo, "pr": pr, "extra": {}})
    for rv in gh_api(f"/repos/{repo}/pulls/{pr}/reviews?per_page=100"):
        events.append({"kind": "review", "id": rv["id"], "user": rv["user"]["login"], "body": rv.get("body") or "", "repo": repo, "pr": pr, "extra": {"state": rv.get("state") or ""}})
    for rc in gh_api(f"/repos/{repo}/pulls/{pr}/comments?per_page=100"):
        events.append({"kind": "review_comment", "id": rc["id"], "user": rc["user"]["login"], "body": rc.get("body") or "", "repo": repo, "pr": pr, "extra": {}})
    return events


def archive_event(event: dict) -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{event['repo'].replace('/', '__')}-pr{event['pr']}-{event['kind']}-{event['id']}.json"
    p = INBOX_DIR / name
    p.write_text(json.dumps(event, indent=2))
    return p


def format_message(event: dict, archive_path: Path, reason: str) -> str:
    snippet = (event.get("body") or "").strip().replace("\n", " ")[:200]
    head = f"[{reason.upper()}] {event['repo']}#{event['pr']} {event['kind']} by @{event['user']}"
    extra = ""
    if event["kind"] == "review":
        extra = f" ({(event.get('extra') or {}).get('state', '?')})"
    return f"{head}{extra}: {snippet}  (full: {archive_path})"


def poll_once(state: dict, dry_run: bool = False) -> None:
    open_prs = discover_open_prs(WATCHED_REPOS)
    print(f"poll: {len(open_prs)} open PR(s) across {len(WATCHED_REPOS)} repo(s)")
    seen = set(state["seen_ids"])
    initialized = set(state["initialized_prs"])

    for repo, pr, pr_author in open_prs:
        pr_key = f"{repo}#{pr}"
        first_time = pr_key not in initialized
        events = fetch_pr_events(repo, pr)
        for ev in events:
            eid = f"{ev['kind']}:{ev['id']}"
            if eid in seen:
                continue
            seen.add(eid)
            if first_time:
                continue  # bootstrap: don't notify on first encounter

            reason = notify_reason(ev, pr_author)
            approve = is_approve_command(ev)
            if not reason and not approve:
                continue

            archive_path = archive_event(ev)
            if approve and not dry_run:
                ok, info = approve_pr(repo, pr)
                marker = "AUTO-APPROVED" if ok else "AUTO-APPROVE-FAILED"
                msg = f"[{marker}] {repo}#{pr} via {APPROVE_COMMAND} by @{ev['user']}: {info[:200]}"
                push_to_boss(msg)
            if reason:
                msg = format_message(ev, archive_path, reason)
                if dry_run:
                    print(f"  DRY: {msg}")
                else:
                    push_to_boss(msg)
        initialized.add(pr_key)

    state["seen_ids"] = list(seen)
    state["initialized_prs"] = list(initialized)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="seconds between polls (0 = one-shot)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--init", action="store_true", help="mark current state as seen, push nothing")
    args = ap.parse_args()

    if not SELF_USER or not WATCHED_REPOS:
        print("FATAL: SELF_USER and WATCHED_REPOS required in ~/.config/mypeople/gh-pr-watcher.env", file=sys.stderr)
        sys.exit(1)
    if not BOSS_TARGET:
        print("FATAL: BOSS_TARGET required in ~/.config/mypeople/gh-pr-watcher.env", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    if args.init:
        # First-time: walk all events, mark them seen, never push.
        for repo, pr, _author in discover_open_prs(WATCHED_REPOS):
            for ev in fetch_pr_events(repo, pr):
                state["seen_ids"].append(f"{ev['kind']}:{ev['id']}")
            state["initialized_prs"].append(f"{repo}#{pr}")
        save_state(state)
        print(f"initialized: {len(state['seen_ids'])} events seen, {len(state['initialized_prs'])} PRs tracked")
        return

    interval = args.loop if args.loop > 0 else POLL_INTERVAL
    if args.loop == 0:
        poll_once(state, dry_run=args.dry_run)
        save_state(state)
        return

    print(f"loop: polling every {interval}s. Ctrl-C to stop.")
    try:
        while True:
            try:
                poll_once(state, dry_run=args.dry_run)
                save_state(state)
            except Exception as e:
                print(f"  poll FAILED: {e}", file=sys.stderr)
            time.sleep(interval)
    except KeyboardInterrupt:
        save_state(state)


if __name__ == "__main__":
    main()
PY_EOF
chmod +x "$INSTALL_DIR/bin/gh-pr-watcher.py"
```

### 5. Initialize state (bootstrap — silently mark existing PR events as "seen")

**Why**: without this, the first poll fires `mp send` for every comment that already existed on every open PR — blast.

```bash
python3 "$INSTALL_DIR/bin/gh-pr-watcher.py" --init
```

### 6. Start the watcher daemon

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"
nohup python3 -u "$INSTALL_DIR/bin/gh-pr-watcher.py" --loop "$POLL_INTERVAL" \
  > "$INSTALL_DIR/run/gh-pr-watcher.log" 2>&1 &
echo $! > "$INSTALL_DIR/run/gh-pr-watcher.pid"
sleep 2
ps -p "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" -o pid,command 2>&1
```

## Verify

```bash
#!/bin/bash
set -e
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"

# 1. Daemon alive
ps -p "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" -o command= 2>/dev/null | grep -q gh-pr-watcher.py || { echo "FAIL: gh-pr-watcher daemon not running"; exit 1; }

# 2. Config + state files
[ -s "$HOME/.config/mypeople/gh-pr-watcher.env" ] || { echo "FAIL: gh-pr-watcher.env missing"; exit 1; }
[ -f "$INSTALL_DIR/run/gh-pr-watcher-state.json" ] || { echo "FAIL: state file missing (--init didn't run?)"; exit 1; }

# 3. gh CLI reachable + authed
gh auth status >/dev/null 2>&1 || { echo "FAIL: gh auth lost"; exit 1; }

# 4. Boss still reachable on the queue (this seed depends on mypeople)
mp status >/dev/null 2>&1 || { echo "FAIL: mypeople queue unreachable"; exit 1; }

# 5. Sample log line to prove the daemon completed at least one poll
sleep "$(( $(grep ^POLL_INTERVAL= $HOME/.config/mypeople/gh-pr-watcher.env | cut -d= -f2-) + 5 ))"
grep -q '^poll:' "$INSTALL_DIR/run/gh-pr-watcher.log" || { echo "FAIL: no 'poll:' line in log — watcher never completed a poll"; tail -20 "$INSTALL_DIR/run/gh-pr-watcher.log"; exit 1; }

echo "VERIFY_OK"
```

## Failure modes

**`gh: command not found`** → `gh` CLI not installed. macOS: `brew install gh`. Debian: `sudo apt-get install gh`.

**`gh auth status` reports not logged in** → run `gh auth login` and complete the OAuth flow. The watcher uses the host user's authenticated session — no separate token.

**Approve-command fired but `gh pr review --approve` returned non-zero** → likely "Can not approve your own pull request" (GitHub forbids self-approval) or the PR is in a state that doesn't allow reviews. Inspect `$INSTALL_DIR/run/gh-pr-watcher.log` for the stderr.

**First start floods Boss with hundreds of notifications** → you skipped Step 5 (`--init`). Stop the daemon, run `--init`, restart.

**Auto-approves a PR you didn't want approved** → the marker matched somewhere unexpected. The regex is word-boundary anchored (`/<SELF_USER>-approve` followed by non-word, non-`-`) but a comment containing the literal marker IS the contract. To revoke: `gh pr review <pr> --request-changes --repo <repo>`. To prevent on a specific repo: remove it from `APPROVE_REPOS` in `gh-pr-watcher.env` and restart the daemon.

**Notifications never reach Boss** → check the queue: `mp status` should show Boss alive; tail `$INSTALL_DIR/run/queue-server.log` for incoming `/task/submit` from the watcher; check the watcher log for `→ queued task ...` lines.

## Cleanup

```bash
INSTALL_DIR="${INSTALL_DIR:-$HOME/mypeople}"
[ -f "$INSTALL_DIR/run/gh-pr-watcher.pid" ] && kill "$(cat $INSTALL_DIR/run/gh-pr-watcher.pid)" 2>/dev/null || true
pkill -f "$INSTALL_DIR/bin/gh-pr-watcher.py" 2>/dev/null || true
rm -f "$INSTALL_DIR/bin/gh-pr-watcher.py" "$INSTALL_DIR/run/gh-pr-watcher.pid" "$INSTALL_DIR/run/gh-pr-watcher.log" "$INSTALL_DIR/run/gh-pr-watcher-state.json"
rm -f "$HOME/.config/mypeople/gh-pr-watcher.env"
# To also drop the event archive: rm -rf ~/.gh-pr-watcher
```
