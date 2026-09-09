"""Deterministic, dependency-free EmbedderOutputPort for tests: hashed bag of words into a fixed dimension, L2-normalised."""
import hashlib
import math


class HashingEmbedderAdapter:
    def __init__(self, dimension: int = 768):
        self._dim = dimension

    def dimension(self) -> int:
        return self._dim

    def _embed(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for tok in text.lower().split():
            h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self._dim] += 1.0 if (h >> 8) % 2 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]
