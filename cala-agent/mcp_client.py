"""Cala MCP client — connects to the remote MCP server and exposes tool discovery + execution."""

from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config import get_settings


class CalaMCPClient:
    """Wraps a persistent MCP session to Cala's remote server."""

    def __init__(self, session: ClientSession, tools: list):
        self._session = session
        self.tools = tools  # raw MCP tool definitions

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool on Cala's MCP server and return the result content."""
        result = await self._session.call_tool(name, arguments=arguments)
        # result.content is a list of content blocks; join text blocks for simplicity
        return [block.model_dump() for block in result.content]

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]


@asynccontextmanager
async def connect_cala():
    """Async context manager that yields a ready-to-use CalaMCPClient."""
    cfg = get_settings()
    http_client = httpx2.AsyncClient(
        headers={"X-API-KEY": cfg.cala_api_key},
    )
    async with streamable_http_client(
        url=cfg.cala_mcp_url,
        http_client=http_client,
    ) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            yield CalaMCPClient(session=session, tools=tools_result.tools)
