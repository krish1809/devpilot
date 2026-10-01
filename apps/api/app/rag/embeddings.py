"""Provider-neutral text embeddings. The default runs locally (fastembed /
ONNX, no API key); the model is configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

# The pgvector column width. A configured model must produce vectors of this size.
EMBEDDING_DIM = 384


class EmbeddingError(Exception):
    """Embedding model unavailable or misconfigured."""


class Embedder(Protocol):
    model: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed (model downloaded once, then cached)."""

    def __init__(self, model: str, cache_dir: str | None = None) -> None:
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model, cache_dir=cache_dir)
        except Exception as exc:  # download/onnx failures surface as one clear error
            raise EmbeddingError(f"Could not load embedding model {model!r}: {exc}") from exc
        self.model = model
        probe = list(self._model.embed(["probe"]))[0]
        self.dim = len(probe)
        if self.dim != EMBEDDING_DIM:
            raise EmbeddingError(
                f"Embedding model {model!r} produces {self.dim}-d vectors; "
                f"the index column is {EMBEDDING_DIM}-d."
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=64)]

    def embed_query(self, text: str) -> list[float]:
        # bge-style models expect an instruction prefix on queries.
        return list(self._model.query_embed([text]))[0].tolist()


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir or None)
