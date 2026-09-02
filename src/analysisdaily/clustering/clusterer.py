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
SIM_THRESHOLD = 0.45
# 两级聚类：feed 内更紧（分开不同子事件），跨 feed 仅合并高相似的同一事件
FEED_SIM = 0.55
MERGE_SIM = 0.50


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
        labels = self._compute_labels(windowed, vecs)

        groups: dict[int, list[RawArticle]] = {}
        for a, lab in zip(windowed, labels):
            groups.setdefault(int(lab), []).append(a)

        out: list[EventCluster] = []
        seq_by_terms: Counter = Counter()
        for lab, arts in groups.items():
            if lab < 1 or len(arts) < self.min_samples or len({a.source_name for a in arts}) < 2:
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

    def _compute_labels(self, windowed: list[RawArticle], vecs: np.ndarray) -> np.ndarray:
        """两级聚类：按 feed 分组，feed 内紧聚类，再跨 feed 合并同一事件。"""
        feeds: dict[str, list[int]] = {}
        for i, a in enumerate(windowed):
            feeds.setdefault(a.feed, []).append(i)
        if len(feeds) <= 1:
            if self.algorithm == "hdbscan":
                return self._hdbscan(vecs)
            return self._threshold_cluster(vecs, SIM_THRESHOLD)
        # 一级：每个 feed 内"紧"聚类（同主题内分开不同的子事件）
        sub_groups: list[list[int]] = []
        for idxs in feeds.values():
            sub_groups.extend(self._cluster_subset(vecs, idxs, FEED_SIM))
        # 二级：跨 feed 仅合并"同一事件"（高相似）的簇
        merged = self._merge_groups(sub_groups, vecs, MERGE_SIM)
        idx2label: dict[int, int] = {}
        for lab, grp in enumerate(merged, start=1):
            for i in grp:
                idx2label[i] = lab
        return np.array([idx2label.get(i, -1) for i in range(len(windowed))], dtype=int)

    def _cluster_subset(self, vecs: np.ndarray, idxs: list[int], threshold: float) -> list[list[int]]:
        if len(idxs) <= 1:
            return [list(idxs)]
        from sklearn.cluster import AgglomerativeClustering  # type: ignore

        sub = vecs[idxs]
        clf = AgglomerativeClustering(
            n_clusters=None, distance_threshold=max(0.05, 1.0 - threshold),
            metric="cosine", linkage="average",
        )
        assign = clf.fit_predict(sub)
        groups: dict[int, list[int]] = {}
        for j, lab in enumerate(assign.tolist()):
            groups.setdefault(int(lab), []).append(idxs[j])
        return list(groups.values())

    def _merge_groups(self, groups: list[list[int]], vecs: np.ndarray, threshold: float) -> list[list[int]]:
        if not groups:
            return []
        from sklearn.cluster import AgglomerativeClustering  # type: ignore

        centroids = np.stack([vecs[g].mean(axis=0) for g in groups])
        clf = AgglomerativeClustering(
            n_clusters=None, distance_threshold=max(0.05, 1.0 - threshold),
            metric="cosine", linkage="average",
        )
        assign = clf.fit_predict(centroids)
        merged: dict[int, list[int]] = {}
        for j, lab in enumerate(assign.tolist()):
            merged.setdefault(int(lab), []).extend(groups[j])
        return list(merged.values())

    def _hdbscan(self, vecs: np.ndarray) -> np.ndarray:
        try:
            from sklearn.cluster import HDBSCAN  # type: ignore

            clf = HDBSCAN(min_cluster_size=self.min_samples, min_samples=1, metric="cosine")
            return clf.fit_predict(vecs)
        except Exception:  # noqa: BLE001
            return self._threshold_cluster(vecs, SIM_THRESHOLD)

    def _guess_category(self, articles: list[RawArticle]) -> str:
        """规则分类（LLM 分类的兜底）：用标题+权重最高文本的显著词，避免泛化误判。"""
        a0 = articles[0]
        head = (a0.title + " " + a0.text[:220]).lower()
        cats = [
            ("安全与冲突", ("war", "attack", "military", "drone", "missile", "conflict", "strike", "troops", "defense", "ceasefire", "hostage", "invasion", "bomb")),
            ("国际政治", ("president", "minister", "parliament", "election", "diplomacy", "embassy", "summit", "treaty", "sanctions", "prime minister", "government", "policy", "ambassador")),
            ("经济与市场", ("economy", "market", "stock", "inflation", "gdp", "trade", "tariff", "bank", "interest rate", "company", "profit", "shares", "earnings", "revenue")),
            ("科技与AI", ("artificial intelligence", " ai ", "technology", "chip", "software", "data", "cybersecurity", "robot", "app ", "cloud", "startup")),
            ("气候与环境", ("climate", "carbon", "emission", "energy", "renewable", "weather", "flood", "wildfire", "pollution", "warming", "heatwave")),
            ("社会与公共政策", ("immigration", "health", "education", "crime", "court", "trial", "lawsuit", "worker", "school", "pension", "asylum")),
            ("文化体育", ("film", "festival", "music", "sport", "league", "actor", "concert", "album", "tournament", "movie", "star ")),
        ]
        best, best_hits = "未分类", 0
        for cat, words in cats:
            hits = sum(head.count(w) for w in words)
            if hits > best_hits:
                best, best_hits = cat, hits
        return best