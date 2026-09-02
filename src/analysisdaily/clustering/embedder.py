"""文本向量化。

设计目标：离线、可回退、确定性优先。
- `auto`：优先 sentence-transformers（BGE-M3，需下载模型），
  不可用时回退 scikit-learn TF-IDF（确定性），
  再回退 HashingVectorizer（纯确定性，无模型依赖）。
统一输出稠密向量矩阵，供 HDBSCAN(metric='cosine') 使用。
"""
from __future__ import annotations

import numpy as np

from ..config import Settings

DEFAULT_DIM = 256


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._backend = self._pick_backend()
        self._model = None
        self._vectorizer = None
        self._init(self._backend)

    def _pick_backend(self) -> str:
        chosen = self.settings.embedding_backend
        if chosen == "sentence_transformers":
            return chosen
        if chosen in ("tfidf", "hashing"):
            return chosen
        # auto：尝试 st，失败回退 tfidf
        try:
            import sentence_transformers  # noqa: F401

            return "sentence_transformers"
        except Exception:  # noqa: BLE001
            return "tfidf"

    def _init(self, backend: str) -> None:
        if backend == "sentence_transformers":
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.settings.embedding_model)
        elif backend == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

            self._vectorizer = TfidfVectorizer(
                max_features=DEFAULT_DIM, stop_words="english", ngram_range=(1, 2)
            )
        elif backend == "hashing":
            from sklearn.feature_extraction.text import HashingVectorizer  # type: ignore

            self._vectorizer = HashingVectorizer(
                n_features=DEFAULT_DIM,
                ngram_range=(1, 2),
                alternate_sign=False,
                norm="l2",
            )

    @property
    def backend(self) -> str:
        return self._backend

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DEFAULT_DIM), dtype=np.float32)
        if self._backend == "sentence_transformers":
            vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.asarray(vecs, dtype=np.float32)
        # sklearn 向量化器
        if self._backend == "tfidf":
            matrix = self._vectorizer.fit_transform(texts).toarray().astype(np.float32)
        else:
            matrix = self._vectorizer.transform(texts).astype(np.float32)
        return _l2norm(matrix)

    def fit_embed(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts)


def _l2norm(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)