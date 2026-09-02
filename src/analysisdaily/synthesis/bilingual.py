"""英→中 双语：把英文日报翻译成中文版（保留结构、专有名词、数据）。"""
from __future__ import annotations

from ..config import Settings

_SYS = (
    "You are a professional news translator. Translate the ENTIRE following English daily news report into fluent, natural "
    "Simplified Chinese: EVERY sentence, paragraph, heading, and bullet must be translated into Chinese. DO NOT leave any "
    "English prose in the output. Preserve the markdown structure (##/### headings, bullet lists, quotes, numbers). "
    "Keep proper nouns (people, places, organizations) and quoted phrases accurate; use standard Chinese for well-known "
    "terms (e.g. International Politics → 国际政治). Output ONLY the complete Chinese translation, no commentary."
)


def translate_to_zh(settings: Settings, markdown_en: str) -> str:
    if settings.llm_provider not in ("openai", "anthropic", "ollama", "openrouter") or not settings.llm_api_key or not settings.llm_model:
        return markdown_en
    try:
        from ..llm_client import chat_completion

        return chat_completion(
            settings,
            [{"role": "system", "content": _SYS}, {"role": "user", "content": markdown_en}],
            temperature=0.2, max_tokens=8000,
        ).strip()
    except Exception:  # noqa: BLE001
        return markdown_en  # 翻译失败则保留英文版