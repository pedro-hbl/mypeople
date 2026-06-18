#!/usr/bin/env python3
"""mypeople queue server for Kimi Code CLI.

A tiny HTTP control plane that:
- Spawns and manages independent Kimi sessions via the ACP multi-session server.
- Tracks agent state (idle / working / blocked / dead).
- Accepts lifecycle hooks from Kimi sessions.
- Serves a browser dashboard.
- Provides the REST surface the `mp` CLI talks to.

Design notes
------------
- This is a single-process stdlib server. The ACP subprocess (`kimi acp`) runs in a
  background thread with its own asyncio event loop.
- All agent state is kept in memory. If the queue server restarts, the ACP subprocess
  also restarts and existing sessions are lost. This matches mypeople v1 semantics.
- Windows: run this inside WSL. The dashboard is reachable from the Windows host at
  http://<wsl-ip>:9900/dashboard and can be opened in Brave.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Add package root to path when running as a script.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from acp_client import ACPClient, ACPAgentConfig, ACPError  # noqa: E402


DEFAULT_PORT = 9900
DEFAULT_KIMI_WEB_URL = "http://127.0.0.1:5494"
AGENT_DEAD_AFTER = 300.0  # seconds before a silent agent is marked dead


class AgentRunner:
    """Thread-safe facade around the async ACP client."""

    def __init__(self, secret: str, acp_command: list[str] | None = None) -> None:
        self.secret = secret
        self.acp_command = acp_command
        self.agents: dict[str, ACPAgentConfig] = {}
        self.lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: ACPClient | None = None
        self._started = threading.Event()

    # ------------------------------------------------------------------
    # Background asyncio thread
    # ------------------------------------------------------------------

    def start(self) -> None:
        def run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._client = ACPClient(
                command=self.acp_command or ["kimi", "acp"],
                on_update=self._on_acp_update,
            )
            self._loop.run_until_complete(self._client.start())
            self._started.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=30):
            raise RuntimeError("ACP client failed to start within 30s")

    def stop(self) -> None:
        if self._loop is None or self._client is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._client.stop(), self._loop)
        fut.result(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self, coro: asyncio.Coroutine) -> Any:
        """Run an async coroutine on the ACP thread and return its result."""
        if self._loop is None:
            raise RuntimeError("ACP runner not started")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=120)

    # ------------------------------------------------------------------
    # ACP update handling
    # ------------------------------------------------------------------

    def _on_acp_update(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        params = msg.get("params", {})
        if method != "session/update":
            return

        session_id = params.get("sessionId")
        update = params.get("update", {})
        update_type = update.get("sessionUpdate") or update.get("session_update")

        with self.lock:
            agent = self._agent_by_session(session_id)
            if agent is None:
                return

            agent.last_activity = time.time()
            if update_type in (
                "agent_message_chunk",
                "agent_thought_chunk",
                "tool_call",
                "tool_call_update",
            ):
                agent.state = "working"
                content = update.get("content", {})
                if isinstance(content, dict) and content.get("type") == "text":
                    text = content.get("text", "")
                    agent.history.append({"ts": time.time(), "role": "assistant", "text": text})
                    agent.summary = (text[:200] + "...") if len(text) > 200 else text

    def _agent_by_session(self, session_id: str) -> ACPAgentConfig | None:
        for agent in self.agents.values():
            if agent.session_id == session_id:
                return agent
        return None

    # ------------------------------------------------------------------
    # Public actions used by HTTP handlers
    # ------------------------------------------------------------------

    def spawn(
        self,
        agent_id: str,
        cwd: str,
        boss_id: str | None = None,
        is_master: bool = False,
    ) -> dict[str, Any]:
        with self.lock:
            if agent_id in self.agents and self.agents[agent_id].state != "dead":
                return {"agent_id": agent_id, "reused_existing": True}

        session_id = self._run(self._client.new_session(cwd))

        with self.lock:
            self.agents[agent_id] = ACPAgentConfig(
                agent_id=agent_id,
                session_id=session_id,
                cwd=os.path.abspath(cwd),
                state="idle",
                boss_id=boss_id,
                is_master=is_master,
                last_activity=time.time(),
            )

        return {"agent_id": agent_id, "session_id": session_id}

    def send(self, agent_id: str, message: str) -> dict[str, Any]:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None or agent.session_id is None:
                raise ValueError(f"agent not found: {agent_id}")
            agent.state = "working"
            agent.last_activity = time.time()
            agent.history.append({"ts": time.time(), "role": "user", "text": message})

        try:
            result = self._run(self._client.prompt(agent.session_id, message))
        except ACPError as e:
            with self.lock:
                agent.last_activity = time.time()
                agent.state = "dead"
                agent.summary = f"prompt failed: {e.message}"
            raise

        with self.lock:
            agent.last_activity = time.time()
            if agent.state == "working":
                agent.state = "idle"

        return {"agent_id": agent_id, "stop_reason": result.get("stopReason")}

    def peek(self, agent_id: str) -> dict[str, Any]:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                raise ValueError(f"agent not found: {agent_id}")
            self._reap_if_stale(agent)
            return {
                "agent_id": agent.agent_id,
                "session_id": agent.session_id,
                "state": agent.state,
                "summary": agent.summary,
                "last_activity": agent.last_activity,
                "history": agent.history[-20:],
            }

    def kill(self, agent_id: str) -> dict[str, Any]:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                raise ValueError(f"agent not found: {agent_id}")
            if agent.session_id:
                try:
                    self._run(self._client.cancel(agent.session_id))
                except ACPError as e:
                    print(f"[kill] cancel failed for {agent_id}: {e}", file=sys.stderr)
            agent.state = "dead"
            agent.last_activity = time.time()
        return {"agent_id": agent_id, "killed": True}

    def status(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = []
            for agent in self.agents.values():
                self._reap_if_stale(agent)
                rows.append({
                    "agent_id": agent.agent_id,
                    "session_id": agent.session_id,
                    "state": agent.state,
                    "summary": agent.summary,
                    "last_activity": agent.last_activity,
                    "boss_id": agent.boss_id,
                    "is_master": agent.is_master,
                })
            return rows

    def _reap_if_stale(self, agent: ACPAgentConfig) -> None:
        if agent.last_activity and time.time() - agent.last_activity > AGENT_DEAD_AFTER:
            agent.state = "dead"

    def handle_hook(self, payload: dict[str, Any]) -> None:
        """Process a lifecycle hook POSTed by a Kimi session."""
        event = payload.get("hook_event_name")
        session_id = payload.get("session_id")
        if not session_id:
            return

        with self.lock:
            agent = self._agent_by_session(session_id)
            if agent is None:
                return

            agent.last_activity = time.time()
            if event == "SessionStart":
                agent.state = "idle"
            elif event == "Stop":
                agent.state = "idle"
                if not agent.summary:
                    agent.summary = "turn completed"
                self._notify_boss_locked(agent)
            elif event == "StopFailure":
                agent.state = "dead"
                agent.summary = payload.get("error_message", "turn failed")
                self._notify_boss_locked(agent)
            elif event == "SessionEnd":
                agent.state = "dead"
            elif event == "PreToolUse":
                tool = payload.get("tool_name", "")
                if tool == "AskUserQuestion":
                    agent.state = "blocked"
                    agent.summary = "waiting on user question"

    def _notify_boss_locked(self, agent: ACPAgentConfig) -> None:
        """Send a short notification prompt to the Boss session.

        Must be called while holding self.lock.
        """
        if not agent.boss_id:
            return
        boss = self.agents.get(agent.boss_id)
        if boss is None or boss.session_id is None:
            return
        summary = agent.summary or "(no summary)"
        message = (
            f"[AGENT NOTIFICATION] {agent.agent_id} finished: {summary}\n\n"
            "Acknowledge this notification in one line."
        )
        # Offload to the ACP thread so we don't block the hook response.
        boss_session = boss.session_id
        asyncio.run_coroutine_threadsafe(
            self._client.prompt(boss_session, message),
            self._loop,
        )


# ------------------------------------------------------------------------------
# HTTP handlers
# ------------------------------------------------------------------------------


def _json_response(handler: BaseHTTPRequestHandler, status: int, data: Any) -> None:
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    _json_response(handler, status, {"ok": False, "error": message})


class RequestHandler(BaseHTTPRequestHandler):
    runner: AgentRunner
    secret: str

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[queue] {self.address_string()} {fmt % args}", file=sys.stderr)

    def _check_secret(self) -> bool:
        supplied = (self.headers.get("X-Queue-Secret") or "").strip()
        if not supplied:
            auth = (self.headers.get("Authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                supplied = auth[7:].strip()
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if not supplied and "secret" in qs:
            supplied = qs["secret"][0]
        if supplied != self.secret:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health":
            _json_response(self, 200, {"status": "ok", "backend": "kimi-acp"})
            return

        if path in ("/agents", "/status"):
            if not self._check_secret():
                return
            _json_response(self, 200, self.runner.status())
            return

        if path == "/dashboard" or path == "/":
            self._serve_dashboard()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/hook":
            payload = self._read_json()
            self.runner.handle_hook(payload)
            _json_response(self, 200, {"ok": True})
            return

        if path in (
            "/task/submit",
            "/spawn",
            "/send",
            "/peek",
            "/kill",
        ):
            if not self._check_secret():
                return
            payload = self._read_json()
            try:
                result = self._handle_action(path, payload)
                _json_response(self, 200, {"ok": True, "result": result})
            except Exception as e:
                _error(self, 500, str(e))
            return

        self.send_response(404)
        self.end_headers()

    def _handle_action(self, path: str, payload: dict[str, Any]) -> Any:
        action = payload.get("action", "")
        if path == "/spawn" or action == "spawn":
            p = payload.get("payload", payload)
            return self.runner.spawn(
                agent_id=p["agent_id"],
                cwd=p.get("cwd", "."),
                boss_id=p.get("boss_id"),
                is_master=p.get("is_master", False),
            )

        if path == "/send" or action == "send":
            target = payload.get("target_agent") or payload.get("payload", {}).get("agent_id")
            msg = payload.get("payload", {}).get("message", "")
            if not target:
                target = payload.get("agent_id")
                msg = payload.get("message", "")
            return self.runner.send(target, msg)

        if path == "/peek" or action == "peek":
            target = (
                payload.get("target_agent")
                or payload.get("payload", {}).get("agent_id")
                or payload.get("agent_id")
            )
            return self.runner.peek(target)

        if path == "/kill" or action == "kill":
            target = (
                payload.get("target_agent")
                or payload.get("payload", {}).get("agent_id")
                or payload.get("agent_id")
            )
            return self.runner.kill(target)

        raise ValueError(f"unknown action or path: {path}")

    def _serve_dashboard(self) -> None:
        agents = self.runner.status()
        rows = []
        for a in agents:
            state_class = {
                "idle": "idle",
                "working": "working",
                "blocked": "blocked",
                "dead": "dead",
                "starting": "starting",
            }.get(a["state"], "unknown")
            last = ""
            if a["last_activity"]:
                last = f"{int(time.time() - a['last_activity'])}s ago"
            web_url = os.environ.get("KIMI_WEB_URL", DEFAULT_KIMI_WEB_URL)
            if "?" not in web_url and self.secret:
                web_url = f"{web_url}?token={urllib.parse.quote(self.secret)}"
            rows.append(
                f"<tr>"
                f"<td><code>{html.escape(a['agent_id'])}</code></td>"
                f"<td><span class='pill {state_class}'>{html.escape(a['state'])}</span></td>"
                f"<td>{html.escape(a.get('summary', '') or '')}</td>"
                f"<td>{last}</td>"
                f"<td><a href='{web_url}' target='_blank'>Open in Kimi Web</a></td>"
                f"</tr>"
            )

        body = DASHBOARD_TEMPLATE.format(
            rows="\n".join(rows) if rows else "<tr><td colspan='5'>No agents yet.</td></tr>",
            count=len(agents),
        )
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


DASHBOARD_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>mypeople — Kimi agents</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ margin-bottom: 0.25rem; }}
    p.sub {{ color: #94a3b8; margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; }}
    th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ color: #cbd5e1; font-weight: 600; }}
    a {{ color: #38bdf8; }}
    .pill {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600; }}
    .idle {{ background: #14532d; color: #86efac; }}
    .working {{ background: #1e3a8a; color: #93c5fd; }}
    .blocked {{ background: #713f12; color: #fde047; }}
    .dead {{ background: #450a0a; color: #fca5a5; }}
    .starting {{ background: #3f3f46; color: #d4d4d8; }}
    .refresh {{ margin-top: 1rem; color: #94a3b8; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>mypeople dashboard</h1>
  <p class="sub">{count} agent(s) tracked. Auto-refreshes every 3s.</p>
  <table>
    <thead>
      <tr><th>Agent</th><th>State</th><th>Summary</th><th>Last activity</th><th>Open</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <p class="refresh">Use <code>mp spawn &lt;agent-id&gt; --cwd &lt;dir&gt;</code> from WSL to add agents.</p>
  <script>
    setTimeout(() => location.reload(), 3000);
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="mypeople queue server for Kimi")
    parser.add_argument("--port", type=int, default=int(os.environ.get("QUEUE_PORT", DEFAULT_PORT)))
    parser.add_argument("--secret", default=os.environ.get("QUEUE_SECRET"))
    parser.add_argument("--acp-command", help="Override the `kimi acp` command (json list)")
    args = parser.parse_args()

    secret = args.secret or secrets.token_urlsafe(32)
    if not args.secret:
        print(f"[queue] generated secret: {secret}", file=sys.stderr)

    acp_command = None
    if args.acp_command:
        acp_command = json.loads(args.acp_command)

    runner = AgentRunner(secret=secret, acp_command=acp_command)
    runner.start()

    RequestHandler.runner = runner
    RequestHandler.secret = secret

    server = ThreadingHTTPServer(("0.0.0.0", args.port), RequestHandler)
    print(f"[queue] listening on http://0.0.0.0:{args.port}", file=sys.stderr)
    print(f"[queue] dashboard: http://127.0.0.1:{args.port}/dashboard", file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[queue] shutting down", file=sys.stderr)
    finally:
        runner.stop()
        server.server_close()


if __name__ == "__main__":
    main()
