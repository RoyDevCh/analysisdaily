"""滑动时间窗口 + 事件聚类 → Event_Cluster_ID。

需求要点：仅聚合"过去 window_hours 小时"内的文章；同一事件的 5-20 篇
不同来源文章聚为一个 Event_Cluster_ID；并给每个簇生成可读 slug 与排序。

算法：默认 `algorithm="similarity"`（确定性：按余弦阈值做连通域聚类，
对中小语料稳定）。生产大语料可选 `algorithm="hdbscan"`（scikit-learn
HDBSCAN，符合需求推荐），小样本下 HDBSCAN 易把稀疏组标为噪声，故默认
用相似度阈值法以保障端到端可用性。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Literal

import numpy as np

from ..models.raw import EventCluster, RawArticle
from .embedder import Embedder

STOP = {"a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for", "with", "as", "by", "from", "into", "over", "after", "before", "amid", "be", "is", "are", "was", "were", "will", "would", "can", "could", "should", "this", "that", "these", "those", "new", "says", "said", "report", "reports", "news", "today", "year", "years", "day", "days", "week", "weeks"}

# 文章相似度阈值（余弦）：事件内跨源应 >= 该值
SIM_THRESHOLD = 0.30


def _cluster_id(date_str: str, slug: str, seq: int) -> str:
    return f"{date_str}-{slug}-{seq:02d}"


def _slugify_terms(title: str) -> str:
    seen = set()
    terms = []
    for word in re.findall(r"[\w\u4e00-\u9fff]+", title.lower()):
        if word in STOP or word in seen:
            continue
        seen.add(word)
        terms.append(word)
        if len(terms) >= 4:
            break
    return "-".join(terms) or "event"


class HdbscanClusterer:
    def __init__(
        self,
        embedder: Embedder,
        window_hours: int = 24,
        min_samples: int = 2,
        algorithm: Literal["similarity", "hdbscan"] = "similarity",
    ):
        self.embedder = embedder
        self.window_hours = window_hours
        self.min_samples = min(3, max(2, min_samples))
        self.algorithm = algorithm

    def cluster(self, articles: list[RawArticle], date_str: str) -> list[EventCluster]:
        if not articles:
            return []
        windowed = self._sliding_window(articles)
        if not windowed:
            return []
        texts = [a.text for a in windowed]
        vecs = self.embedder.encode(texts)
        if self.algorithm == "hdbscan":
            labels = self._hdbscan(vecs)
        else:
            labels = self._threshold_cluster(vecs, SIM_THRESHOLD)

        groups: dict[int, list[RawArticle]] = {}
        for a, lab in zip(windowed, labels):
            groups.setdefault(int(lab), []).append(a)

        out: list[EventCluster] = []
        seq_by_terms: Counter = Counter()
        for lab, arts in groups.items():
            if lab < 1 or len(arts) < self.min_samples:
                continue
            arts.sort(key=lambda a: a.bias.fact_weight, reverse=True)
            slug = _slugify_terms(arts[0].title)
            seq_by_terms[slug] += 1
            eid = _cluster_id(date_str, slug, seq_by_terms[slug])
            weighted = [(a.source_name, a.text, a.bias.fact_weight) for a in arts]
            weighted.sort(key=lambda t: t[2], reverse=True)
            out.append(
                EventCluster(
                    event_cluster_id=eid,
                    date=date_str,
                    category=self._guess_category(arts),
                    articles=arts,
                    weighted_texts=weighted,
                )
            )
        out.sort(key=lambda c: c.size, reverse=True)
        return out

    def _sliding_window(self, articles: list[RawArticle]) -> list[RawArticle]:
        now = max(a.published for a in articles)
        cutoff = now.timestamp() - self.window_hours * 3600
        return [a for a in articles if a.published.timestamp() >= cutoff]

    def _threshold_cluster(self, vecs: np.ndarray, threshold: float) -> np.ndarray:
        """平均连接层次聚类（抗链式合并）：返回 [1..K, -1 噪声]。

        单连接（连通域）在混合 feed 上容易把不同主题链成一个巨型簇；
        平均连接以"组间平均相似度"判定合并，显著降低过合并。
        distance_threshold = 1 - similarity_threshold。
        """
        n = len(vecs)
        labels = np.full(n, -1, dtype=int)
        if n == 0:
            return labels
        try:
            from sklearn.cluster import AgglomerativeClustering  # type: ignore

            clf = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=max(0.05, 1.0 - threshold),
                metric="cosine",
                linkage="average",
            )
            assign = clf.fit_predict(vecs)
            # 归一：只有 >=2 的簇保留为事件，单点标记为噪声(-1)
            from collections import Counter

            counts = Counter(assign.tolist())
            for i, lab in enumerate(assign.tolist()):
                labels[i] = lab + 1 if counts[lab] >= 2 else -1
            return labels
        except Exception:  # noqa: BLE001
            # 兜底：连到 0.35 以上的连通域
            sim = vecs @ vecs.T
            parent = list(range(n))

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            for i in range(n):
                for j in range(i + 1, n):
                    if sim[i, j] >= 0.35:
                        union(i, j)
            comp: dict[int, int] = {}
            next_lab = 1
            for i in range(n):
                root = find(i)
                if root not in comp:
                    comp[root] = next_lab
                    next_lab += 1
                labels[i] = comp[root]
            return labels

    def _hdbscan(self, vecs: np.ndarray) -> np.ndarray:
        try:
            from sklearn.cluster import HDBSCAN  # type: ignore

            clf = HDBSCAN(min_cluster_size=self.min_samples, min_samples=1, metric="cosine")
            return clf.fit_predict(vecs)
        except Exception:  # noqa: BLE001
            return self._threshold_cluster(vecs, SIM_THRESHOLD)

    def _guess_category(self, articles: list[RawArticle]) -> str:
        kw = {
            "经济与科技": ("tech", "chip", "ai", "economy", "market", "trade", "tariff", "公司", "科技", "经济", "antitrust", "fine"),
            "政治与外交": ("president", "parliament", "election", "minister", "embassy", "政治", "总统", "选举"),
            "社会与公共政策": ("immigration", "health", "education", "social", "社会", "移民", "医疗"),
            "环境与能源": ("climate", "oil", "energy", "carbon", "环境", "气候", "coal"),
        }
        corpus = " ".join(a.text.lower() for a in articles)
        best, best_hits = "未分类", 0
        for cat, words in kw.items():
            hits = sum(corpus.count(w) for w in words)
            if hits > best_hits:
                best, best_hits = cat, hits
        return best