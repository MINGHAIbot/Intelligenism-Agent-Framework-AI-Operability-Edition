"""
通用互联网搜索工具 - 为 agent 提供实时 web 搜索能力

搜索通道（按 config.json 中配置的 provider 自动选择）：
  - Brave:   Brave Search API → 返回搜索��果摘要（需配置 services.brave_search）
  - Grok:    xAI API 原生实时知识
  - ChatGPT: OpenAI Responses API + web_search_preview
  - Claude:  Anthropic Messages API + web_search 工具

agent 认为需要搜索互联网或用户明确要求时，调用 web_search 工具即可。
"""
import json
import os
import requests


def _load_config():
    """加载 config.json"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config.json")
    config_path = os.path.normpath(config_path)
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 搜索实现：各通道
# ---------------------------------------------------------------------------

def _search_via_brave(question, config):
    """Brave Search API → 返回搜索结果摘要文本"""
    brave_cfg = config.get("services", {}).get("brave_search", {})
    brave_key = brave_cfg.get("api_key", "")
    brave_url = brave_cfg.get("url", "https://api.search.brave.com/res/v1/web/search")
    if not brave_key or brave_key.startswith("YOUR_"):
        return None  # 未配置，跳过

    resp = requests.get(
        brave_url,
        headers={"X-Subscription-Token": brave_key, "Accept": "application/json"},
        params={"q": question, "count": 10},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("web", {}).get("results", [])[:10]:
        title = item.get("title", "")
        url = item.get("url", "")
        desc = item.get("description", "")
        results.append(f"[{title}]({url})\n{desc}")

    if not results:
        return "No results found."
    return "\n\n".join(results)


def _search_via_grok(question, config):
    """xAI Grok API 搜索"""
    p = config.get("providers", {}).get("xai", {})
    api_key = p.get("api_key", "")
    if not api_key or api_key.startswith("YOUR_"):
        return None

    resp = requests.post(
        p.get("url", "https://api.x.ai/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": p.get("model", "grok-4-1-fast-non-reasoning"),
            "max_tokens": p.get("max_tokens", 4096),
            "messages": [{"role": "user", "content": question}]
        },
        timeout=60
    )
    resp.raise_for_status()
    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")


def _search_via_chatgpt(question, config):
    """OpenAI Responses API + web_search_preview"""
    p = config.get("providers", {}).get("openai", {})
    api_key = p.get("api_key", "")
    if not api_key or api_key.startswith("YOUR_"):
        return None

    resp = requests.post(
        p.get("url", "https://api.openai.com/v1/responses"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": p.get("model", "gpt-5.4-mini"),
            "max_output_tokens": p.get("max_tokens", 4096),
            "tools": [{"type": "web_search_preview"}],
            "input": question
        },
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()

    content = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    content += c.get("text", "")
    return content or None


def _search_via_claude(question, config):
    """Anthropic Messages API + web_search 工具"""
    p = config.get("providers", {}).get("anthropic", {})
    api_key = p.get("api_key", "")
    if not api_key or api_key.startswith("YOUR_"):
        return None

    resp = requests.post(
        p.get("url", "https://api.anthropic.com/v1/messages"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        json={
            "model": p.get("model", "claude-haiku-4-5-20251001"),
            "max_tokens": p.get("max_tokens", 4096),
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            "messages": [{"role": "user", "content": question}]
        },
        timeout=90
    )
    resp.raise_for_status()
    data = resp.json()

    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")
    return content or None


# ---------------------------------------------------------------------------
# 搜索通道优先级（按成本从低到高）
# ---------------------------------------------------------------------------
_SEARCH_CHANNELS = [
    ("brave",   _search_via_brave),
    ("grok",    _search_via_grok),
    ("chatgpt", _search_via_chatgpt),
    ("claude",  _search_via_claude),
]


def _web_search(args):
    """
    通用互联网搜索。自动选择可用的搜索通道（优先 Brave，其次 Grok/ChatGPT/Claude）。
    返回纯文本搜索结果摘要，适合 agent 在对话中直接使用。
    """
    question = args.get("question", "")
    if not question:
        return "Error: question parameter is required"

    config = _load_config()
    if not config:
        return "Error: config.json not found"

    # 按优先级尝试各��道
    errors = []
    for name, fn in _SEARCH_CHANNELS:
        try:
            result = fn(question, config)
            if result:
                return result[:8000]
        except Exception as e:
            errors.append(f"{name}: {str(e)[:100]}")
            continue

    if errors:
        return f"Error: all search channels failed:\n" + "\n".join(errors)
    return "Error: no search channel configured. Please set up API keys in config.json"


# === TOOLS 导出 ===
TOOLS = {
    "web_search": {
        "description": "搜索互联网获取实时信息。当需要查找最新资讯、技术文档、产品信息或任何需要联网才能回答的问题时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要搜索的问题或关键词"
                }
            },
            "required": ["question"]
        },
        "handler": _web_search
    }
}
