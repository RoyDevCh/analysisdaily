"""管道内部数据模型：来源、原始文章、事件簇。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .report import BiasLabel


class Channel(str, Enum):
    """数据通道：对应三类抓取流的四类实现。"""

    WIRE = "wire"          # 事实底座流（电讯社）
    SPECTRUM = "spectrum"  # 舆论光谱流（左右中对比）
    CONTEXT = "context"    # 宏观背景流（OWID / Pew）
    RESEARCH = "research"  # 研报/智库（并入背景，独立命名便于扩展）


class SourceInfo(BaseModel):
    name: str
    url: str = ""
    channel: Channel = Channel.WIRE
    bias: BiasLabel = BiasLabel.UNKNOWN
    kind: str = "wire"  # wire | analysis | commentary | data
    feed_url: str = ""  # RSS/API 地址
    enabled: bool = True

    @property
    def weight(self) -> float:
        return self.bias.fact_weight


class RawArticle(BaseModel):
    id: str = Field(..., description="全局唯一 id：source_hash + published")
    source_name: str
    channel: Channel = Channel.WIRE
    bias: BiasLabel = BiasLabel.UNKNOWN
    # 偏向分类：left_leaning | right_leaning | center | unknown
    side: str = "unknown"
    title: str
    url: str
    published: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""               # RSS 摘要 / 导语
    content: str = ""               # 抓取正文（可经 Trafilatura 抽取）
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    feed: str = Field(default="", description="来源 feed 分组（用于按主题分离聚类）")

    @field_validator("summary", "content")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        # 剥离 HTML 与实体（RSS 摘要常含标签）
        from ..ingestion.textutils import strip_html

        return strip_html(v) if v else v

    @property
    def text(self) -> str:
        """用于向量化与事实提取的文本（正文优先，回退摘要+标题）。"""
        body = (self.content or self.summary or "").strip()
        if body:
            return f"{self.title}。{body}"
        return self.title

    def dedup_key(self) -> str:
        """去重键：标题小写 + 来源 + 发布时间（到分钟）。"""
        return (
            f"{self.title.strip().lower()}||{self.source_name}||"
            f"{self.published.strftime('%Y%m%d%H%M')}"
        )


class EventCluster(BaseModel):
    """一次"事件"：由多篇同主题文章在滑动时间窗口内聚类而来。"""

    event_cluster_id: str = Field(..., description="如 20260902-tech-antitrust-01")
    date: str = ""                       # YYYYMMDD
    category: str = "未分类"
    articles: list[RawArticle] = Field(default_factory=list)
    # 候选事实文本池（按来源权重排序），供事实引擎使用
    weighted_texts: list[tuple[str, str, float]] = Field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.articles)

    @property
    def center_count(self) -> int:
        return sum(1 for a in self.articles if a.side == "center")

    @property
    def left_count(self) -> int:
        return sum(1 for a in self.articles if a.side == "left_leaning")

    @property
    def right_count(self) -> int:
        return sum(1 for a in self.articles if a.side == "right_leaning")

    @property
    def headline_hint(self) -> str:
        """取权重最高的居中源标题作为 headline 雏形。"""
        best: RawArticle | None = None
        best_w = -1
        for a in self.articles:
            if a.bias.fact_weight > best_w:
                best, best_w = a, a.bias.fact_weight
        return best.title if best else ""