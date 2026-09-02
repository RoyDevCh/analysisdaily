"""事件追踪：同一事件跨日串联，形成发展时间线。

- 用持久化 threads 存储（data/threads.json）。
- 跨日匹配：新事件与已有线程按"标题+综述"嵌入余弦相似度匹配，命中则追加一天快照，
  否则新建线程。
- 渲染：日报里输出"事件追踪"时间线（如 提案 → 委员会 → 表决）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ..clustering.embedder import Embedder
from ..models.report import StructuredReport

MATCH_THRESHOLD = 0.34


class ThreadSnapshot(BaseModel):
    date: str
    event_cluster_id: str
    headline: str
    summary: str = ""
    category: str = ""


class Thread(BaseModel):
    thread_id: str
    title: str
    category: str = ""
    events: list[ThreadSnapshot] = Field(default_factory=list)


def load_threads(path: Path) -> list[Thread]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [Thread(**t) for t in data]
        except Exception:  # noqa: BLE001
            return []
    return []


def save_threads(path: Path, threads: list[Thread]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([t.model_dump() for t in threads], ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.lower()).strip("-")
    return s[:40] or "event"


def update_threads(embedder: Embedder, reports: list[StructuredReport], threads: list[Thread], date_str: str) -> list[Thread]:
    """把今天的每条事件并入对应线程（匹配则追加，否则新建）。"""
    if not reports:
        return threads
    # 一次 encode：让新事件与既有线程共享同一词表（TF-IDF 每次 fit 的维度需一致）
    texts = [f"{r.headline}. {r.summary}" for r in reports] + (
        [f"{t.events[-1].headline}. {t.events[-1].summary}" for t in threads] if threads else []
    )
    vecs = embedder.encode(texts)
    new_vecs = vecs[: len(reports)]
    last_vecs = vecs[len(reports):]
    for i, r in enumerate(reports):
        nv = new_vecs[i]
        best_t, best_sim = None, 0.0
        for j, tv in enumerate(last_vecs):
            sim = float(nv @ tv)
            if sim > best_sim:
                best_t, best_sim = threads[j], sim
        snap = ThreadSnapshot(
            date=date_str, event_cluster_id=r.event_id, headline=r.headline,
            summary=(r.summary or "")[:400], category=r.category,
        )
        if best_t is not None and best_sim >= MATCH_THRESHOLD:
            best_t.events.append(snap)
            best_t.title = snap.headline  # 用最新标题
            best_t.category = snap.category
        else:
            threads.append(Thread(thread_id=f"thread-{_slug(r.headline)}", title=r.headline, category=r.category, events=[snap]))
    return threads


def _d(e: ThreadSnapshot) -> str:
    return f"{e.date[:4]}-{e.date[4:6]}-{e.date[6:8]}"


def render_tracking(threads: list[Thread], min_days: int = 2) -> list[str]:
    """返回 事件追踪 时间线（多日事件优先，逐日缩进呈现发展脉络）。"""
    multi = [t for t in threads if len(t.events) >= min_days]
    active = [t for t in threads if len(t.events) == 1]
    def _fmt(t: Thread) -> str:
        span = f"{_d(t.events[0])} → {_d(t.events[-1])}"
        lines = [f"- **{t.title[:64]}**（{len(t.events)} 天 | {span}）"]
        for e in t.events:
            lines.append(f"   · {_d(e)}  {e.headline[:60]}")
        return "\n".join(lines)
    out = [_fmt(t) for t in multi]
    for t in active:
        out.append(f"- **{t.title[:64]}**（新 · {_d(t.events[0])}）")
    return out