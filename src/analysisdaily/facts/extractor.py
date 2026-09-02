"""最大公约数事实提取（Common Denominator Facts）。

护城河二 + 需求"3. 事实交叉核验"：
- 只把"多个来源共同承认"的事实作为核心事实；
- 单一（偏）来源声称 → 标注 single_source_claim=True；
- 每条事实携带原文 QuoteSpan 作为证据。

分组信号：余弦相似度（>= SIM_THRESHOLD）**或**共享关键锚点（数字/专有名词）
——同一事件的跨源报道措辞不同，但共享数字/实体锚点，故两者结合可稳健
识别"同一事实的多种表述"。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from ..clustering.embedder import Embedder
from ..models.raw import EventCluster
from ..models.report import BiasLabel, FactStatement, QuoteSpan
from .subjectivity import is_clean_fact, is_factual, split_sentences

SIM_THRESHOLD = 0.30

_NUMBER_RE = re.compile(r"(?<![A-Za-z])[\d]+(?:[.,]\d+)?(?:\s?(?:billion|million|percent|%|bn|mln))?", re.IGNORECASE)
_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2}\b")


@dataclass
class _Sent:
    text: str
    source_name: str
    url: str
    weight: float
    side: str
    bias: BiasLabel


def _anchors(text: str) -> set[str]:
    a: set[str] = set()
    for m in _NUMBER_RE.findall(text):
        a.add(m.lower().replace(" ", ""))
    for e in _ENTITY_RE.findall(text):
        a.add(e.lower())
    return a


def _gather_sentences(cluster: EventCluster) -> list[_Sent]:
    out: list[_Sent] = []
    for a in cluster.articles:
        for s in split_sentences(a.text):
            if is_factual(s):
                out.append(_Sent(s, a.source_name, a.url, a.bias.fact_weight, a.side, a.bias))
    return out


def _group(sents: list[_Sent], vecs: np.ndarray) -> list[list[int]]:
    """相似 OR 锚点一致 → 归入同一事实族。"""
    n = len(sents)
    sim = vecs @ vecs.T
    anchors = [_anchors(s.text) for s in sents]
    groups: list[list[int]] = []
    used = [False] * n
    for i in range(n):
        if used[i]:
            continue
        members = [i]
        for j in range(i + 1, n):
            if used[j]:
                continue
            share_anchor = bool(anchors[i] & anchors[j])
            if sim[i, j] >= SIM_THRESHOLD or share_anchor:
                members.append(j)
        for m in members:
            used[m] = True
        groups.append(members)
    return groups


def extract_facts(cluster: EventCluster, embedder: Embedder, max_facts: int = 5) -> list[FactStatement]:
    sents = _gather_sentences(cluster)
    if not sents:
        return []
    vecs = embedder.encode([s.text for s in sents])
    groups = _group(sents, vecs)

    facts: list[FactStatement] = []
    for members in groups:
        if len(members) < 1:
            continue
        group = [sents[i] for i in members]
        distinct_sources = {s.source_name for s in group}
        common = len(distinct_sources) >= 2
        support = sum(s.weight for s in group)
        rep = max(group, key=lambda s: (s.weight, len(s.text)))
        spans: list[QuoteSpan] = []
        seen_src = set()
        for s in sorted(group, key=lambda s: s.weight, reverse=True):
            if s.source_name in seen_src:
                continue
            seen_src.add(s.source_name)
            spans.append(
                QuoteSpan(
                    source_name=s.source_name,
                    url=s.url,
                    quote=s.text[:400],
                    bias=s.bias,
                )
            )
            if len(spans) >= 2:
                break
        if not spans or not is_clean_fact(rep.text):
            continue
        diversity = min(len(distinct_sources), 5) / 5
        conf = min(1.0, (support / max(1.0, len(distinct_sources))) * 0.5 + diversity * 0.5)
        facts.append(
            FactStatement(
                text=rep.text,
                quote_spans=spans,
                confidence=round(conf, 2),
                single_source_claim=not common,
            )
        )

    facts.sort(key=lambda f: (not f.single_source_claim, f.confidence, len(f.quote_spans)), reverse=True)
    return facts[:max_facts]