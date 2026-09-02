from pathlib import Path

from analysisdaily.clustering.clusterer import HdbscanClusterer
from analysisdaily.clustering.embedder import Embedder
from analysisdaily.config import Settings
from analysisdaily.facts.divergence import analyze_divergence
from analysisdaily.facts.engine import RulesFactEngine, get_fact_engine
from analysisdaily.facts.extractor import extract_facts
from analysisdaily.ingestion.fixture import load_fixture_dir

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"


def _top_cluster():
    arts = load_fixture_dir(FIXTURE)
    settings = Settings(embedding_backend="tfidf")
    embed = Embedder(settings)
    clusterer = HdbscanClusterer(embed, window_hours=24, min_samples=2)
    clusters = clusterer.cluster(arts, "20260902")
    return max(clusters, key=lambda c: c.size), settings, embed


def test_extract_facts_have_grounding():
    cluster, _settings, embed = _top_cluster()
    facts = extract_facts(cluster, embed)
    assert facts
    for f in facts:
        assert f.quote_spans, "每条事实必须带引文接地"


def test_common_denominator_detected():
    cluster, _settings, embed = _top_cluster()
    facts = extract_facts(cluster, embed)
    assert any(not f.single_source_claim for f in facts), "应存在多源共有的核心事实"


def test_divergence_and_blindspot():
    cluster, _settings, _embed = _top_cluster()
    div = analyze_divergence(cluster)
    assert div.left_coverage + div.right_coverage + div.center_coverage > 0
    assert div.blindspot_warning


def test_rules_engine_builds_package():
    cluster, settings, embed = _top_cluster()
    eng = get_fact_engine(settings, embed)
    assert isinstance(eng, RulesFactEngine)
    pkg = eng.analyze(cluster)
    assert pkg.verified_facts
    assert pkg.divergence.blindspot_warning
    assert "!" not in pkg.headline