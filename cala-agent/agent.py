"""Core agent loop — Gemini + Cala MCP tool execution."""

from google import genai
from google.genai import types

from config import get_settings
from mcp_client import CalaMCPClient

# Maximum tool-call rounds before forcing a text response
MAX_TOOL_ROUNDS = 12

SYSTEM_INSTRUCTION = (
    "You are a structured knowledge graph traversal assistant powered by Cala's verified entity graph. "
    "Do NOT use broad prose search. Always use deterministic entity endpoints to navigate the graph: "
    "1. Resolve entity names to UUIDs with `entity_search`. "
    "2. Inspect available incoming and outgoing relationship types with `entity_introspection`. "
    "3. Retrieve exact properties and graph edges using `entity_retrieval` with explicit projections. "
    "Efficiency guideline: Only query 1-2 hops. Once you have retrieved the target entity's direct properties, "
    "founders (`FOUNDED` / `IS_CEO_OF`), and investors (`INVESTED_IN`), stop calling tools and immediately "
    "synthesize the final answer with source citations. Do NOT recursively inspect every secondary entity."
)

EXCLUDED_TOOLS = {"knowledge_search"}


GEMINI_ALLOWED_FIELDS = {
    "type", "format", "description", "nullable", "enum", "properties", "required", "items"
}


def _clean_schema(s):
    """Sanitize JSON Schema dictionary so it adheres strictly to Gemini API Schema specs."""
    if not isinstance(s, dict):
        return s
    res = {}
    for k, v in s.items():
        if k in GEMINI_ALLOWED_FIELDS:
            if k == "properties" and isinstance(v, dict):
                res[k] = {pk: _clean_schema(pv) for pk, pv in v.items()}
            elif k == "items":
                res[k] = _clean_schema(v)
            else:
                res[k] = v
    if "type" in res and isinstance(res["type"], str):
        res["type"] = res["type"].upper()
    return res


def _mcp_to_gemini_tools(mcp_tools: list) -> list[types.Tool]:
    """Convert MCP tool definitions to Gemini function declarations, skipping excluded tools."""
    declarations = []
    for tool in mcp_tools:
        if tool.name in EXCLUDED_TOOLS:
            continue
        parameters = _clean_schema(tool.input_schema) if tool.input_schema else None
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=parameters,
            )
        )
    return [types.Tool(function_declarations=declarations)]


def _get_gemini_client() -> genai.Client:
    cfg = get_settings()
    # If a project is set, use Vertex AI; otherwise use the Gemini Developer API
    if cfg.google_cloud_project:
        return genai.Client(
            vertexai=True,
            project=cfg.google_cloud_project,
            location="us-central1",
        )
    return genai.Client()  # uses GOOGLE_API_KEY env var


async def run_agent_turn(
    user_message: str,
    cala: CalaMCPClient,
    history: list[types.Content] | None = None,
) -> tuple[str, list[types.Content]]:
    """
    Run one full agent turn: prompt → (tool calls)* → final text.

    Returns (answer_text, updated_history).
    """
    client = _get_gemini_client()
    cfg = get_settings()
    gemini_tools = _mcp_to_gemini_tools(cala.tools)

    # Build conversation history
    if history is None:
        history = []

    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=cfg.gemini_model,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=gemini_tools,
            ),
        )

        candidate = response.candidates[0]
        assistant_content = candidate.content
        history.append(assistant_content)

        # Collect any function calls in this response
        function_calls = [p for p in assistant_content.parts if p.function_call]
        if not function_calls:
            # Pure text response — we're done
            text = "".join(p.text for p in assistant_content.parts if p.text)
            return text, history

        # Execute each tool call against Cala
        tool_response_parts = []
        for part in function_calls:
            fc = part.function_call
            try:
                result = await cala.call_tool(fc.name, dict(fc.args))
                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )
                )
            except Exception as exc:
                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"error": str(exc)},
                        )
                    )
                )

        history.append(types.Content(role="user", parts=tool_response_parts))

    # Safety net: if tools were exhausted, force a text synthesis from all facts collected
    final_prompt = types.Content(
        role="user",
        parts=[types.Part(text="Now synthesize and provide the complete final answer to the user's question using the facts retrieved above.")],
    )
    final_resp = client.models.generate_content(
        model=cfg.gemini_model,
        contents=history + [final_prompt],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )
    final_text = "".join(p.text for p in final_resp.candidates[0].content.parts if p.text)
    return final_text or "[No response text generated]", history
