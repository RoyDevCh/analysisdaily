"""英→中 双语：把英文日报翻译成中文版（保留结构、专有名词、数据）。"""
from __future__ import annotations

import json

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

_PER_ITEM_SYS = (
    "You are a professional news translator. Translate this event's fields into fluent Simplified Chinese. "
    "Output STRICT JSON only: {\"headline_zh\": str, \"summary_zh\": str, \"left_zh\": str, \"right_zh\": str, \"blindspot_zh\": str}. "
    "Keep proper nouns (people, places, organizations), numbers, and quoted phrases as-is; translate the rest into Chinese."
)


def _key(settings: Settings) -> str:
    return settings.openrouter_api_key or settings.llm_api_key


_BATCH_SYS = (
    "You are a professional news translator. Translate each item's fields into fluent Simplified Chinese. "
    "Output STRICT JSON: a JSON array [{\"i\": int, \"headline_zh\": str, \"summary_zh\": str, "
    "\"left_zh\": str, \"right_zh\": str, \"blindspot_zh\": str}, ...], one entry per input item, using the same \"i\". "
    "Keep proper nouns, numbers, and quoted phrases as-is; translate the rest into Chinese."
)


def localize_zh(reports, settings: Settings, batch: int = 5) -> None:
    """逐项翻译（批量）：每条报告的 headline/summary/left/right/blindspot 译为中文，写入报表中文字段。

    批量（每批 5 条）兼顾可靠性与速度。
    """
    if settings.llm_provider not in ("openai", "anthropic", "ollama", "openrouter") or not _key(settings):
        return
    from ..llm_client import chat_completion

    for start in range(0, len(reports), batch):
        chunk = reports[start:start + batch]
        try:
            src_items = [
                {"i": start + k,
                 "headline": r.headline, "summary": (r.summary or "")[:450],
                 "left": r.perspectives_divergence.left_leaning_focus,
                 "right": r.perspectives_divergence.right_leaning_focus,
                 "blindspot": r.perspectives_divergence.blindspot_warning}
                for k, r in enumerate(chunk)
            ]
            out = chat_completion(settings,
                [{"role": "system", "content": _BATCH_SYS}, {"role": "user", "content": json.dumps(src_items, ensure_ascii=False)}],
                temperature=0.2, max_tokens=1600)
            results = {int(x.get("i", -1)): x for x in json.loads(out)}
            for k, r in enumerate(chunk):
                obj = results.get(start + k)
                if not obj:
                    continue
                r.headline_zh = str(obj.get("headline_zh", "")).strip()
                r.summary_zh = str(obj.get("summary_zh", "")).strip()
                r.left_focus_zh = str(obj.get("left_zh", "")).strip()
                r.right_focus_zh = str(obj.get("right_zh", "")).strip()
                r.blindspot_zh = str(obj.get("blindspot_zh", "")).strip()
        except Exception:  # noqa: BLE001, S112
            continue


def translate_feature_zh(feature_en: str, settings: Settings) -> str:
    """把英文深度报道译成中文（单段长文，隔离翻译更可靠）。"""
    if not feature_en:
        return ""
    if settings.llm_provider not in ("openai", "anthropic", "ollama", "openrouter") or not _key(settings):
        return feature_en
    try:
        from ..llm_client import chat_completion

        return chat_completion(settings,
            [{"role": "system", "content": _SYS}, {"role": "user", "content": feature_en}],
            temperature=0.2, max_tokens=3000).strip()
    except Exception:  # noqa: BLE001
        return feature_en