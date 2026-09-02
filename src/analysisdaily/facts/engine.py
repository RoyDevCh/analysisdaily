"""事实/偏见引擎：总体门面 + 规则引擎 + LLM 引擎选择工厂。

规则引擎（默认，离线确定性）：最大公约数事实 + 左右翼分歧/盲区 + 情绪剥离。
LLM 引擎（`LLM_PROVIDER` 非 none 时启用）：OpenAI 兼容（含 Ollama Cloud），
失败时自动回退规则引擎。
"""
from __future__ import annotations

import re

from ..clustering.embedder import Embedder
from ..config import Settings
from ..models.raw import EventCluster
from ..models.report import BackgroundData, FactStatement
from .divergence import analyze_divergence
from .extractor import extract_facts
from .package import EventPackage
from .subjectivity import EMOTIVE_WORDS, strip_emotive


class RulesFactEngine:
    name = "rules"

    def __init__(self, settings: Settings, embedder: Embedder):
        self.settings = settings
        self.embedder = embedder

    def analyze(self, cluster: EventCluster) -> EventPackage:
        facts = extract_facts(cluster, self.embedder)
        div = analyze_divergence(cluster)
        return EventPackage(
            cluster=cluster,
            headline=self._headline(cluster, facts),
            verified_facts=facts,
            divergence=div,
            background=BackgroundData(source=self._context_source(cluster), key_stat="", url=""),
            summary=self._summary(cluster),
            engine=self.name,
        )

    def _headline(self, cluster: EventCluster, facts: list[FactStatement]) -> str:
        hint = cluster.headline_hint
        hint_clean = strip_emotive(hint)
        for w in EMOTIVE_WORDS:
            hint_clean = re.sub(re.escape(w), "", hint_clean, flags=re.IGNORECASE)
        hint_clean = re.sub(r"\s+", " ", hint_clean).strip().rstrip("!?")
        if len(hint_clean) >= 8 and "!" not in hint_clean:
            return hint_clean[:120]
        if facts:
            f0 = strip_emotive(facts[0].text).rstrip("!?")
            return f0[:120]
        return cluster.headline_hint[:120]

    def _summary(self, cluster: EventCluster) -> str:
        """规则兜底综述：取权重最高来源的正文章节作为内容。"""
        for a in sorted(cluster.articles, key=lambda x: x.bias.fact_weight, reverse=True):
            body = (a.content or a.summary or "").strip()
            if len(body) >= 60:
                return body[:600]
        return cluster.headline_hint

    def _context_source(self, cluster: EventCluster) -> str:
        for a in cluster.articles:
            if a.channel.value in ("context", "research"):
                return a.source_name
        return ""


def get_fact_engine(settings: Settings, embedder: Embedder):
    from .llm_engine import LLMFactEngine

    if settings.llm_provider in ("openai", "anthropic", "ollama"):
        return LLMFactEngine(settings, embedder)
    return RulesFactEngine(settings, embedder)