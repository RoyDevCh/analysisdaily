"""一次事件的事实/偏见分析结果（统一的引擎输出包）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.raw import EventCluster
from ..models.report import BackgroundData, FactStatement, PerspectivesDivergence


@dataclass
class EventPackage:
    cluster: EventCluster
    headline: str
    headline_zh: str = ""
    summary_zh: str = ""
    left_focus_zh: str = ""
    right_focus_zh: str = ""
    blindspot_zh: str = ""
    verified_facts: list[FactStatement] = field(default_factory=list)
    divergence: PerspectivesDivergence = field(default_factory=PerspectivesDivergence)
    background: BackgroundData = field(default_factory=BackgroundData)
    summary: str = ""
    engine: str = "rules"