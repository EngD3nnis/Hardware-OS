# HardwareOS — AI Service

A separate **FastAPI** service that adds intelligence on top of the HardwareOS
backend. It **never touches the database** — it reads facts through the REST API,
forwarding the caller's JWT so tenancy and RBAC are preserved end-to-end.

## Capabilities

| Endpoint                          | What it does                                              |
|-----------------------------------|----------------------------------------------------------|
| `GET  /health`                    | Status + whether the LLM is enabled                      |
| `GET  /ai/forecast/revenue`       | Projects revenue for the next N days from the daily trend |
| `GET  /ai/forecast/stockouts`     | Which products will stock out within N days, + reorder qty |
| `POST /ai/ask`                    | Natural-language querying ("Why did revenue drop?")       |

All endpoints require an `Authorization: Bearer <HardwareOS JWT>` header — the
same token the frontend uses. The service forwards it upstream.

### Examples

```bash
TOKEN=...   # a HardwareOS access token

curl "localhost:8001/ai/forecast/revenue?horizon=14" -H "Authorization: Bearer $TOKEN"
curl "localhost:8001/ai/forecast/stockouts?horizon=14&days=30" -H "Authorization: Bearer $TOKEN"
curl -X POST localhost:8001/ai/ask -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"question":"Which branch performs worst?"}'
```

## Natural-language querying

If `ANTHROPIC_API_KEY` is set, `/ai/ask` answers with **Claude** (default
`claude-opus-4-8`), grounded strictly in JSON facts fetched from the API. With no
key, a **deterministic intent engine** answers the common executive questions
(revenue changes, worst/best branch, stock-outs, summaries) — so the feature
works out of the box and degrades gracefully. This mirrors the backend's
`InsightService`, which is the seam this service extends.

## Run

```bash
cp .env.example .env            # set HARDWAREOS_API_URL and (optionally) ANTHROPIC_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
# docs at http://localhost:8001/docs
```

Or via the root `docker-compose.yml` (service `ai`).

## Tests

```bash
pytest        # forecasting math, stock-out logic, and the heuristic answer engine
```

The forecasting and stock-out logic are pure functions ([app/forecasting.py](app/forecasting.py),
[app/inventory.py](app/inventory.py)), so they're tested without any network or DB.
