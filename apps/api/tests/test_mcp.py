import json
import os
import sys

import pytest

from aether_api.services.mcp import McpClient

FAKE_SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


@pytest.mark.asyncio
async def test_mcp_stdio_list_and_call():
    client = McpClient("stdio", {"command": sys.executable, "args": [FAKE_SERVER]})
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"

    result = await client.call_tool("echo", {"text": "hello"})
    assert "echo: hello" in result


@pytest.mark.asyncio
async def test_mcp_tool_result_error_raises():
    from aether_api.services.mcp import _mcp_result_to_text
    from aether_api.errors import ToolError_

    with pytest.raises(ToolError_):
        _mcp_result_to_text({"isError": True, "content": [{"type": "text", "text": "boom"}]})

    text = _mcp_result_to_text({"content": [{"type": "text", "text": "ok"}]})
    assert text == "ok"


@pytest.mark.asyncio
async def test_mcp_stdio_missing_command_raises():
    from aether_api.errors import ToolError_

    client = McpClient("stdio", {})
    with pytest.raises(ToolError_):
        await client.list_tools()
