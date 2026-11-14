# Cala + Gemini Agent

AI agent that queries [Cala.ai](https://cala.ai)'s knowledge graph via MCP, powered by Gemini on Google Cloud.

## Quick Start (Local)

```bash
cp .env.example .env          # fill in your keys
pip install -r requirements.txt
uvicorn main:app --reload
```

## Test

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
