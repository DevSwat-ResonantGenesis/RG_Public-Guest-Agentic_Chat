"""
Self-contained tool handlers for Guest Agentic Chat.
No imports from agent_engine_service — fully standalone.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from html import unescape
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

# ── Shared constants ──

_WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_page_content(html: str, url: str, max_length: int = 15000, extract_links: bool = True) -> dict:
    """Extract clean structured content from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        text = re.sub(r"(?is)<(script|style|nav|footer|header).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"url": url, "title": "", "content": text[:max_length], "links": []}

    try:
        import lxml  # noqa: F401
        parser = "lxml"
    except ImportError:
        parser = "html.parser"
    soup = BeautifulSoup(html, parser)

    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside",
                               "iframe", "noscript", "svg", "form"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    main = soup.find("article") or soup.find("main") or soup.find(role="main") or soup.body or soup

    parts = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "pre", "code", "blockquote"]):
        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) < 3:
            continue
        tag = el.name
        if tag in ("h1", "h2", "h3", "h4"):
            level = int(tag[1])
            parts.append(f"\n{'#' * level} {text}\n")
        elif tag == "li":
            parts.append(f"  • {text}")
        elif tag == "blockquote":
            parts.append(f"> {text}")
        elif tag in ("pre", "code"):
            parts.append(f"```\n{text}\n```")
        else:
            parts.append(text)

    content = "\n".join(parts).strip()
    if not content:
        content = main.get_text(separator="\n", strip=True)

    links = []
    if extract_links:
        for a in (main.find_all("a", href=True) if main else []):
            href = a["href"]
            link_text = a.get_text(strip=True)
            if href.startswith("http") and link_text and len(link_text) > 2:
                links.append({"text": link_text[:100], "url": href})
            if len(links) >= 20:
                break

    return {"url": url, "title": title, "content": content[:max_length], "content_length": len(content), "links": links}


async def _fetch_and_extract(url: str, max_length: int = 15000, extract_links: bool = True) -> dict:
    """Fetch a URL and extract clean content."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=_WEB_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return {"url": url, "error": f"HTTP {resp.status_code}"}
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" in ct:
                try:
                    return {"url": url, "content": json.dumps(resp.json(), indent=2)[:max_length], "content_type": "json"}
                except Exception:
                    pass
            html = resp.text
            if len(html) > 2_000_000:
                html = html[:2_000_000]
            return _extract_page_content(html, url, max_length, extract_links)
    except Exception as e:
        return {"url": url, "error": str(e)[:300]}


# ════════════════════════════════════════
# TOOL HANDLERS
# ════════════════════════════════════════

async def handle_web_search(args: dict) -> dict:
    """Web search via Tavily with key rotation."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "Missing 'query' parameter"}
    max_results = min(int(args.get("max_results", 5)), 10)
    tavily_raw = os.getenv("TAVILY_API_KEY", "")
    tavily_keys = [k.strip() for k in tavily_raw.split(",") if k.strip()]
    if not tavily_keys:
        return {"error": "Web search not configured."}
    for key in tavily_keys:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.tavily.com/search", json={
                    "api_key": key, "query": query, "search_depth": "advanced",
                    "max_results": max_results, "include_answer": True,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    results = [{"title": r.get("title", ""), "url": r.get("url", ""),
                                "snippet": r.get("content", "")[:400], "published_date": r.get("published_date")}
                               for r in data.get("results", [])[:max_results]]
                    out = {"query": query, "results": results, "count": len(results)}
                    if data.get("answer"):
                        out["ai_summary"] = data["answer"]
                    return out
        except Exception as e:
            logger.warning(f"Tavily key failed: {e}")
    return {"error": "Web search temporarily unavailable.", "query": query}


async def handle_fetch_url(args: dict) -> dict:
    """Fetch URL content."""
    url = (args.get("url") or "").strip()
    if not url:
        return {"error": "Missing 'url' parameter"}
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ResonantGenesis-Bot/1.0"})
            content_type = resp.headers.get("content-type", "")
            if "text" in content_type or "json" in content_type or "xml" in content_type:
                return {"url": url, "status": resp.status_code, "content": resp.text[:4000]}
            return {"url": url, "status": resp.status_code, "content_type": content_type, "note": "Binary content not displayed"}
    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)[:200]}"}


async def handle_read_webpage(args: dict) -> dict:
    """Read a single webpage and extract structured content."""
    url = (args.get("url") or "").strip()
    if not url:
        return {"error": "url is required"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    max_length = int(args.get("max_length", 15000))
    return await _fetch_and_extract(url, max_length, True)


async def handle_read_many_pages(args: dict) -> dict:
    """Read multiple web pages in parallel."""
    urls = args.get("urls", [])
    if isinstance(urls, str):
        try:
            urls = json.loads(urls)
        except Exception:
            urls = [u.strip() for u in urls.split(",") if u.strip()]
    if not urls or not isinstance(urls, list):
        return {"error": "urls is required — provide a list of URLs"}
    urls = urls[:5]
    max_length = int(args.get("max_length_per_page", 8000))
    clean_urls = [("https://" + u.strip() if not u.strip().startswith(("http://", "https://")) else u.strip()) for u in urls]
    results = await asyncio.gather(*[_fetch_and_extract(u, max_length, False) for u in clean_urls])
    return {"pages": list(results), "total": len(results),
            "succeeded": sum(1 for r in results if "error" not in r),
            "failed": sum(1 for r in results if "error" in r)}


async def handle_reddit_search(args: dict) -> dict:
    """Search Reddit via Tavily."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    subreddit = (args.get("subreddit") or "").strip()
    limit = min(int(args.get("limit", 10)), 25)
    tavily_raw = os.getenv("TAVILY_API_KEY", "")
    tavily_keys = [k.strip() for k in tavily_raw.split(",") if k.strip()]
    if not tavily_keys:
        return {"error": "Search API not configured."}
    search_query = f"{query} r/{subreddit} reddit" if subreddit else f"{query} reddit"
    data = None
    last_error = ""
    for key in tavily_keys:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.tavily.com/search", json={
                    "api_key": key, "query": search_query, "max_results": limit,
                    "search_depth": "basic", "include_domains": ["reddit.com"],
                    "include_answer": True, "include_raw_content": False,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    break
                last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            last_error = str(e)[:200]
    if data is None:
        return {"error": f"Search failed. Last: {last_error}"}
    posts = []
    for item in data.get("results", []):
        url = item.get("url", "")
        title = item.get("title", "").replace(" : r/", " | r/").replace(" - Reddit", "").strip()
        sr_match = re.search(r"reddit\.com/r/(\w+)", url)
        posts.append({"title": title, "subreddit": sr_match.group(1) if sr_match else "",
                       "url": url, "snippet": item.get("content", "")[:500]})
    result = {"query": query, "subreddit": subreddit or "all", "results": posts, "count": len(posts)}
    if data.get("answer"):
        result["ai_summary"] = data["answer"]
    return result


async def handle_weather(args: dict) -> dict:
    """Get weather via wttr.in (free, no API key)."""
    location = (args.get("location") or "").strip()
    if not location:
        return {"error": "location is required"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://wttr.in/{location}", params={"format": "j1"},
                                    headers={"User-Agent": "ResonantGenesis/1.0"})
            if resp.status_code != 200:
                return {"error": f"Weather service returned {resp.status_code}"}
            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            area = data.get("nearest_area", [{}])[0]
            forecast = data.get("weather", [])
            city = area.get("areaName", [{}])[0].get("value", location)
            country = area.get("country", [{}])[0].get("value", "")
            result = {
                "location": f"{city}, {country}",
                "current": {
                    "temp_c": current.get("temp_C"), "temp_f": current.get("temp_F"),
                    "feels_like_c": current.get("FeelsLikeC"),
                    "condition": current.get("weatherDesc", [{}])[0].get("value", ""),
                    "humidity": current.get("humidity"), "wind_kmph": current.get("windspeedKmph"),
                    "wind_dir": current.get("winddir16Point"),
                },
                "forecast": [],
            }
            for day in forecast[:3]:
                hourly = day.get("hourly", [{}])
                mid = hourly[4] if len(hourly) > 4 else hourly[0] if hourly else {}
                result["forecast"].append({
                    "date": day.get("date"), "max_c": day.get("maxtempC"), "min_c": day.get("mintempC"),
                    "condition": mid.get("weatherDesc", [{}])[0].get("value", ""),
                    "chance_of_rain": mid.get("chanceofrain", ""),
                })
            return result
    except Exception as e:
        return {"error": f"Weather lookup failed: {str(e)[:300]}"}


async def handle_image_search(args: dict) -> dict:
    """Image search via SerpAPI."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    limit = min(int(args.get("limit", 8)), 20)
    serpapi_key = os.getenv("SERPAPI_KEY", "")
    if not serpapi_key:
        return {"error": "Image search not configured."}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params={
                "engine": "google_images", "q": query, "num": limit, "api_key": serpapi_key,
            })
            if resp.status_code != 200:
                return {"error": f"Image search failed: HTTP {resp.status_code}"}
            data = resp.json()
            images = [{"title": img.get("title", ""), "url": img.get("original", img.get("link", "")),
                        "thumbnail": img.get("thumbnail", ""), "source": img.get("source", "")}
                       for img in data.get("images_results", [])[:limit]]
            return {"query": query, "images": images, "count": len(images)}
    except Exception as e:
        return {"error": f"Image search failed: {str(e)[:300]}"}


async def handle_news_search(args: dict) -> dict:
    """News search via Tavily."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    max_results = min(int(args.get("max_results", 5)), 10)
    tavily_raw = os.getenv("TAVILY_API_KEY", "")
    tavily_keys = [k.strip() for k in tavily_raw.split(",") if k.strip()]
    if not tavily_keys:
        return {"error": "News search not configured."}
    for key in tavily_keys:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.tavily.com/search", json={
                    "api_key": key, "query": query, "max_results": max_results,
                    "search_depth": "advanced", "topic": "news", "include_answer": True,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    articles = [{"title": r.get("title", ""), "url": r.get("url", ""),
                                 "snippet": r.get("content", "")[:400], "published_date": r.get("published_date"),
                                 "source": r.get("url", "").split("/")[2] if "/" in r.get("url", "") else ""}
                                for r in data.get("results", [])[:max_results]]
                    out = {"query": query, "articles": articles, "count": len(articles)}
                    if data.get("answer"):
                        out["ai_summary"] = data["answer"]
                    return out
        except Exception as e:
            logger.warning(f"News Tavily key failed: {e}")
    return {"error": "News search temporarily unavailable."}


async def handle_places_search(args: dict) -> dict:
    """Places search via SerpAPI Google Maps."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    location = (args.get("location") or "").strip()
    serpapi_key = os.getenv("SERPAPI_KEY", "")
    if not serpapi_key:
        return {"error": "Places search not configured."}
    try:
        params = {"engine": "google_maps", "q": f"{query} in {location}" if location else query,
                  "api_key": serpapi_key, "type": "search"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            if resp.status_code != 200:
                return {"error": f"Places search failed: HTTP {resp.status_code}"}
            data = resp.json()
            places = [{"name": p.get("title", ""), "address": p.get("address", ""),
                        "rating": p.get("rating"), "reviews": p.get("reviews"),
                        "phone": p.get("phone", ""), "website": p.get("website", "")}
                       for p in data.get("local_results", [])[:10]]
            return {"query": query, "location": location or "auto", "places": places, "count": len(places)}
    except Exception as e:
        return {"error": f"Places search failed: {str(e)[:300]}"}


async def handle_youtube_search(args: dict) -> dict:
    """YouTube search via SerpAPI."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    limit = min(int(args.get("limit", 5)), 15)
    serpapi_key = os.getenv("SERPAPI_KEY", "")
    if not serpapi_key:
        return {"error": "YouTube search not configured."}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params={
                "engine": "youtube", "search_query": query, "api_key": serpapi_key,
            })
            if resp.status_code != 200:
                return {"error": f"YouTube search failed: HTTP {resp.status_code}"}
            data = resp.json()
            videos = [{"title": v.get("title", ""), "url": v.get("link", ""),
                        "channel": v.get("channel", {}).get("name", ""),
                        "views": v.get("views"), "published": v.get("published_date", ""),
                        "duration": v.get("length", ""), "description": v.get("description", "")[:200]}
                       for v in data.get("video_results", [])[:limit]]
            return {"query": query, "videos": videos, "count": len(videos)}
    except Exception as e:
        return {"error": f"YouTube search failed: {str(e)[:300]}"}


async def handle_wikipedia(args: dict) -> dict:
    """Wikipedia search/summary."""
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    action = (args.get("action") or "summary").strip()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if action == "search":
                resp = await client.get("https://en.wikipedia.org/w/api.php", params={
                    "action": "opensearch", "search": query, "limit": 10, "format": "json",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    titles = data[1] if len(data) > 1 else []
                    descs = data[2] if len(data) > 2 else []
                    urls = data[3] if len(data) > 3 else []
                    results = [{"title": titles[i], "description": descs[i] if i < len(descs) else "",
                                "url": urls[i] if i < len(urls) else ""} for i in range(len(titles))]
                    return {"query": query, "results": results, "count": len(results)}
            else:
                resp = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}")
                if resp.status_code == 200:
                    data = resp.json()
                    return {"title": data.get("title", ""), "extract": data.get("extract", ""),
                            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                            "thumbnail": data.get("thumbnail", {}).get("source", ""),
                            "description": data.get("description", "")}
                elif resp.status_code == 404:
                    search_resp = await client.get("https://en.wikipedia.org/w/api.php", params={
                        "action": "opensearch", "search": query, "limit": 5, "format": "json",
                    })
                    suggestions = search_resp.json()[1] if search_resp.status_code == 200 and len(search_resp.json()) > 1 else []
                    return {"error": f"Article '{query}' not found.", "suggestions": suggestions}
            return {"error": f"Wikipedia API error: HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": f"Wikipedia lookup failed: {str(e)[:300]}"}


async def handle_stock_crypto(args: dict) -> dict:
    """Stock/crypto prices via Yahoo Finance."""
    symbol = (args.get("symbol") or "").strip().upper()
    if not symbol:
        return {"error": "symbol is required (e.g. AAPL, BTC-USD)"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                                    params={"interval": "1d", "range": "5d"},
                                    headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return {"error": f"Could not find symbol '{symbol}'."}
            data = resp.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose", 0)
            change = round(price - prev_close, 2) if prev_close else 0
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
            return {
                "symbol": symbol, "name": meta.get("shortName", symbol),
                "currency": meta.get("currency", "USD"), "exchange": meta.get("exchangeName", ""),
                "price": round(price, 2), "previous_close": round(prev_close, 2) if prev_close else None,
                "change": change, "change_percent": change_pct,
                "market_state": meta.get("marketState", ""),
            }
    except Exception as e:
        return {"error": f"Stock/crypto lookup failed: {str(e)[:300]}"}


async def handle_generate_chart(args: dict) -> dict:
    """Chart generation via QuickChart.io."""
    chart_type = (args.get("type") or "bar").strip().lower()
    labels = args.get("labels", [])
    datasets = args.get("datasets", [])
    title = (args.get("title") or "").strip()
    if not labels or not datasets:
        return {"error": "Both 'labels' and 'datasets' are required."}
    chart_config = {"type": chart_type, "data": {"labels": labels, "datasets": datasets}}
    if title:
        chart_config["options"] = {"plugins": {"title": {"display": True, "text": title}}}
    try:
        import urllib.parse
        encoded = urllib.parse.quote(json.dumps(chart_config))
        chart_url = f"https://quickchart.io/chart?c={encoded}&w=600&h=400&bkg=white"
        if len(chart_url) > 8000:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://quickchart.io/chart/create", json={
                    "chart": chart_config, "width": 600, "height": 400, "backgroundColor": "white",
                })
                if resp.status_code == 200:
                    chart_url = resp.json().get("url", chart_url)
        return {"chart_url": chart_url, "type": chart_type, "title": title,
                "note": "Embed in markdown: ![chart](chart_url)"}
    except Exception as e:
        return {"error": f"Chart generation failed: {str(e)[:300]}"}


_SVG_SYSTEM_PROMPT = """You are an SVG diagram generator. You ONLY output valid SVG markup — no explanation, no markdown, no code fences.

Rules:
- Output ONLY the <svg>...</svg> element. Nothing else.
- Use viewBox for responsive sizing, e.g. viewBox="0 0 800 500"
- Use clean, modern design: rounded rects, soft colors, clear labels
- Color palette: #3b82f6 blue, #10b981 green, #f59e0b amber, #ef4444 red, #8b5cf6 purple
- Text: font-family="system-ui, sans-serif", white or dark text for contrast
- For flowcharts: rounded rectangles with arrow markers
- For architecture: layered boxes with labeled connections
- Max width 800px, max height 600px via viewBox
- Make text readable (min 12px equivalent)"""


async def handle_visualize(args: dict) -> dict:
    """SVG diagram generation via LLM."""
    description = (args.get("description") or args.get("prompt") or "").strip()
    diagram_type = (args.get("type") or "auto").strip().lower()
    if not description:
        return {"error": "description is required"}
    groq_key = os.getenv("GROQ_API_KEY", "").split(",")[0].strip()
    if not groq_key:
        return {"error": "Visualization service not configured."}
    user_prompt = (f"Generate an SVG {diagram_type} diagram for: {description}" if diagram_type != "auto"
                   else f"Generate an SVG diagram (best type) for: {description}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": _SVG_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                "temperature": 0.3, "max_tokens": 4096,
            }, headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"})
            if resp.status_code != 200:
                return {"error": f"SVG generation failed: HTTP {resp.status_code}"}
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            svg_match = re.search(r'(<svg[\s\S]*?</svg>)', content, re.IGNORECASE)
            if not svg_match:
                return {"error": "Failed to generate valid SVG.", "raw": content[:500]}
            svg_code = svg_match.group(1)
            svg_code = re.sub(r'<script[\s\S]*?</script>', '', svg_code, flags=re.IGNORECASE)
            svg_code = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', svg_code)
            return {"svg": svg_code, "type": diagram_type, "description": description}
    except Exception as e:
        return {"error": f"Visualization failed: {str(e)[:300]}"}


# ── Handler registry ──

HANDLER_MAP: Dict[str, Any] = {
    "web_search": handle_web_search,
    "fetch_url": handle_fetch_url,
    "read_webpage": handle_read_webpage,
    "read_many_pages": handle_read_many_pages,
    "reddit_search": handle_reddit_search,
    "image_search": handle_image_search,
    "news_search": handle_news_search,
    "places_search": handle_places_search,
    "youtube_search": handle_youtube_search,
    "wikipedia": handle_wikipedia,
    "weather": handle_weather,
    "stock_crypto": handle_stock_crypto,
    "generate_chart": handle_generate_chart,
    "visualize": handle_visualize,
}
