"""结构化日报的严格 Schema（Pydantic v2）。

对应需求"4. 结构化日报生成规范"，并叠加三道防幻觉护城河：
- verified_facts 每一条必须携带 quote_span 原文证据；
- headline 禁止感叹号与情绪形容词（此处做硬校验，配套 SubjectivityStripper）；
- sources 携带 bias 与可信度权重。
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 反情绪词表（与 facts/subjectivity.py 保持一致；此处用于输出硬校验）
_EMOTIVE_WORDS = (
    "shocking", "outrageous", "terrible", "amazing", "horrific", "stunning",
    "devastating", "unbelievable", "insane", "dramatic", "explosive", "vicious",
    "bias", "biased", "fake", "hoax", "scandal", "meltdown", "chaos", "crisis",
    "disaster", "catastrophe", "unprecedented", "staggering", "alarming",
    "smear", "witch hunt", "deep state", "radical", "extremist",
)


class BiasLabel(str, Enum):
    """来源政治倾向标签。center / center-left / center-right 具有最高事实权重。"""

    CENTER = "Center"
    CENTER_LEFT = "Center-Left"
    LEFT = "Left"
    CENTER_RIGHT = "Center-Right"
    RIGHT = "Right"
    UNKNOWN = "Unknown"

    @property
    def fact_weight(self) -> float:
        """事实可信度权重（护城河三）：电讯社/居中源最高，极端源仅用于分歧归纳。"""
        return {
            BiasLabel.CENTER: 1.0,
            BiasLabel.CENTER_LEFT: 0.9,
            BiasLabel.CENTER_RIGHT: 0.9,
            BiasLabel.UNKNOWN: 0.5,
            BiasLabel.LEFT: 0.4,
            BiasLabel.RIGHT: 0.4,
        }[self]

    @property
    def side(self) -> str:
        """用于左右翼分歧分组。"""
        if self in (BiasLabel.LEFT, BiasLabel.CENTER_LEFT):
            return "left_leaning"
        if self in (BiasLabel.RIGHT, BiasLabel.CENTER_RIGHT):
            return "right_leaning"
        return "center"


class QuoteSpan(BaseModel):
    """一条事实的最小可追溯证据：原文引用片段 + 来源。"""

    source_name: str = Field(..., description="来源名称，如 Reuters")
    url: str = Field(..., description="原文 URL")
    quote: str = Field(..., min_length=8, description="抓取到的原文片段")
    bias: BiasLabel = BiasLabel.UNKNOWN


class SourceRef(BaseModel):
    name: str
    url: str
    bias: BiasLabel = BiasLabel.UNKNOWN

    @property
    def weight(self) -> float:
        return self.bias.fact_weight


class FactStatement(BaseModel):
    text: str = Field(..., description="客观事实陈述，仅主谓宾，无情绪修饰")
    quote_spans: list[QuoteSpan] = Field(default_factory=list, min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    single_source_claim: bool = Field(
        default=False, description="仅单一（偏）来源声称，须标注为'单方声称'"
    )

    @field_validator("text")
    @classmethod
    def _clean_fact(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("fact 不能为空")
        if v.endswith(("!", "!")):
            raise ValueError("fact 禁止以感叹号结尾")
        low = v.lower()
        for w in _EMOTIVE_WORDS:
            if w in low:
                raise ValueError(f"fact 含情绪词 '{w}'：{v}")
        return v


class PerspectivesDivergence(BaseModel):
    left_leaning_focus: str = Field(default="")
    right_leaning_focus: str = Field(default="")
    blindspot_warning: str = Field(default="")

    # 结构化盲区数据（可计算得出）
    left_coverage: int = Field(default=0, ge=0)
    right_coverage: int = Field(default=0, ge=0)
    center_coverage: int = Field(default=0, ge=0)

    @property
    def coverage_note(self) -> str:
        return (
            f"事件报道覆盖：中心源 {self.center_coverage} 篇 / "
            f"左翼源 {self.left_coverage} 篇 / 右翼源 {self.right_coverage} 篇"
        )


class BackgroundData(BaseModel):
    source: str = Field(default="", description="如 Our World in Data / Pew Research")
    key_stat: str = Field(default="")
    url: str = Field(default="")


class StructuredReport(BaseModel):
    """单条日报条目 —— 严格输出契约。"""

    event_id: str = Field(..., pattern=r"^\d{8}-[a-z0-9-]+$")
    date: date
    category: str = "未分类"
    headline: str = Field(..., min_length=8)
    headline_zh: str = Field(default="", description="中文标题")
    summary: str = Field(default="", description="LLM 撰写的英文新闻综述（内容主体）")
    summary_zh: str = Field(default="", description="中文新闻综述")
    left_focus_zh: str = Field(default="", description="中文左翼侧重")
    right_focus_zh: str = Field(default="", description="中文右翼侧重")
    blindspot_zh: str = Field(default="", description="中文盲区提示")
    verified_facts: list[FactStatement] = Field(..., min_length=1)
    perspectives_divergence: PerspectivesDivergence = Field(default_factory=PerspectivesDivergence)
    background_data: BackgroundData = Field(default_factory=BackgroundData)
    sources: list[SourceRef] = Field(..., min_length=1)

    # ---- 内部可追溯字段 ----
    event_cluster_id: str = ""
    engine: Literal["rules", "llm"] = "rules"
    generated_at: str = ""
    raw_article_count: int = 0

    @field_validator("headline")
    @classmethod
    def _headline_clean(cls, v: str) -> str:
        v = v.strip()
        if "!" in v or "!" in v:
            raise ValueError("headline 禁止感叹号")
        low = v.lower()
        for w in _EMOTIVE_WORDS:
            if w in low:
                raise ValueError(f"headline 含情绪词 '{w}'：{v}")
        return v

    @model_validator(mode="after")
    def _require_grounding(self) -> StructuredReport:
        # 护城河二：每条事实都必须有至少一个 quote_span。
        for f in self.verified_facts:
            if not f.quote_spans:
                raise ValueError("存在无引文接地的事实，已拒绝生成")
        return self

    def to_render_dict(self) -> dict:
        """转成面向 Markdown/JSON 输出的精简字典。"""
        return {
            "event_id": self.event_id,
            "date": self.date.isoformat(),
            "category": self.category,
            "headline": self.headline,
            "verified_facts": [
                {
                    "text": f.text,
                    "confidence": round(f.confidence, 2),
                    "single_source_claim": f.single_source_claim,
                    "quote_spans": [q.quote for q in f.quote_spans],
                    "sources": [q.source_name for q in f.quote_spans],
                }
                for f in self.verified_facts
            ],
            "perspectives_divergence": self.perspectives_divergence.model_dump(),
            "background_data": self.background_data.model_dump(),
            "sources": [s.model_dump() for s in self.sources],
            "event_cluster_id": self.event_cluster_id,
            "engine": self.engine,
            "generated_at": self.generated_at,
            "raw_article_count": self.raw_article_count,
            "coverage": self.perspectives_divergence.coverage_note,
        }