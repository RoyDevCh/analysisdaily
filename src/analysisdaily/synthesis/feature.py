"""跨事件深度报道：把当天多个相关事件串成一篇多段落的叙事（LLM 执笔，规则兜底）。

像记者一样：识别共同线索与深层含义，指出分歧；写成流畅的段落（非列表）。
"""
from __future__ import annotations

from ..config import Settings

_SYSTEM = (
    "You are an experienced news features journalist. Given several related news events from the same day, "
    "write a cohesive feature article of 3-5 paragraphs that connects them into one narrative. "
    "Identify the common threads and broader implications; explicitly note where sources or viewpoints diverge. "
    "Write flowing, neutral, factual prose (NO bullet points, NO markdown headers), in the same language as the "
    "source text (mostly English)."
)


def _chat(settings: Settings, messages: list[dict], max_tokens: int = 1300) -> str:
    from ..llm_client import chat_completion

    return chat_completion(settings, messages, temperature=0.4, max_tokens=max_tokens)


def write_feature(items, settings: Settings) -> str:
    """items: list[DailyItem]。返回英文深度报道正文（中文版由整篇翻译处理）。"""
    if not items:
        return ""
    if settings.llm_provider not in ("openai", "anthropic", "ollama", "openrouter") or not settings.llm_api_key or not settings.llm_model:
        return _rule_feature(items)
    try:
        ctx = "\n\n".join(f"[{it.category}] {it.headline}\n{it.summary[:400]}" for it in items[:8])
        user = (
            f"Today's top news events (headline + summary):\n\n{ctx}\n\n"
            "Write the feature article (3-5 paragraphs) connecting these events into one narrative. Only output the article body."
        )
        return _chat(settings, [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]).strip()
    except Exception:  # noqa: BLE001
        return _rule_feature(items)


def _rule_feature(items) -> str:
    heads = "；".join(it.headline for it in items[:5])
    tip = "（未配置 LLM 或生成失败，此为规则兜底。）"
    return f"(rule fallback) {len(items)} events: {heads}. {tip}"