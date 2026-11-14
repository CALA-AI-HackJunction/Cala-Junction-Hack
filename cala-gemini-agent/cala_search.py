import asyncio
import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def search_cala(question: str, key: str) -> str:
    async with asyncio.timeout(45), httpx.AsyncClient(
        headers={"X-API-KEY": key}, timeout=40, follow_redirects=False
    ) as http:
        async with streamable_http_client("https://api.cala.ai/mcp/", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("knowledge_search", {"input": question})
    if result.isError:
        raise RuntimeError("Cala search failed.")
    evidence = "\n".join(block.text for block in result.content if block.type == "text")
    if not evidence and result.structuredContent:
        evidence = json.dumps(result.structuredContent, ensure_ascii=False)
    return evidence.replace(key, "[redacted]")[:40_000]
