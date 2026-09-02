"""一次事件的事实/偏见分析结果（统一的引擎输出包）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.raw import EventCluster
from ..models.report import BackgroundData, FactStatement, PerspectivesDivergence


@dataclass
class EventPackage:
    cluster: EventCluster
    headline: str
    verified_facts: list[FactStatement] = field(default_factory=list)
    divergence: PerspectivesDivergence = field(default_factory=PerspectivesDivergence)
    background: BackgroundData = field(default_factory=BackgroundData)
    summary: str = ""
    engine: str = "rules"