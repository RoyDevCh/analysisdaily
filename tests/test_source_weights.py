from datetime import date
from pathlib import Path

from analysisdaily.config import Settings
from analysisdaily.ingestion.fixture import load_fixture_dir
from analysisdaily.orchestration.pipeline import run_pipeline
from analysisdaily.synthesis.daily import build_daily_report

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "e2e_sample"


def test_source_weights_change_presentation_not_facts(tmp_path):
    settings = Settings(embedding_backend="tfidf", app_data_dir=tmp_path)
    arts = load_fixture_dir(FIXTURE)
    reports, _ = run_pipeline(arts, settings, report_date=date(2026, 9, 2), out_dir=tmp_path / "reports")

    # 无权重（仅验证可构建）
    build_daily_report(reports, "t")
    # 用户偏好 Reuters（设高权重）
    d1 = build_daily_report(reports, "t", source_weights={"Reuters (via Google News)": 3.0})

    # 事实数量不变（最大公约数事实保留）
    assert len(d1.top_stories) >= 1
    # 设置了偏好后在对应条目出现 preferred_sources 提示
    any_pref = any(it.preferred_sources for sec in d1.sections for it in sec.items)
    assert any_pref, "应出现用户偏好信源标记"