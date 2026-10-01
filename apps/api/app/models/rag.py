from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.rag.embeddings import EMBEDDING_DIM


class RepoIndex(Base):
    """An embedded snapshot of one repository at one commit (shared by runs)."""

    __tablename__ = "repo_indexes"
    __table_args__ = (UniqueConstraint("repo_url", "commit_sha", "embedding_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RepoChunk(Base):
    """A chunk of one file: text for the prompt, a vector for semantic search,
    and a generated tsvector for keyword search. Searches are always filtered by
    ``index_id`` (one repo at one commit), so exact vector scans stay small and
    no ANN index is needed."""

    __tablename__ = "repo_chunks"
    __table_args__ = (Index("ix_repo_chunks_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(
        ForeignKey("repo_indexes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', path || ' ' || content)", persisted=True),
    )
