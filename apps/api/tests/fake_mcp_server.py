#!/usr/bin/env python3
"""Minimal stdio MCP server for tests: speaks newline-delimited JSON-RPC."""
import json
import sys


def respond(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        respond({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
        }})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        respond({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": "echo", "description": "Echoes the input back.",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}},
                             "required": ["text"]}},
        ]}})
    elif method == "tools/call":
        params = req.get("params") or {}
        args = params.get("arguments") or {}
        respond({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}],
            "isError": False,
        }})
    elif rid is not None:
        respond({"jsonrpc": "2.0", "id": rid, "result": {}})
