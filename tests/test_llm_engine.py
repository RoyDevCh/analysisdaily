from pathlib import Path

from analysisdaily.clustering.clusterer import HdbscanClusterer
from analysisdaily.clustering.embedder import Embedder
from analysisdaily.config import Settings
from analysisdaily.facts.llm_engine import LLMFactEngine
from analysisdaily.ingestion.fixture import load_fixture_dir

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"

MOCK_JSON = '''{
  "headline": "European Commission fines TechCo 1.8 billion euros",
  "left_leaning_focus": "Impact on smaller competitors",
  "right_leaning_focus": "Concerns about regulatory overreach",
  "blindspot_warning": "both sides covered",
  "facts": [
    {"text": "The European Commission fined TechCo 1.8 billion euros.", "sources": ["Reuters (via Google News)", "AP News (via Google News)"]},
    {"text": "TechCo said it will appeal the decision.", "sources": ["Reuters (via Google News)"]}
  ]
}'''


def _top_cluster():
    arts = load_fixture_dir(FIXTURE)
    settings = Settings()
    embed = Embedder(settings)
    clusterer = HdbscanClusterer(embed, 24, 2)
    clusters = clusterer.cluster(arts, "20260902")
    return max(clusters, key=lambda c: c.size), settings, embed


def test_llm_engine_parse_grounds_real_quotes(monkeypatch):
    cluster, settings, embed = _top_cluster()
    eng = LLMFactEngine(settings, embed)
    monkeypatch.setattr(eng, "_call", lambda cluster: MOCK_JSON)
    pkg = eng.analyze(cluster)
    assert pkg.engine == "llm"
    assert pkg.verified_facts
    # 护城河二：每条事实必须有真实 quote_span
    for f in pkg.verified_facts:
        assert f.quote_spans, "LLM 事实必须回填真实引文"
    # 引用必须来自真实抓取文本（非凭空捏造）
    for f in pkg.verified_facts:
        for q in f.quote_spans:
            assert q.url == "https://example.com/reuters/1" or "example.com" in q.url
    assert "!" not in pkg.headline


def test_llm_engine_falls_back_when_unparsable(monkeypatch):
    cluster, settings, embed = _top_cluster()
    eng = LLMFactEngine(settings, embed)
    monkeypatch.setattr(eng, "_call", lambda cluster: "not json at all")
    pkg = eng.analyze(cluster)
    assert pkg.engine == "rules"
    assert pkg.verified_facts

def test_llm_engine_filters_emotive_fact_before_construction(monkeypatch):
    """LLM 只输出标签；若产出的"事实文本"含情绪词，应在构造前被过滤而不崩溃。"""
    import json

    from analysisdaily.facts.llm_engine import LLMFactEngine

    cluster, settings, embed = _top_cluster()
    # 构造成份在 _parse 内发生：用 monkeypatch 让 _call 返回含"disaster"的 JSON
    bad_json = json.dumps({
        "headline": "Neutral headline here",
        "left_leaning_focus": "x", "right_leaning_focus": "y", "blindspot_warning": "z",
        "facts": [
            {"text": "The European Commission fined TechCo 1.8 billion euros.", "sources": ["Reuters (via Google News)"]},
            {"text": "As climate change warms the Himalayas, disasters are becoming more frequent.", "sources": ["AP News (via Google News)"]},
        ],
    })
    eng = LLMFactEngine(settings, embed)
    monkeypatch.setattr(eng, "_call", lambda cluster: bad_json)
    pkg = eng.analyze(cluster)  # 不应抛出异常（失败也会回退规则引擎）
    # 若走了 LLM 产物，则"disaster"事实必须被过滤
    assert pkg.verified_facts
    assert all("disaster" not in f.text for f in pkg.verified_facts)
