# Cala Research

Use the pinned `google-genai` SDK with the Gemini Developer API at `v1beta`.
Direct mode calls Cala's MCP endpoint from the backend and sends only the
question and evidence to Gemini. Keep the Cala key scoped to Cala.
The optional managed mode uses `antigravity-preview-09-2026`. Provision its named
configuration with the documented REST Agents endpoint so that
`tools[].credential` is preserved. Use the SDK for Credentials and Interactions.
Keep provider keys out of source, browser responses, logs, and images.
Run `python -m pytest` with the project's virtual environment before delivery.
Use mocked provider responses in automated tests.
