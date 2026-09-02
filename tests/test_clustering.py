from pathlib import Path

from analysisdaily.clustering.clusterer import HdbscanClusterer
from analysisdaily.clustering.embedder import Embedder
from analysisdaily.config import Settings
from analysisdaily.ingestion.fixture import load_fixture_dir

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"


def test_fixture_forms_multiple_events():
    arts = load_fixture_dir(FIXTURE)
    assert len(arts) >= 10
    settings = Settings(embedding_backend="tfidf")
    embed = Embedder(settings)
    clusterer = HdbscanClusterer(embed, window_hours=24, min_samples=2)
    clusters = clusterer.cluster(arts, "20260902")
    assert len(clusters) >= 2  # 至少两个事件（antitrust / climate）


def test_cluster_has_weighted_texts():
    arts = load_fixture_dir(FIXTURE)
    settings = Settings(embedding_backend="tfidf")
    embed = Embedder(settings)
    clusterer = HdbscanClusterer(embed, window_hours=24, min_samples=2)
    clusters = clusterer.cluster(arts, "20260902")
    top = max(clusters, key=lambda c: c.size)
    assert top.size >= 2
    assert top.weighted_texts  # 候选事实文本池非空
    assert top.headline_hint
