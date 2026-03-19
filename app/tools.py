"""
Guest tool definitions in OpenAI function-calling format.
Used with native function calling — NO JSON prompt injection.
"""

GUEST_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, articles, documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (1-10, default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read raw content from any URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Read a webpage and extract clean structured content (preferred over fetch_url).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to read"},
                    "max_length": {"type": "integer", "description": "Max chars to return (default 15000)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_many_pages",
            "description": "Read multiple web pages in parallel (max 5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "List of URLs to read"},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reddit_search",
            "description": "Search Reddit for discussions and recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "subreddit": {"type": "string", "description": "Limit to subreddit (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_search",
            "description": "Search for images on the web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Image search query"},
                    "limit": {"type": "integer", "description": "Number of results (default 8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "news_search",
            "description": "Search latest news articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News topic"},
                    "max_results": {"type": "integer", "description": "Number of results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "places_search",
            "description": "Search for businesses, restaurants, locations on Google Maps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to find"},
                    "location": {"type": "string", "description": "City or area (optional)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": "Search YouTube for videos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wikipedia",
            "description": "Search and read Wikipedia articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Article title or search term"},
                    "action": {"type": "string", "description": "summary or search (default summary)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get current weather and 3-day forecast for any location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stock_crypto",
            "description": "Get real-time stock or cryptocurrency prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker e.g. AAPL, BTC-USD, ETH-USD"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": "Generate a chart image from data (bar, line, pie, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Chart type: bar, line, pie, doughnut, radar, or scatter (default bar)"},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "X-axis labels"},
                    "datasets": {"type": "array", "description": "Data sets [{label, data}]"},
                    "title": {"type": "string", "description": "Chart title"},
                },
                "required": ["labels", "datasets"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "visualize",
            "description": "Generate an SVG diagram inline (flowchart, architecture, mindmap, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What to visualize"},
                    "type": {"type": "string", "description": "Diagram type or auto (default auto)"},
                },
                "required": ["description"],
            },
        },
    },
]

TOOL_NAMES = [t["function"]["name"] for t in GUEST_TOOLS]
