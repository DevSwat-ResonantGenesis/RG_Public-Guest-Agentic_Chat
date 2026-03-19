# Guest Agentic Chat — Standalone Microservice

Public AI assistant for unauthenticated visitors on the ResonantGenesis platform.

## Architecture

- **No auth required** — rate limited per IP (20 req/min)
- **Native function calling** via direct Groq/OpenAI API (NOT JSON prompt injection)
- **14 guest-safe tools**: web search, news, weather, stocks, charts, Wikipedia, YouTube, etc.
- **No DB, no memory, no file ops** — completely stateless
- **SSE streaming** responses

## Quick Start

```bash
# Install deps
pip install -r requirements.txt

# Set API keys
cp .env.example .env
# Edit .env with your keys

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

## Docker

```bash
docker build -t guest-agentic-chat .
docker run -p 8010:8010 --env-file .env guest-agentic-chat
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/public/agentic-chat/stream` | SSE streaming chat |
| GET | `/public/agentic-chat/health` | Health + tool list |
| GET | `/health` | Simple health check |

## LLM Providers

| Provider | Role | Model |
|----------|------|-------|
| Groq | Primary | llama-3.3-70b-versatile |
| OpenAI | Fallback | gpt-4o |

## Tools (14)

web_search, fetch_url, read_webpage, read_many_pages, reddit_search,
image_search, news_search, places_search, youtube_search, wikipedia,
weather, stock_crypto, generate_chart, visualize
