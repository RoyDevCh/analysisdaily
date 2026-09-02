"""情绪/主观剥离（Subjectivity Stripping）。

规则化：
- 识别并剔除煽动性形容词/副词与无实据猜测性句子；
- 仅保留"主谓宾"式的客观事实陈述；
- 供事实提取使用；同时被 synthesis 用于 headline/fact 硬校验兜底。
"""
from __future__ import annotations

import re

# 煽动/评价性形容词、副词（含常见变体）
EMOTIVE_WORDS = {
    "shocking", "shock", "outrageous", "outrage", "terrible", "awful", "amazing",
    "horrific", "horrifying", "stunning", "devastating", "devastated", "unbelievable",
    "insane", "dramatic", "explosive", "vicious", "disgusting", "tragic", "appalling",
    "incredible", "alarming", "desperate", "chaotic", "unhinged", "bonkers", "wild",
    "furious", "hapless", "shameful", "sickening", "breathtaking", "frightening",
    "terrifying", "astonishing", "scandalous", "criminal", "biased", "fake", "hoax",
    "radical", "extremist", "fringe", "smear", "witch hunt", "deep state", "sneaky",
    "sneak", "lurid", "fantastic", "brilliant", "heroic", "evil", "corrupt", "messy",
    "historic", "landmark",
}

# 无实据/推测性标记（出现即倾向剔除）
SPECULATIVE_MARKERS = {
    "reportedly", "allegedly", "appears to", "seem to", "seems to", "might",
    "may have", "could have", "possibly", "perhaps", "rumored", "rumored to",
    "is said to", "suggests", "suggesting", "likely", "apparently", "unclear if",
    "vowed to", "threatened to", "I think", "we believe", "in my view", "experts say",
}


def split_sentences(text: str) -> list[str]:
    """英文/中文句子切分。统一中英文标点为英文句末标点 + 空格后切分。"""
    text = re.sub(r"\s+", " ", text or "")
    text = text.replace("。", ". ").replace("！", "! ").replace("？", "? ").replace("。", ". ")
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip() and not p.isspace()]


def is_emotive(sentence: str) -> bool:
    low = sentence.lower()
    for w in EMOTIVE_WORDS:
        if w in low:
            return True
    return False


def is_speculative(sentence: str) -> bool:
    low = sentence.lower()
    for m in SPECULATIVE_MARKERS:
        if m in low:
            return True
    return False


def strip_emotive(text: str) -> str:
    """删除包含情绪词的句子；保留客观句。"""
    kept = []
    for s in split_sentences(text):
        if is_emotive(s) or is_speculative(s):
            continue
        kept.append(s)
    return " ".join(kept)


def is_factual(sentence: str) -> bool:
    """是否可作为客观事实句：无情绪、无推测、有一定长度且含实体锚点。"""
    if len(sentence) < 20:
        return False
    if is_emotive(sentence) or is_speculative(sentence):
        return False
    # 需要锚点：数字 / 日期 / 大写词（人名、组织、地名）
    has_anchor = bool(
        re.search(r"\d", sentence)
        or re.search(r"[A-Z][a-z]+", sentence)
        or re.search(r"\d{4}", sentence)
    )
    return has_anchor
