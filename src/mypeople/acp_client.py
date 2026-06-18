#!/usr/bin/env python3
"""Minimal JSON-RPC client for `kimi acp` (ACP multi-session server).

Spawns `kimi acp` as a subprocess and speaks newline-delimited JSON-RPC over
stdin/stdout. Exposes the small subset of ACP methods mypeople needs:

- initialize
- session/new
- session/list
- session/prompt
- session/cancel (notification)

All streaming `session/update` notifications are collected into a callback.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ACPAgentConfig:
    """Configuration for a single ACP-managed agent session."""

    agent_id: str
    session_id: Optional[str] = None
    cwd: str = "."
    state: str = "starting"  # starting, idle, working, blocked, dead
    summary: str = ""
    last_activity: Optional[float] = None
    boss_id: Optional[str] = None
    is_master: bool = False
    pending_task_id: Optional[str] = None
    history: list[dict[str, Any]] = field(default_factory=list)


class ACPClient:
    """Async JSON-RPC client for Kimi Code CLI ACP server."""

    def __init__(
        self,
        command: list[str] | None = None,
        on_update: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.command = command or ["kimi", "acp"]
        self.on_update = on_update
        self._proc: asyncio.subprocess.Process | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._next_id = 1
        self._inflight: dict[int | str, asyncio.Future] = {}
        self._ready = asyncio.Event()
        self._agent_capabilities: dict[str, Any] = {}

    async def start(self) -> None:
        """Start the ACP subprocess and initialize the connection."""
        if self._proc is not None:
            return

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._writer = self._proc.stdin
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())

        result = await self._request(
            "initialize",
            {
                "protocolVersion": 1,
                "capabilities": {},
                "clientInfo": {"name": "mypeople", "version": "0.2.0"},
            },
        )
        self._agent_capabilities = result.get("agentCapabilities", {})
        self._ready.set()
        print(f"[acp] initialized; pid={self._proc.pid}", file=sys.stderr)

    async def stop(self) -> None:
        """Terminate the ACP subprocess and clean up."""
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        for fut in list(self._inflight.values()):
            if not fut.done():
                fut.cancel()

        if self._proc:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()

        self._proc = None
        self._writer = None
        self._reader_task = None
        self._stderr_task = None
        self._ready.clear()

    async def _read_loop(self) -> None:
        """Read newline-delimited JSON-RPC messages from ACP stdout."""
        assert self._proc is not None
        buf = b""
        while True:
            try:
                chunk = await self._proc.stdout.read(8192)
            except asyncio.CancelledError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"[acp] bad json: {line!r} ({e})", file=sys.stderr)
                    continue
                await self._dispatch(msg)

    async def _stderr_loop(self) -> None:
        """Forward ACP stderr to our stderr so errors are visible."""
        assert self._proc is not None
        while True:
            try:
                line = await self._proc.stderr.readline()
            except asyncio.CancelledError:
                break
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                print(f"[kimi-acp] {text}", file=sys.stderr)

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and msg["id"] is not None:
            fut = self._inflight.pop(msg["id"], None)
            if fut is not None and not fut.done():
                if "error" in msg:
                    fut.set_exception(ACPError(msg["error"]))
                else:
                    fut.set_result(msg.get("result", {}))
            return

        # One-way notification (session/update, etc.)
        if self.on_update:
            try:
                result = self.on_update(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[acp] update handler error: {e}", file=sys.stderr)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._writer is None:
            raise RuntimeError("ACP client not started")

        req_id = self._next_id
        self._next_id += 1
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._inflight[req_id] = fut

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self._writer.write(data)
        await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout=60)
        except asyncio.TimeoutError:
            self._inflight.pop(req_id, None)
            raise ACPError({"code": -32000, "message": f"ACP timeout: {method}"})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        await self._ready.wait()
        if self._writer is None:
            raise RuntimeError("ACP client not started")
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self._writer.write(data)
        await self._writer.drain()

    # ------------------------------------------------------------------
    # High-level ACP helpers
    # ------------------------------------------------------------------

    async def new_session(self, cwd: str, mcp_servers: list[dict[str, Any]] | None = None) -> str:
        """Create a new ACP session. Returns the sessionId."""
        await self._ready.wait()
        params: dict[str, Any] = {"cwd": os.path.abspath(cwd)}
        params["mcpServers"] = mcp_servers or []
        result = await self._request("session/new", params)
        return result["sessionId"]

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List active ACP sessions."""
        await self._ready.wait()
        result = await self._request("session/list", {})
        return result.get("sessions", [])

    async def prompt(
        self,
        session_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Send a text prompt to a session. Returns the prompt result."""
        await self._ready.wait()
        return await self._request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
        )

    async def cancel(self, session_id: str) -> None:
        """Cancel any running turn in a session."""
        await self._ready.wait()
        await self.notify(
            "session/cancel",
            {"sessionId": session_id},
        )

    def is_alive(self) -> bool:
        """Best-effort check whether the ACP subprocess is still running."""
        return self._proc is not None and self._proc.returncode is None


class ACPError(Exception):
    def __init__(self, error: dict[str, Any]) -> None:
        self.code = error.get("code")
        self.message = error.get("message", "unknown ACP error")
        self.data = error.get("data")
        super().__init__(f"ACP error {self.code}: {self.message}")
