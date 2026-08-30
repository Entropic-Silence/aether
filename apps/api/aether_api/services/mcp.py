from __future__ import annotations

import asyncio
import json
import uuid

import httpx

from ..errors import ToolError_

MCP_PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "aether", "version": "0.6.0"}


class McpClient:
    """Minimal Model Context Protocol client: stdio and HTTP transports.

    Implements JSON-RPC 2.0 handshake (initialize), tools/list and tools/call.
    """

    def __init__(self, transport: str, config: dict):
        self.transport = transport
        self.config = config

    async def list_tools(self) -> list[dict]:
        if self.transport == "stdio":
            return await self._stdio_session(list_only=True)
        return await self._http_request("tools/list", {})

    async def call_tool(self, name: str, arguments: dict) -> str:
        if self.transport == "stdio":
            return await self._stdio_session(call=(name, arguments))
        result = await self._http_request("tools/call", {"name": name, "arguments": arguments})
        return _mcp_result_to_text(result)

    # --- stdio transport -------------------------------------------------

    async def _stdio_session(self, list_only: bool = False, call: tuple[str, dict] | None = None):
        command = self.config.get("command")
        if not command:
            raise ToolError_("MCP stdio server needs a command")
        args = self.config.get("args") or []
        env = self.config.get("env") or {}

        import os

        full_env = {**os.environ, **{str(k): str(v) for k, v in env.items()}}
        proc = await asyncio.create_subprocess_exec(
            command, *[str(a) for a in args],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )
        try:
            async def rpc(method: str, params: dict, notify: bool = False):
                msg = {"jsonrpc": "2.0", "method": method, "params": params}
                if not notify:
                    msg["id"] = str(uuid.uuid4())
                proc.stdin.write((json.dumps(msg) + "\n").encode())
                await proc.stdin.drain()
                if notify:
                    return None
                while True:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
                    if not line:
                        raise ToolError_("MCP server closed the connection")
                    try:
                        resp = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue
                    if resp.get("id") == msg["id"]:
                        if "error" in resp:
                            raise ToolError_(f"MCP error: {resp['error']}")
                        return resp.get("result")

            await rpc("initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            })
            await rpc("notifications/initialized", {}, notify=True)
            if call:
                name, arguments = call
                result = await rpc("tools/call", {"name": name, "arguments": arguments})
                return _mcp_result_to_text(result)
            result = await rpc("tools/list", {})
            return result.get("tools", []) if isinstance(result, dict) else []
        finally:
            try:
                proc.stdin.close()
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    # --- HTTP transport --------------------------------------------------

    async def _http_request(self, method: str, params: dict):
        url = self.config.get("url")
        if not url:
            raise ToolError_("MCP HTTP server needs a url")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        for k, v in (self.config.get("headers") or {}).items():
            headers[str(k)] = str(v)
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}

        session_headers = dict(headers)
        async with httpx.AsyncClient(timeout=60) as client:
            if method != "initialize":
                init = await client.post(url, headers=headers, json={
                    "jsonrpc": "2.0", "id": "init", "method": "initialize",
                    "params": {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
                })
                sid = _extract_session_id(init)
                if sid:
                    session_headers["Mcp-Session-Id"] = sid
                await _parse_rpc(init)
                try:
                    await client.post(url, headers=session_headers, json={
                        "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
                    })
                except httpx.HTTPError:
                    pass
            resp = await client.post(url, headers=session_headers, json=payload)
            return await _parse_rpc(resp)


def _extract_session_id(resp: httpx.Response) -> str | None:
    return resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")


async def _parse_rpc(resp: httpx.Response):
    if resp.status_code >= 400:
        raise ToolError_(f"MCP server returned HTTP {resp.status_code}")
    ctype = (resp.headers.get("content-type") or "").lower()
    text = resp.text
    if "text/event-stream" in ctype:
        data_lines = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        if not data_lines:
            raise ToolError_("MCP server returned an empty SSE response")
        obj = json.loads(data_lines[-1])
    else:
        obj = json.loads(text)
    if isinstance(obj, dict) and "error" in obj:
        raise ToolError_(f"MCP error: {obj['error']}")
    return obj.get("result") if isinstance(obj, dict) else obj


def _mcp_result_to_text(result) -> str:
    if not isinstance(result, dict):
        return str(result)
    if result.get("isError"):
        content = result.get("content") or []
        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
        raise ToolError_("MCP tool error: " + " ".join(parts)[:500])
    content = result.get("content") or []
    parts = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif isinstance(c, dict):
            parts.append(json.dumps(c, ensure_ascii=False)[:2000])
    return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)[:2000]
