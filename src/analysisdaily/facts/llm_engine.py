"""LLM 事实引擎（OpenAI 兼容，接 Ollama Cloud gemma4:31b）。

防幻觉边界：
- 严格 JSON 提示，禁止开放式生成；temperature=0.1；
- 仅让模型输出"事实文本 + 来源名"，**证据 quote_span 由真实抓取文本回填**，
  杜绝模型捏造引文；
- 任一环节失败/解析失败 → 回退规则引擎（engine=rules）。
"""
from __future__ import annotations

import json
import re
import urllib.request

from ..clustering.embedder import Embedder
from ..config import Settings
from ..models.raw import EventCluster
from ..models.report import BackgroundData, FactStatement, QuoteSpan
from .package import EventPackage
from .subjectivity import is_clean_fact, is_factual, split_sentences

_SYSTEM = (
    "You are a neutral fact-checking editor. Given several news articles about the SAME event, "
    "extract ONLY verified, objective facts that appear in the sources. Rules: "
    "1) Output STRICT JSON only, no markdown, no commentary. "
    "2) Facts must be plain subject-verb-object statements, no adjectives, no opinion, no exclamation. "
    "3) source field values MUST be chosen from the provided source names verbatim. "
    "    category MUST be one of: 国际政治, 经济与市场, 科技与AI, 气候与环境, 安全与冲突, 社会与公共政策, 文化体育. "
    "4) Write in the SAME language as the source text (mostly English). "
    "JSON schema: {\"category\": str, \"headline\": str, \"left_leaning_focus\": str, \"right_leaning_focus\": str, "
    "\"blindspot_warning\": str, \"facts\": [{\"text\": str, \"sources\": [str]}]}"
)


class LLMFactEngine:
    name = "llm"

    def __init__(self, settings: Settings, embedder: Embedder | None = None):
        self.settings = settings
        self.embedder = embedder

    def analyze(self, cluster: EventCluster) -> EventPackage:
        """返回 EventPackage；失败时回退规则引擎结果。"""
        fallback = self._fallback(cluster)
        try:
            raw = self._call(cluster)
            parsed = self._parse(raw, cluster)
            return parsed if parsed is not None else fallback
        except Exception:  # noqa: BLE001
            return fallback

    def _fallback(self, cluster: EventCluster) -> dict:
        from .engine import RulesFactEngine

        if self.embedder is None:
            raise ValueError("no embedder for fallback")
        return RulesFactEngine(self.settings, self.embedder).analyze(cluster)

    def _call(self, cluster: EventCluster) -> str:
        lines = []
        for a in cluster.articles[:8]:
            body = (a.content or a.summary or "").strip()[:700]
            lines.append(f"[{a.source_name}] (bias={a.side}) {a.title}\n{body}")
        context = "\n\n".join(lines)
        user = (
            f"Here are {len(cluster.articles)} articles about one event. Each is labeled [source_name] (bias=side).\n\n{context}\n\n"
            "Return the strict JSON according to the system schema. Max 5 facts."
        )
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ]
        payload = json.dumps({
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 900,
        }).encode("utf-8")
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.settings.llm_api_key},
        )
        with urllib.request.urlopen(req, timeout=self.settings.llm_timeout) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"]

    def _parse(self, raw: str, cluster: EventCluster) -> dict | None:
        obj = self._extract_json(raw)
        if not isinstance(obj, dict) or "facts" not in obj:
            return None
        src_quote = self._source_quotes(cluster)
        facts: list[FactStatement] = []
        for f in obj["facts"][:5]:
            text = str(f.get("text", "")).strip()
            if len(text) < 20 or not is_clean_fact(text):
                continue
            sources = [str(s) for s in f.get("sources", [])]
            spans, used = [], set()
            for s in sources:
                q = src_quote.get(s)
                if q and s not in used:
                    spans.append(QuoteSpan(source_name=s, url=q[0], quote=q[1], bias=q[2]))
                    used.add(s)
                if len(spans) >= 2:
                    break
            if not spans:
                continue  # 无真实证据 → 丢弃（护城河二）
            common = len(used) >= 2
            facts.append(
                FactStatement(
                    text=text,
                    quote_spans=spans,
                    confidence=0.8 if common else 0.5,
                    single_source_claim=not common,
                )
            )
        if not facts:
            return None
        cat = str(obj.get("category", "")).strip()
        if cat:
            cluster.category = cat
        headline = str(obj.get("headline", "")).strip().rstrip("!?")
        if not headline or "!" in headline:
            headline = cluster.headline_hint.rstrip("!?")
        from .divergence import analyze_divergence

        div = analyze_divergence(cluster)
        div.left_leaning_focus = str(obj.get("left_leaning_focus", "")).strip() or div.left_leaning_focus
        div.right_leaning_focus = str(obj.get("right_leaning_focus", "")).strip() or div.right_leaning_focus
        div.blindspot_warning = str(obj.get("blindspot_warning", "")).strip() or div.blindspot_warning
        return EventPackage(
            cluster=cluster,
            headline=headline,
            verified_facts=facts,
            divergence=div,
            background=BackgroundData(source=self._context_source(cluster), key_stat="", url=""),
            engine=self.name,
        )

    def _source_quotes(self, cluster: EventCluster) -> dict:
        """source_name -> (url, 真实事实句, bias)。证据全部来自真实抓取文本。"""
        out: dict = {}
        for a in cluster.articles:
            if a.source_name in out:
                continue
            for s in split_sentences(a.content or a.summary or a.text):
                if is_factual(s):
                    out[a.source_name] = (a.url, s[:400], a.bias)
                    break
        return out

    @staticmethod
    def _extract_json(text: str):
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\s*", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:  # noqa: BLE001
                    return None
            return None

    @staticmethod
    def _context_source(cluster: EventCluster) -> str:
        for a in cluster.articles:
            if a.channel.value in ("context", "research"):
                return a.source_name
        return ""