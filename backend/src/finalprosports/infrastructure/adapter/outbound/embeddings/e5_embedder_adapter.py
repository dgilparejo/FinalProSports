"""EmbedderOutputPort with intfloat/multilingual-e5-base (sentence-transformers) running in process.
e5 convention: documents are prefixed with "passage: " and queries with "query: "; vectors are L2-normalised so that the
cosine distance of pgvector (<=>) equals 1 - dot product."""
from __future__ import annotations


class E5EmbedderAdapter:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-base", batch_size: int = 32, revision: str | None = None):
        from sentence_transformers import SentenceTransformer  # heavy import kept local: only this adapter needs it
        self._model = SentenceTransformer(model_name, revision=revision)      # revision = HF commit hash (Settings.embedding_model_revision)
        self.model_name, self.revision = model_name, revision
        self._batch = batch_size
        self._dim = int(self._model.get_sentence_embedding_dimension())

    def dimension(self) -> int:
        return self._dim

    def embed_query(self, text: str) -> list[float]:
        t = text if text.startswith("query: ") else f"query: {text}"
        return self._model.encode([t], normalize_embeddings=True, batch_size=1)[0].tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        docs = [t if t.startswith("passage: ") else f"passage: {t}" for t in texts]
        return [v.tolist() for v in self._model.encode(docs, normalize_embeddings=True, batch_size=self._batch, show_progress_bar=False)]


class LazyE5EmbedderAdapter:
    """Same port, but the model is loaded on the first call: the default retrieval strategy (attributes) never needs it,
    so the API and the evaluation adapters start without paying the model load."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base", batch_size: int = 32, revision: str | None = None):
        self._args, self._inner = (model_name, batch_size, revision), None

    def _get(self) -> E5EmbedderAdapter:
        if self._inner is None:
            self._inner = E5EmbedderAdapter(*self._args)
        return self._inner

    def dimension(self) -> int:
        return self._get().dimension()

    def embed_query(self, text: str) -> list[float]:
        return self._get().embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._get().embed_documents(texts)
