---
name: cala-agent-dev
description: Use when developing or reviewing the Cala Gemini project's raw Cala MCP entity retrieval and deterministic graph traversal.
---

# Cala Agent Development

## Deterministic graph traversal

> Critically, I wouldn't use an LLM to perform the actual graph traversal. I'd use deterministic BFS, shortest-path algorithms, or graph queries. Agents decide what to search for and interpret why a connection matters.

- Run traversal in code or through deterministic graph queries over the retrieved graph. An LLM must never expand the frontier, choose the next hop, or construct a path.
- Traverse only relationships explicitly returned by Cala. Preserve each relationship's endpoints, type, and direction. Never infer, fabricate, or fill in missing edges.
- Set a finite maximum hop depth before traversal. Use a stable ordering and tie-breaking rule, deduplicate visited entities by Cala ID, and deduplicate repeated edges by their Cala relationship ID when available. Otherwise, use a stable identity based on the returned relationship record. Retain all provenance when merging duplicates. Stop expanding at the depth limit or when the frontier is exhausted. Report a depth cutoff when it limits the result.

## Raw Cala MCP retrieval

These rules govern entity retrieval in this project. The only permitted Cala MCP tools are:

1. `entity_search` to resolve a name to a seed entity, using entity-type filters when applicable.
2. `entity_lookup` to resolve a known external identifier to a seed entity.
3. `entity_introspection` to inspect the properties, relationships, and numerical observations available for that specific Cala entity ID.
4. `entity_retrieval` to fetch the needed properties, relationships, and numerical observations. Repeat introspection and retrieval for linked IDs selected by the deterministic traversal.

Never call `knowledge_search`, `knowledge_query`, or any other endpoint for this workflow, including as a fallback. Return raw structured records with Cala entity, relationship, and observation IDs as supplied, original values, and their associated source records and dates. Do not summarize, paraphrase, or synthesize during retrieval. If interpretation is requested, work from the retrieved evidence after retrieval and traversal finish.
