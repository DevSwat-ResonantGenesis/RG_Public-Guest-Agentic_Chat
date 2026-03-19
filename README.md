# RG Public Guest Agentic Chat

> **Part of the [ResonantGenesis](https://dev-swat.com) platform** — standalone microservice for public AI assistant chat.

Public-facing AI assistant for **unauthenticated visitors** on the ResonantGenesis platform. Provides real-time tool-augmented conversations with web search, weather, news, financial data, and more — all without requiring login.

## Architecture

```
Visitor → Nginx → Gateway → guest_agentic_chat (this service)
                                 ├── Groq API (primary LLM)
                                 ├── OpenAI API (fallback LLM)
                                 ├── Tavily API (web/news/reddit search)
                                 └── SerpAPI (images, YouTube, places)
```

**Key design decisions:**
- **No auth required** — rate limited per IP (configurable, default 20 req/min)
- **Native function calling** via direct Groq/OpenAI API (NOT JSON prompt injection)
- **14 guest-safe tools** — search, news, weather, stocks, charts, Wikipedia, YouTube, etc.
- **No database, no memory, no file ops** — completely stateless and safe for public exposure
- **SSE streaming** responses with real-time tool call visibility
- **Multi-key Groq support** — comma-separated keys for round-robin
- **Groq text-mode fallback** — parses `<function>` blocks when native tool calling fails

## Quick Start

```bash
# Clone
git clone git@github-devswat:DevSwat-ResonantGenesis/RG_Public-Guest-Agentic_Chat.git
cd RG_Public-Guest-Agentic_Chat

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys (see Environment Variables below)

# Run locally
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

## Docker

```bash
# Build
docker build -t rg-guest-agentic-chat .

# Run
docker run -p 8010:8010 --env-file .env rg-guest-agentic-chat
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/public/agentic-chat/stream` | SSE streaming agentic chat (main endpoint) |
| `GET` | `/public/agentic-chat/health` | Detailed health check — tools, rate limit, provider status |
| `GET` | `/health` | Simple health check |

### Request Body (`POST /public/agentic-chat/stream`)

```json
{
  "message": "What's the weather in San Francisco?",
  "conversation_history": [],
  "max_loops": 5
}
```

### SSE Events

| Event | Description |
|-------|-------------|
| `status` | Session started — tools count, guest flag |
| `thinking` | Loop N reasoning |
| `tool_call` | Tool invoked — name, args, loop |
| `tool_result` | Tool returned — name, result, loop |
| `response` | Final assistant text response |
| `done` | Session complete — loops, tokens, elapsed |
| `error` | Error occurred |

## LLM Providers

| Provider | Role | Model | Tool Calling |
|----------|------|-------|-------------|
| **Groq** | Primary | `llama-3.3-70b-versatile` | Native + text-mode fallback |
| **OpenAI** | Fallback | `gpt-4o` | Native |

Fallback chain: Groq (with tools) → Groq (without tools, text-mode FC) → OpenAI (with tools)

## Tools (14)

| Tool | Description | API |
|------|-------------|-----|
| `web_search` | Search the web for current information | Tavily |
| `fetch_url` | Fetch raw content from any URL | httpx |
| `read_webpage` | Extract clean structured content from URL | Tavily |
| `read_many_pages` | Read up to 5 pages in parallel | Tavily |
| `reddit_search` | Search Reddit discussions | Tavily |
| `image_search` | Search for images | SerpAPI |
| `news_search` | Latest news articles | Tavily |
| `places_search` | Businesses, restaurants on Google Maps | SerpAPI |
| `youtube_search` | Search YouTube videos | SerpAPI |
| `wikipedia` | Search and read Wikipedia articles | Wikipedia API |
| `weather` | Current weather + 3-day forecast | wttr.in |
| `stock_crypto` | Real-time stock/crypto prices | Yahoo Finance |
| `generate_chart` | Generate chart images (bar, line, pie, etc.) | QuickChart.io |
| `visualize` | Generate SVG diagrams inline | Built-in |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | **Yes** | Groq API key(s) — comma-separated for round-robin |
| `OPENAI_API_KEY` | No | OpenAI API key (fallback provider) |
| `TAVILY_API_KEY` | **Yes** | Tavily API key — web search, news, reddit |
| `SERPAPI_KEY` | No | SerpAPI key — image search, YouTube, places |
| `PUBLIC_CHAT_RATE_LIMIT` | No | Requests per minute per IP (default: `20`) |
| `GUEST_CHAT_MODEL` | No | Groq model (default: `llama-3.3-70b-versatile`) |
| `PORT` | No | Server port (default: `8010`) |

## File Structure

```
app/
├── main.py       # FastAPI app, SSE streaming endpoint, rate limiter, LLM calling
├── handlers.py   # Tool handler implementations (HANDLER_MAP)
├── tools.py      # OpenAI-format tool definitions (GUEST_TOOLS)
.env.example      # Environment variable template
Dockerfile        # Production Docker image
requirements.txt  # Python dependencies
```

## Gateway Integration

The gateway proxies public chat requests:
```
/api/v1/public/agentic-chat/* → http://guest_agentic_chat:8010/public/agentic-chat/*
```

## Security

- **No authentication** — this is intentional for public visitors
- **IP-based rate limiting** — prevents abuse (configurable via `PUBLIC_CHAT_RATE_LIMIT`)
- **No database access** — cannot read or write any user data
- **No memory** — conversations are not stored; each request is independent
- **No file operations** — no filesystem access whatsoever
- **Guest-safe tools only** — web search, weather, etc. No internal platform tools exposed

## Related Modules

| Module | Repo | Description |
|--------|------|-------------|
| Registered Users Agentic Chat | `RG_Registered_Users_Agentic_Chat` | Full agentic chat for authenticated users (130+ tools) |
| Unified LLM Client | `RG_UnifiedLLMClient` | Shared LLM provider abstraction (not used by this service) |
| Unified Tool Registry | `RG_Unified_Tool_Registry-Observability_Module` | Tool registry (not used by this service) |

## Deployment Status

- **Extracted from**: `genesis2026_production_backend/chat_service` (public chat router)
- **Production**: Not yet deployed as standalone — currently runs inside `chat_service`
- **Target**: Replace the public chat router in `chat_service` with this standalone service

---

**Organization**: [DevSwat-ResonantGenesis](https://github.com/DevSwat-ResonantGenesis)
**Platform**: [dev-swat.com](https://dev-swat.com)
