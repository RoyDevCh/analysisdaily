"""命令行入口。

用法：
  python -m analysisdaily.cli --fixture data/e2e_sample
  python -m analysisdaily.cli --run --date 2026-09-02
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from ..config import get_settings
from ..ingestion.collect import collect_articles
from ..ingestion.fixture import load_fixture_dir
from ..orchestration.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="analysisdaily")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="从公开数据源实时摄取并运行管道")
    mode.add_argument("--fixture", metavar="DIR", help="从样本夹具目录运行管道（离线可复现）")
    p.add_argument("--date", default=None, help="日报日期 YYYY-MM-DD（默认取文章最新日期）")
    p.add_argument("--out", default=None, help="输出目录（默认 data/reports）")
    args = p.parse_args(argv)

    settings = get_settings()
    report_date: date | None = None
    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()  # noqa: DTZ007

    if args.fixture:
        articles = load_fixture_dir(Path(args.fixture))
        print(f"[ingest] loaded {len(articles)} fixture articles from {args.fixture}")
    else:
        articles = collect_articles(settings)
        print(f"[ingest] collected {len(articles)} live articles")

    reports = run_pipeline(
        articles,
        settings,
        report_date=report_date,
        out_dir=Path(args.out) if args.out else None,
    )
    print(f"[synthesis] produced {len(reports)} structured report(s)")
    for r in reports:
        print(f"  - {r.event_id} [{r.category}] facts={len(r.verified_facts)}")
    if not reports:
        print("[warn] 无足够证据形成日报（可能为单篇/噪声样本），已按护城河放弃。")
    return 0


if __name__ == "__main__":
    sys.exit(main())