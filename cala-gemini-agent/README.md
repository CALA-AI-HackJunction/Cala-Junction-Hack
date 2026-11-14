# Cala Research

A FastAPI chat UI backed by the Gemini Developer API and Cala's remote Model
Context Protocol (MCP) server. The default `CALA_CONNECTION_MODE=direct` uses
the app's MCP client to call Cala's `knowledge_search`. The app sends the
question and retrieved evidence to Gemini and polls Gemini for the answer.
Follow-up turns retain the Gemini interaction history.

The managed Antigravity path is available as `CALA_CONNECTION_MODE=managed`
for projects where Google accepts the stored MCP credential reference. During
live testing, Google's API returned HTTP 400 for `tools[].credential` in both
agent creation and interaction creation. Direct mode uses `GEMINI_MODEL`
(default `gemini-3.8-flash`), supports text research, and has no remote sandbox.

## Managed preview API contract

| Component | Implementation |
| --- | --- |
| Antigravity | Google documents `antigravity-preview-09-2026` as a **base agent ID**. The underlying Gemini model is selected by Google unless explicitly configured. |
| Agents | Setup registers a named agent at the Gemini Developer API's `v1beta/agents` endpoint, with the three built-in tools and Cala. The installed `google-genai==2.34.0` MCP schema omits `credential`, so direct REST preserves that field. |
| Credentials | Setup calls the SDK's create and update methods. Google stores the Cala key as a bearer-token credential with custom header `X-API-KEY` and an empty prefix. The agent definition contains only the credential ID. |
| Interactions | The SDK starts and polls background interactions and supports synchronous chat. Follow-ups use the previous interaction ID and, when supplied, the same environment ID. |
| Cala | The documented Streamable HTTP endpoint is `https://api.cala.ai/mcp/`. Google sends the custom header when it calls this endpoint. |

The setup script reuses an existing matching agent and rotates the credential.
The Developer API's published agent management methods and the pinned SDK
provide create, get, list, and delete. To change a saved definition, provision
under a new `GEMINI_AGENT_ID` and deploy with that ID. An existing agent with an
unexpected definition stops setup before credential rotation. The credential ID
is shared across app-managed agent versions in the same Gemini project.

The managed architecture retains hosted Python execution, tools, sandbox
continuity, and asynchronous execution. The implementation depends on access
to Google's managed-agent preview. Live provider availability is verified by
the smoke test below.

[Antigravity](https://aistudio.google.com/docs/antigravity-agent) ·
[Custom agents](https://aistudio.google.com/docs/custom-agents) ·
[Credentials](https://aistudio.google.com/docs/agent-credentials) ·
[Managed-agent quickstart](https://aistudio.google.com/docs/managed-agents-quickstart) ·
[Cala MCP](https://docs.cala.ai/integrations/mcp#other)

## Run locally

Use Python 3.12, a Gemini Developer API key from a billing-enabled project
with managed-agent access, and a Cala key from the Cala console. Run from this
project directory.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set `GEMINI_API_KEY` and `CALA_API_KEY` in the local `.env` file. For direct
mode, start the app after saving the file.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8080 --no-access-log
```

### macOS or Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
# Set GEMINI_API_KEY and CALA_API_KEY in .env using your editor.
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8080 --no-access-log
```

Open [the local chat](http://127.0.0.1:8080). Ask it to use Cala's
`knowledge_search` for a topic covered by your Cala key and cite a source you
can verify. Follow up by asking it to summarize the same results in a table.
In managed mode, run `setup_agent.py --prompt-cala-key` before starting the
app. To validate the managed tool call itself, inspect the interaction steps from your
trusted local Gemini client. Use the job ID from the browser's network
inspector and print only the Cala tool names returned for that job.

```python
from gemini_client import load_settings, make_client, required_setting

load_settings()
with make_client(required_setting("GEMINI_API_KEY")) as client:
    job = client.interactions.get(id="JOB_ID_FROM_BROWSER")
    print([
        step.name for step in (job.steps or [])
        if step.type == "mcp_server_tool_result" and step.server_name == "cala"
    ])
```

Check for a Cala tool in the list and verify a citation against its original
source. This step uses your paid Gemini project and Cala account.

## Access and data handling

- In direct mode, the runtime sends the Cala key directly to Cala and the
  Gemini key directly to Google. Managed mode uses the Cala key during
  provisioning and rotation, then Google injects it into the Cala request.
  The project excludes local secrets from Git, Docker, and Cloud Run source
  uploads. Server exceptions return generic messages.
- Local mode defaults to open access on loopback. For standalone use, set a
  random `APP_ACCESS_TOKEN` of at least 32 ASCII characters without whitespace,
  run behind HTTPS, and use the **Access token** dialog. The browser keeps that
  app token in session storage.
- Every job and follow-up requires the signed receipt issued for it. Treat it
  like a session credential. Receipts expire after 24 hours. A local restart
  invalidates old receipts when `CHAT_SIGNING_KEY` is unset.
- Anyone with access to the app shares the configured Cala access. Use a Cala
  key limited to data this audience can read. Prompts and retrieved content go
  to Google and relevant queries go to Cala. Google Search and URL Context may
  send queries or URLs to public services. Instructions to keep private content
  out of public requests are behavioral guidance. For private workflows that
  require enforced egress isolation, review the available tools and managed
  sandbox network settings before granting the service access to that data.
- **New chat** clears the browser conversation and stops polling. Jobs already
  accepted by Google may continue. History lives in the open page and Google's
  stored interactions. Refreshing the page starts a new browser conversation.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Process health, `{"status":"ok"}`. |
| POST | `/api/chat` | Synchronous answer with `reply`, `interaction_id`, and `environment_id`. |
| POST | `/api/jobs` | Accepts the same input and returns HTTP 202 with the interaction ID and state. |
| GET | `/api/jobs/{interaction_id}` | Returns state, environment ID, and final Markdown and rendered HTML when available. |

POST JSON is `{"message":"…"}`, optionally with `previous_interaction_id`
and/or `environment_id`. Echo the `X-Chat-Receipt` response header when polling
or continuing a turn. Use the latest receipt from the matching response.
`queued` and `in_progress` are pending. The browser polls every two seconds.
If app authentication is configured, send `Authorization: Bearer <token>`.

## Deploy privately to Cloud Run

1. Select a Gemini Developer API key and a Cala key for direct mode.
2. In the Cloud Run project's Secret Manager, add `gemini-api-key`,
   `cala-api-key`, and `cala-chat-signing-key`. Generate the signing value locally with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Enter both
   values directly into Secret Manager. Use a dedicated Cloud Run runtime
   service account and grant it Secret Manager Secret Accessor on these
   secrets. The deployer also needs Cloud Run source deployment and service
   account usage permissions.
3. From the project directory, deploy with the Google Cloud CLI. Replace the
   project ID and secret version numbers with your own values. The source
   deploy uses the provided Dockerfile.

```bash
PROJECT_ID=your-cloud-run-project
REGION=europe-north1
gcloud run deploy cala-gemini-agent \
  --project "$PROJECT_ID" --region "$REGION" \
  --source . --port 8080 --timeout 900 --no-allow-unauthenticated \
  --service-account "cala-run@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars CALA_CONNECTION_MODE=direct,GEMINI_MODEL=gemini-3.8-flash \
  --set-secrets GEMINI_API_KEY=gemini-api-key:1,CALA_API_KEY=cala-api-key:1,CHAT_SIGNING_KEY=cala-chat-signing-key:1
```

4. Grant intended users Cloud Run Invoker on the service. For browser testing,
   run the authenticated proxy from WSL, macOS, or Linux, then open
   [the proxied chat](http://localhost:8080).

```bash
gcloud run services proxy cala-gemini-agent \
  --project "$PROJECT_ID" --region "$REGION" --port 8080
```

Cloud Run IAM handles deployment access. For direct browser login for a team,
configure Identity-Aware Proxy. Cloud Run requires a stable signing key so an
interaction started by one instance can be polled on another. Changing the key
invalidates outstanding receipts. To rotate a provider key in direct mode,
deploy a revision with the new Secret Manager version and verify it serves
requests before revoking the old key. In managed mode, rotate the Cala
credential with the setup script.

[Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets) ·
[Private service proxy](https://docs.cloud.google.com/run/docs/authenticating/developers) ·
[Identity-Aware Proxy](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
