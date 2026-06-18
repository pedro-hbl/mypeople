#!/usr/bin/env python3
"""mypeople lifecycle hook for Kimi Code CLI.

Install in ~/.kimi/config.toml as:

[[hooks]]
event = "SessionStart"
command = "/path/to/mypeople/hooks/mypeople-hook.py"

[[hooks]]
event = "Stop"
command = "/path/to/mypeople/hooks/mypeople-hook.py"

[[hooks]]
event = "StopFailure"
command = "/path/to/mypeople/hooks/mypeople-hook.py"

[[hooks]]
event = "SessionEnd"
command = "/path/to/mypeople/hooks/mypeople-hook.py"

[[hooks]]
event = "PreToolUse"
matcher = "AskUserQuestion"
command = "/path/to/mypeople/hooks/mypeople-hook.py"

The hook reads a JSON payload from stdin and POSTs it to the mypeople queue
server at $QUEUE_URL (default http://127.0.0.1:9900).
"""

import json
import os
import sys
import urllib.request


QUEUE_URL = os.environ.get("QUEUE_URL", "http://127.0.0.1:9900")
QUEUE_SECRET = os.environ.get("QUEUE_SECRET", "")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    # Don't let a hook failure block the agent's normal flow.
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{QUEUE_URL}/hook",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Queue-Secret": QUEUE_SECRET,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        # Write to a local log so failures are not silently swallowed.
        log_dir = os.path.expanduser("~/.config/mypeople")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "hook-errors.log"), "a") as f:
            f.write(f"{json.dumps({'error': str(e), 'payload': payload})}\n")


if __name__ == "__main__":
    main()
