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