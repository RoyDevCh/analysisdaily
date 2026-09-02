"""文本清理：剥离 HTML 标签与 HTML 实体，提取纯文本。"""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")

# 常见 HTML 实体（&nbsp; &#8230; &amp; &quot; 等）
_ENTITY = re.compile(r"&[a-zA-Z#0-9]{2,8};")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = _TAG.sub(" ", text)
    text = _ENTITY.sub(" ", text)
    text = html.unescape(text)
    from ..facts.subjectivity import split_sentences

    return " ".join(split_sentences(text)).strip()
