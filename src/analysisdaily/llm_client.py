"""统一 LLM 客户端：OpenRouter / OpenAI / Anthropic 兼容，429/5xx 自动重试。

各引擎（事实、深度报道、正文翻译）统一走这里，保证 429 限流不中断整批。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .config import Settings


def _resolve(settings: Settings) -> tuple[str, str, list[str]]:
    """返回 (base_url, api_key, models)。支持 openrouter 专用 key + 多模型回退。"""
    if settings.llm_provider == "openrouter":
        key = settings.openrouter_api_key or settings.llm_api_key
        raws = (settings.llm_models or "").split(",")
        models = [m.strip() for m in raws if m.strip()] or [settings.llm_model]
        return "https://openrouter.ai/api/v1", key, models
    base = settings.llm_base_url.rstrip("/") or "https://openrouter.ai/api/v1"
    return base, settings.llm_api_key, [settings.llm_model]


def _post(url: str, key: str, payload: dict):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def chat_completion(settings: Settings, messages: list[dict], temperature: float = 0.1, max_tokens: int = 900) -> str:
    base, key, models = _resolve(settings)
    if not key or not models:
        raise ValueError("LLM 未配置（缺 api_key/model）")
    last = None
    # 多轮 pass × 多模型 × 多次重试，把瞬时 429（上游限流）彻底扛过去
    for _pass in range(3):
        for model in models:
            body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            url = base + "/chat/completions"
            for attempt in range(4):
                try:
                    data = _post(url, key, body)
                    return data["choices"][0]["message"]["content"]
                except urllib.error.HTTPError as e:
                    last = e
                    if e.code in (429, 500, 502, 503) and attempt < 3:
                        time.sleep(min(2 * (attempt + 1), 6))
                        continue
                    break  # 该模型耗尽 -> 换下一个模型
                except Exception:  # noqa: BLE001
                    if attempt < 3:
                        time.sleep(min(2 * (attempt + 1), 6))
                        continue
                    break
        if last is not None and _pass < 2:
            time.sleep(3)  # 一轮全失败，稍等再整轮重试
    raise last