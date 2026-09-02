from datetime import date
from pathlib import Path

from analysisdaily.config import Settings
from analysisdaily.ingestion.fixture import load_fixture_dir
from analysisdaily.orchestration.pipeline import run_pipeline

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"


def test_end_to_end_pipeline(tmp_path):
    settings = Settings(embedding_backend="tfidf", app_data_dir=tmp_path)
    arts = load_fixture_dir(FIXTURE)
    reports, _ = run_pipeline(arts, settings, report_date=date(2026, 9, 2), out_dir=tmp_path / "reports")
    assert reports, "应产出至少一条日报"
    for r in reports:
        assert r.verified_facts, "每条日报必须有核验事实"
        assert "!" not in r.headline, "headline 禁止感叹号"
        assert (tmp_path / "reports" / f"{r.event_id}.json").exists()
        assert (tmp_path / "reports" / f"{r.event_id}.md").exists()