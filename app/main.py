"""
Guest Agentic Chat — Standalone Microservice
=============================================
Public AI assistant for unauthenticated visitors.
Uses NATIVE FUNCTION CALLING (direct Groq/OpenAI API) — no JSON prompt injection.

Security:
  - No auth required
  - Rate limited per IP (default 20 req/min)
  - No DB writes, no memory, no file ops
  - Guest-safe tools only (search, weather, charts, etc.)
"""

import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from .handlers import HANDLER_MAP
from .tools import GUEST_TOOLS, TOOL_NAMES

# Groq/Llama text-mode tool call parser — handles ALL observed variants:
#   <function(web_search){"query":"..."}</function>
#   <function=web_search>{"query":"..."}</function>
#   <function(web_search {"query":"..."})></function>
#   <function\web_search{"query":"..."}</function>
#   <function/web_search,{"query":"..."}>
#   <function=wikipedia({"query":"...", "action":"summary"})
_TOOL_NAMES_SET = set(TOOL_NAMES)


def _parse_text_tool_calls(content: str):
    """Parse text-mode tool calls from Groq/Llama — general approach.
    Finds any known tool name near a JSON object in <function...> blocks."""
    if "<function" not in content:
        return []
    results = []
    # Find all JSON objects in the content
    for tool_name in TOOL_NAMES:
        if tool_name not in content:
            continue
        # Find JSON after the tool name
        idx = content.find(tool_name)
        # Search for { after the tool name
        rest = content[idx + len(tool_name):]
        brace_start = rest.find("{")
        if brace_start == -1:
            continue
        # Extract balanced JSON
        depth = 0
        json_start = idx + len(tool_name) + brace_start
        json_end = json_start
        for i, ch in enumerate(content[json_start:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    json_end = json_start + i + 1
                    break
        if json_end > json_start:
            args_str = content[json_start:json_end]
            try:
                args = json.loads(args_str)
                results.append({"name": tool_name, "arguments": args_str, "args_parsed": args})
            except json.JSONDecodeError:
                pass
    return results

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("guest_chat")

# ── App ──
app = FastAPI(title="Guest Agentic Chat", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LLM config ──
_raw_key = os.getenv("GROQ_API_KEY", "")
_groq_keys = [k.strip() for k in _raw_key.split(",") if k.strip()]
GROQ_API_KEY = _groq_keys[0] if _groq_keys else ""
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("GUEST_CHAT_MODEL", "llama-3.3-70b-versatile")
OPENAI_FALLBACK_MODEL = "gpt-4o"


async def _call_groq_raw(key: str, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Single Groq API call. Returns parsed response dict or None on failure."""
    try:
        payload: Dict[str, Any] = {
            "model": DEFAULT_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                return {
                    "content": msg.get("content") or "",
                    "tool_calls": msg.get("tool_calls") or [],
                    "usage": data.get("usage", {}),
                    "provider": "groq",
                }
            # Groq tool_use_failed — extract the failed text-mode output
            if resp.status_code == 400 and tools:
                try:
                    err = resp.json().get("error", {})
                    failed = err.get("failed_generation", "")
                    if failed and err.get("code") == "tool_use_failed":
                        logger.info(f"Groq tool_use_failed, extracting from failed_generation")
                        return {
                            "content": failed,
                            "tool_calls": [],
                            "usage": {},
                            "provider": "groq",
                        }
                except Exception:
                    pass
            logger.warning(f"Groq returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Groq call failed: {e}")
    return None


async def _call_llm(messages: List[Dict], tools: List[Dict]) -> Dict:
    """Call LLM with native function calling. Groq primary, OpenAI fallback.
    Handles Groq's tool_use_failed by extracting text-mode tool calls.
    Returns dict with: content, tool_calls, usage, provider, error."""
    # Try each Groq key WITH tools
    for key in _groq_keys:
        result = await _call_groq_raw(key, messages, tools)
        if result:
            return result

    # Fallback: Groq WITHOUT tools (model still sees tool descriptions in system prompt)
    for key in _groq_keys:
        result = await _call_groq_raw(key, messages, None)
        if result:
            return result

    # Fallback: OpenAI (with tools — OpenAI has reliable native FC)
    if OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": OPENAI_FALLBACK_MODEL,
                        "messages": messages,
                        "tools": tools,
                        "temperature": 0.7,
                        "max_tokens": 4096,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    return {
                        "content": msg.get("content") or "",
                        "tool_calls": msg.get("tool_calls") or [],
                        "usage": data.get("usage", {}),
                        "provider": "openai",
                    }
                logger.warning(f"OpenAI returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"OpenAI call failed: {e}")

    return {"error": "All LLM providers failed.", "content": "", "tool_calls": [], "usage": {}, "provider": "none"}

# ── Rate limiter ──
_rate_limits: Dict[str, list] = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = int(os.getenv("PUBLIC_CHAT_RATE_LIMIT", "20"))


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[ip].append(now)
    return True


# ── System prompt (no tool format instructions — native FC handles that) ──
SYSTEM_PROMPT = """You are Resonant Assistant — an AI assistant on the ResonantGenesis platform.

You have access to tools for web search, weather, news, stocks, charts, and more.
Use tools when you need current data — never guess or fabricate information.

RULES:
1. Use web_search for current information. Never fabricate data.
2. Prefer read_webpage over fetch_url — it returns structured content.
3. Use read_many_pages to read up to 5 pages in parallel.
4. Use weather for forecasts, stock_crypto for prices, news_search for headlines.
5. Use image_search for images, youtube_search for videos, places_search for businesses.
6. Use wikipedia for factual knowledge, generate_chart for data visualization.
7. Use visualize to generate SVG diagrams inline.
8. Be concise, direct, and use Markdown formatting.
9. You are talking to a visitor of ResonantGenesis. Be helpful and welcoming.
10. If asked about features, explain that signing up unlocks long-term memory, AI agents, code analysis, and more.
11. Always identify yourself as Resonant Assistant when asked."""


class PublicChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, Any]]] = None
    max_loops: int = 5


@app.post("/public/agentic-chat/stream")
async def public_chat_stream(body: PublicChatRequest, request: Request):
    """Public agentic chat — no auth, native function calling, rate limited."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        return JSONResponse(status_code=429,
                            content={"error": "Rate limit exceeded. Please wait before trying again."})

    async def _stream():
        start_time = time.time()
        loop_count = 0
        total_tokens = 0

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add conversation history (last 10 for guests)
        if body.conversation_history:
            for msg in body.conversation_history[-10:]:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        messages.append({"role": "user", "content": body.message})

        max_loops = min(body.max_loops, 5)

        yield f"event: status\ndata: {json.dumps({'status': 'started', 'tools_available': len(TOOL_NAMES), 'guest': True})}\n\n"

        try:
            while loop_count < max_loops:
                loop_count += 1
                yield f"event: thinking\ndata: {json.dumps({'loop': loop_count, 'message': 'Reasoning...'})}\n\n"

                # ── NATIVE FUNCTION CALLING with tool_choice: auto ──
                response = await _call_llm(messages, GUEST_TOOLS)

                if response.get("error"):
                    yield f"event: error\ndata: {json.dumps({'error': response['error']})}\n\n"
                    break

                total_tokens += response.get("usage", {}).get("total_tokens", 0)

                # ── Check for native tool calls ──
                tool_calls = response.get("tool_calls") or []

                if tool_calls:
                    # Native FC — tool_calls are dicts from the API
                    messages.append({
                        "role": "assistant",
                        "content": response.get("content") or None,
                        "tool_calls": tool_calls,
                    })

                    for tc in tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        call_id = tc.get("id", f"call_{loop_count}")

                        # Parse arguments
                        raw_args = func.get("arguments", "{}")
                        try:
                            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError:
                            tool_args = {}

                        yield f"event: tool_call\ndata: {json.dumps({'tool': tool_name, 'args': tool_args, 'loop': loop_count})}\n\n"

                        # Execute tool
                        handler = HANDLER_MAP.get(tool_name)
                        if not handler:
                            tool_result = {"error": f"Tool '{tool_name}' not available. Available: {', '.join(TOOL_NAMES)}"}
                        else:
                            try:
                                tool_result = await handler(tool_args)
                            except Exception as e:
                                tool_result = {"error": str(e)[:500]}

                        result_str = json.dumps(tool_result, default=str)
                        if len(result_str) > 4000:
                            result_str = result_str[:4000] + "...(truncated)"

                        yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'result': result_str[:3000], 'loop': loop_count})}\n\n"

                        # Append tool result for next LLM call
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": result_str,
                        })

                    continue  # Loop back to LLM with tool results

                else:
                    # No native tool calls — check for text-mode tool calls (Groq/Llama fallback)
                    content = response.get("content", "")
                    text_calls = _parse_text_tool_calls(content) if content else []

                    if text_calls:
                        # Text-mode tool calls detected — process them
                        messages.append({"role": "assistant", "content": content})

                        for tc_text in text_calls:
                            tool_name = tc_text["name"]
                            tool_args = tc_text["args_parsed"]

                            yield f"event: tool_call\ndata: {json.dumps({'tool': tool_name, 'args': tool_args, 'loop': loop_count})}\n\n"

                            handler = HANDLER_MAP.get(tool_name)
                            if not handler:
                                tool_result = {"error": f"Tool '{tool_name}' not available."}
                            else:
                                try:
                                    tool_result = await handler(tool_args)
                                except Exception as e:
                                    tool_result = {"error": str(e)[:500]}

                            result_str = json.dumps(tool_result, default=str)
                            if len(result_str) > 4000:
                                result_str = result_str[:4000] + "...(truncated)"

                            yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'result': result_str[:3000], 'loop': loop_count})}\n\n"

                            messages.append({"role": "user", "content": f"Tool result for {tool_name}:\n{result_str}"})

                        continue  # Loop back for LLM to process results

                    # Final text response (no tool calls at all)
                    if content:
                        yield f"event: response\ndata: {json.dumps({'content': content, 'loop': loop_count, 'tokens': total_tokens})}\n\n"
                    break

            elapsed = round(time.time() - start_time, 2)
            yield f"event: done\ndata: {json.dumps({'loops': loop_count, 'tokens': total_tokens, 'elapsed_seconds': elapsed, 'guest': True})}\n\n"

        except Exception as e:
            logger.exception("Public chat error")
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:500]})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/public/agentic-chat/health")
async def health():
    return {
        "status": "healthy",
        "service": "guest-agentic-chat",
        "tools_available": len(TOOL_NAMES),
        "tools": TOOL_NAMES,
        "rate_limit": f"{RATE_LIMIT_MAX}/min",
        "groq_key_configured": bool(GROQ_API_KEY),
        "mode": "native-function-calling",
    }


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "guest-agentic-chat"}
