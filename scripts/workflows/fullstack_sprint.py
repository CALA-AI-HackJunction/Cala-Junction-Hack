"""
Dynamic Multi-Agent Full-Stack Sprint Workflow for Antigravity (`run_workflow`).
Orchestrates Architect + Cala Intelligence in parallel, then Backend + Frontend in parallel,
followed by QA & Integration review with context-preserving follow-up fixes.
"""

feature = (args or {}).get("feature", "Build initial MVP vertical slice")

phase("1. Architecture & Cala Graph Discovery")
contract_and_data = await parallel(
    [
        {
            "type": "architect-coordinator",
            "role": "System Architect",
            "prompt": (
                f"Feature goal: {feature}\n"
                "Update docs/contracts/API_CONTRACT.md with exact REST/SSE endpoints, "
                "TypeScript/JSON types, and Cala provenance envelopes. Return a concise summary."
            ),
        },
        {
            "type": "cala-intelligence-agent",
            "role": "Cala Graph Specialist",
            "prompt": (
                f"Feature goal: {feature}\n"
                "Read the cala skill, verify optimal knowledge_query / entity_introspection -> entity_retrieval "
                "patterns, and save realistic sourced JSON fixtures under docs/contracts/cala-fixtures/. "
                "Return the fixture paths and key edge names."
            ),
        },
    ],
    lambda item: agent(
        item["prompt"],
        schema={"type": "string"},
        role=item["role"],
        type_name=item["type"],
    ),
)
contract_summary, cala_summary = contract_and_data
log("Contract locked:", contract_summary)
log("Cala fixtures ready:", cala_summary)

phase("2. Parallel Backend & Frontend Implementation")
backend_worker = agent(
    f"Implement backend scope for: {feature}\n"
    f"Contract summary:\n{contract_summary}\n"
    f"Cala query & fixture notes:\n{cala_summary}\n"
    "Work strictly inside backend/ (or server API directories).",
    role="Backend Engineer",
    type_name="backend-agent",
)
frontend_worker = agent(
    f"Implement frontend UI scope for: {feature}\n"
    f"Contract summary:\n{contract_summary}\n"
    f"Cala fixture notes:\n{cala_summary}\n"
    "Work strictly inside frontend/ (or client UI directories).",
    role="Frontend Engineer",
    type_name="frontend-agent",
)

impl_results = await parallel(
    [
        backend_worker("Build the endpoints, Cala integration, and streaming logic now.", {"type": "string"}),
        frontend_worker("Build the UI views, graph cards, and provenance badges now.", {"type": "string"}),
    ],
    lambda p: p,
)
log("Backend result:", impl_results[0])
log("Frontend result:", impl_results[1])

phase("3. Full-Stack QA & Cross-Agent Fix Loop")
qa_report = await agent(
    f"Audit full-stack integration and Cala provenance for: {feature}\n"
    f"Backend summary: {impl_results[0]}\n"
    f"Frontend summary: {impl_results[1]}\n"
    "Return structured issues split by backend_issues and frontend_issues.",
    schema={
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "backend_issues": {"type": "array", "items": {"type": "string"}},
            "frontend_issues": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": ["passed", "backend_issues", "frontend_issues", "summary"],
    },
    role="QA & Provenance Auditor",
    type_name="qa-integrations-agent",
)
log("QA Audit:", qa_report["summary"])

if not qa_report["passed"]:
    phase("4. Parallel Targeted Fixes")
    fix_tasks = []
    if qa_report["backend_issues"]:
        fix_tasks.append(
            backend_worker(
                "Fix these QA issues in backend:\n- " + "\n- ".join(qa_report["backend_issues"]),
                {"type": "string"},
            )
        )
    if qa_report["frontend_issues"]:
        fix_tasks.append(
            frontend_worker(
                "Fix these QA issues in frontend:\n- " + "\n- ".join(qa_report["frontend_issues"]),
                {"type": "string"},
            )
        )
    if fix_tasks:
        fixes = await parallel(fix_tasks, lambda t: t)
        for f in fixes:
            log("Fix applied:", f)

del backend_worker
del frontend_worker
print("Full-stack multi-agent sprint completed successfully.")
