# Cala + Gemini Agent

AI agent that queries [Cala.ai](https://cala.ai)'s knowledge graph via MCP, powered by Gemini on Google Cloud.

## Quick Start (Local)

```bash
cp .env.example .env          # fill in your keys
pip install -r requirements.txt
uvicorn main:app --reload
```

## Test

### Explore a Cala export on the map

From the `cala-agent` directory, generate a report:

```powershell
python scan_export.py "$env:USERPROFILE\Downloads\slush-2026-graph.json" --output slush-network.json
```

Open the app and choose the report under **Slush snapshot**. To load the report
automatically, set `$env:CALA_SNAPSHOT_REPORT = (Resolve-Path slush-network.json).Path`
before starting the server. Only configure this on a server whose users can
access the report. Select a starting entity and a reachable attendee to draw
their path. Double-click a node to explore from it and click an edge for its
relationship properties and sources.

The snapshot uses the report's hop limit. Industry, headquarters and
registration edges can be enabled in the map. Coverage reflects what Cala
retrieved before the export ended.

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Find AI startups in Berlin with Series A funding"}'
```

## Deploy to Cloud Run

```bash
# Store secrets
echo -n "YOUR_KEY" | gcloud secrets create cala-api-key --data-file=-

# Deploy
gcloud run deploy cala-agent \
  --source . \
  --region us-central1 \
  --set-secrets CALA_API_KEY=cala-api-key:latest \
  --set-env-vars GEMINI_MODEL=gemini-2.5-flash
```
