"""左右翼叙事分歧与盲区分析。

需求"3. 叙事分歧 / 盲区计算"：
- left_leaning_focus / right_leaning_focus：归纳该侧侧重角度（由该侧独有高频词表述）；
- blindspot_warning：一侧大面积回避（例如右翼报道占比 > 80% 且左翼几乎缺席）。
"""
from __future__ import annotations

import re
from collections import Counter

from ..models.raw import EventCluster
from ..models.report import PerspectivesDivergence

STOP = {"the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for", "with", "as", "by", "from", "into", "over", "before", "after", "amid", "is", "are", "was", "were", "be", "been", "being", "will", "would", "should", "can", "could", "may", "might", "has", "have", "had", "new", "says", "said", "report", "reports", "news", "today", "year", "years", "day", "days", "week", "weeks", "more", "most", "also", "their", "its", "this", "that", "these", "those", "it", "he", "she", "they", "we", "you", "i", "not", "no", "yes"}


def _top_terms(texts: list[str], n: int = 8) -> list[str]:
    c: Counter = Counter()
    for t in texts:
        for w in re.findall(r"[\w\u4e00-\u9fff]{3,}", t.lower()):
            if w in STOP or len(w) < 3:
                continue
            c[w] += 1
    return [w for w, _ in c.most_common(n)]


def analyze_divergence(cluster: EventCluster) -> PerspectivesDivergence:
    left_texts = [a.text for a in cluster.articles if a.side == "left_leaning"]
    right_texts = [a.text for a in cluster.articles if a.side == "right_leaning"]
    center_texts = [a.text for a in cluster.articles if a.side == "center"]

    left_terms = set(_top_terms(left_texts, 10)) if left_texts else set()
    right_terms = set(_top_terms(right_texts, 10)) if right_texts else set()
    left_distinct = [w for w in left_terms if w not in right_terms]
    right_distinct = [w for w in right_terms if w not in left_terms]

    left_focus = (
        "左翼侧重：" + _phrase(left_distinct) if left_texts
        else "左翼媒体基本未报道该事件。"
    )
    right_focus = (
        "右翼侧重：" + _phrase(right_distinct) if right_texts
        else "右翼媒体基本未报道该事件。"
    )

    # 盲区计算（限定在有偏见的报道范围内计算比例）
    bias_total = len(left_texts) + len(right_texts)
    if bias_total >= 3:
        right_share = len(right_texts) / bias_total
        left_share = len(left_texts) / bias_total
        if right_share >= 0.8 and len(left_texts) == 0:
            warning = f"盲区提示：该事件 {right_share:.0%} 由右翼媒体覆盖，左翼近乎零报道（可能被回避）。"
        elif left_share >= 0.8 and len(right_texts) == 0:
            warning = f"盲区提示：该事件 {left_share:.0%} 由左翼媒体覆盖，右翼近乎零报道（可能被回避）。"
        else:
            warning = f"盲区观察：左翼 {len(left_texts)} 篇 / 右翼 {len(right_texts)} 篇，双方均有报道，未见明显单侧回避。"
    else:
        warning = "样本过少，暂无法判定单侧回避。"
        if len(left_texts) == 0 and len(right_texts) == 0:
            warning = "（无偏见源覆盖，以居中源为主，未见光谱分歧。）"

    return PerspectivesDivergence(
        left_leaning_focus=left_focus,
        right_leaning_focus=right_focus,
        blindspot_warning=warning,
        left_coverage=len(left_texts),
        right_coverage=len(right_texts),
        center_coverage=len(center_texts),
    )


def _phrase(terms: list[str]) -> str:
    if not terms:
        return "未见明显特有框架。"
    return "强调 " + "、".join(terms[:5]) + " 等角度。"