# RG Public Guest Agentic Chat

> **Part of the [ResonantGenesis](https://dev-swat.com) platform** — standalone microservice for public AI assistant chat.

[![Status: Production](https://img.shields.io/badge/Status-Production-brightgreen.svg)]()
[![Docker: rg_public_guest_chat](https://img.shields.io/badge/Docker-rg__public__guest__chat-blue.svg)]()
[![Port: 8010](https://img.shields.io/badge/Port-8010-orange.svg)]()
[![License: RG Source Available](https://img.shields.io/badge/License-RG%20Source%20Available-blue.svg)](LICENSE.txt)

Public-facing AI assistant for **unauthenticated visitors** on the ResonantGenesis platform. Provides real-time tool-augmented conversations with web search, weather, news, financial data, and more — all without requiring login.

## Architecture

```
Visitor → Nginx → Gateway → rg_public_guest_chat (this service, port 8010)
                                 ├── rg_llm (volume-mounted, multi-provider with fallback)
                                 │    ├── Groq API (primary)
                                 │    ├── OpenAI API (fallback)
                                 │    ├── Anthropic API (fallback)
                                 │    └── Gemini API (fallback)
                                 ├── Tavily API (web/news/reddit search)
                                 └── SerpAPI (images, YouTube, places)
```

**Key design decisions:**
- **No auth required** — rate limited per IP (configurable, default 20 req/min)
- **Native function calling** via direct LLM provider APIs (NOT JSON prompt injection)
- **Multi-provider LLM with automatic fallback** via `rg_llm` (volume-mounted shared client)
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

## LLM Providers (via `rg_llm`)

| Provider | Role | Model | Tool Calling |
|----------|------|-------|-------------|
| **Groq** | Primary | `llama-3.3-70b-versatile` | Native + text-mode fallback |
| **OpenAI** | Fallback | `gpt-4o` | Native |
| **Anthropic** | Fallback | `claude-sonnet-4-20250514` | Native |
| **Gemini** | Fallback | `gemini-2.0-flash` | Native |

Fallback chain (via `rg_llm` `UnifiedLLMClient`): Groq → OpenAI → Anthropic → Gemini. Provider keys resolved from environment. Groq also supports text-mode fallback when native tool calling fails.

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

## Volume Mounts

| Mount | Source Repo | Path in Container |
|-------|-----------|-------------------|
| `rg_llm` | `RG_UnifiedLLMClient` | `/app/rg_llm:ro` |

Uses `PYTHONPATH=/app` so imports work as `from rg_llm import ...`.

## Gateway Integration

The gateway SSE streaming proxy routes public chat requests:
```
/api/v1/public/agentic-chat/* → http://rg_public_guest_chat:8010/public/agentic-chat/*
/public/agentic-chat/*        → http://rg_public_guest_chat:8010/public/agentic-chat/*
```

## Security

- **No authentication** — this is intentional for public visitors
- **IP-based rate limiting** — prevents abuse (configurable via `PUBLIC_CHAT_RATE_LIMIT`)
- **No database access** — cannot read or write any user data
- **No memory** — conversations are not stored; each request is independent
- **No file operations** — no filesystem access whatsoever
- **Guest-safe tools only** — web search, weather, etc. No internal platform tools exposed

## Related Modules

| Module | Repo | Relationship |
|--------|------|-------------|
| Registered Users Agentic Chat | [`RG_Registered_Users_Agentic_Chat`](https://github.com/DevSwat-ResonantGenesis/RG_Registered_Users_Agentic_Chat) | Authenticated variant (112 handlers, 4 providers, DB, BYOK) |
| Unified LLM Client | [`RG_UnifiedLLMClient`](https://github.com/DevSwat-ResonantGenesis/RG_UnifiedLLMClient) | Multi-provider LLM abstraction (volume-mounted into this service) |
| Unified Tool Registry | [`RG_Unified_Tool_Registry-Observability_Module`](https://github.com/DevSwat-ResonantGenesis/RG_Unified_Tool_Registry-Observability_Module) | Tool registry + observability (not used by this service — tools defined locally) |
| AST Analysis | [`RG_AST_analysis`](https://github.com/DevSwat-ResonantGenesis/RG_AST_analysis) | Code analysis service (not called by guest chat) |
| Resonant IDE | [`RG_IDE`](https://github.com/DevSwat-ResonantGenesis/RG_IDE) | AI-native VS Code fork (uses Registered Users Chat, not this) |

## Deployment Status

- **Status**: ✅ **Production** — deployed as standalone Docker container `rg_public_guest_chat`
- **Extracted from**: `genesis2026_production_backend/agent_engine_service` (`routers_public_chat.py` — deleted from monolith)
- **Server path**: `/home/deploy/RG_Public-Guest-Agentic_Chat` (cloned from DevSwat GitHub)
- **Docker service**: `rg_public_guest_chat` in `docker-compose.unified.yml`
- **Port**: 8010 (internal Docker network)

---

**Organization**: [DevSwat-ResonantGenesis](https://github.com/DevSwat-ResonantGenesis)
**Platform**: [dev-swat.com](https://dev-swat.com)
