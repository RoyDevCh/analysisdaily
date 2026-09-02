from datetime import date
from pathlib import Path

from analysisdaily.clustering.embedder import Embedder
from analysisdaily.config import Settings
from analysisdaily.ingestion.fixture import load_fixture_dir
from analysisdaily.orchestration.pipeline import run_pipeline
from analysisdaily.tracking.threads import render_tracking, update_threads

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"


def test_events_tracked_across_days(tmp_path):
    settings = Settings(embedding_backend="tfidf", app_data_dir=tmp_path)
    arts = load_fixture_dir(FIXTURE)
    embed = Embedder(settings)
    reports, _ = run_pipeline(arts, settings, report_date=date(2026, 9, 2), out_dir=tmp_path / "reports")

    # 第 1 天：每条事件 = 新线程
    threads = update_threads(embed, reports, [], "20260902")
    assert len(threads) == len(reports)

    # 第 2 天：同一事件应匹配到已有线程，追加一天快照（线程数不变、各 2 天）
    threads2 = update_threads(embed, reports, threads, "20260903")
    assert len(threads2) == len(reports)
    assert all(len(t.events) == 2 for t in threads2)

    timeline = render_tracking(threads2)
    assert any("2 天" in line for line in timeline)
