"""Build (or reuse) a repo index and retrieve context from it.

Retrieval is hybrid: exact cosine search over the index's vectors plus
Postgres full-text search over identifiers, fused with Reciprocal Rank Fusion.
Files named in the failing test's traceback get a boost, since they are the
strongest localization signal available.

Small repositories are embedded eagerly. Large ones (more chunks than
``eager_limit``) store text + tsvector for every chunk but embed lazily: each
query embeds the top keyword candidates that have no vector yet and persists
them, so vector search acts as a re-ranker over a set that grows with use.
CPU embedding runs at ~10–15 chunks/s here, so eagerly embedding a 12k-chunk
repo would take ~15 minutes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.rag import RepoChunk, RepoIndex
from app.rag.chunking import collect_chunks
from app.rag.embeddings import Embedder

_RRF_K = 60
_CANDIDATES_PER_LIST = 40
_TRACEBACK_BOOST = 2.0 / (_RRF_K + 1)  # = ranking first in both lists

# OR-query over the query's distinctive words: words that appear in more than
# :max_df chunks of this index (``self``, ``return``, the project name…) are
# dropped, a cheap stand-in for IDF weighting.
_KEYWORD_SQL = text(
    """
    WITH words AS (
        SELECT DISTINCT unnest(tsvector_to_array(to_tsvector('simple', :query))) AS lexeme
    ),
    stats AS (
        SELECT word, ndoc
        FROM ts_stat('SELECT tsv FROM repo_chunks WHERE index_id = '
                     || CAST(CAST(:index_id AS integer) AS text))
    ),
    q AS (
        SELECT to_tsquery('simple', string_agg(quote_literal(w.lexeme), ' | ')) AS query
        FROM words w JOIN stats s ON s.word = w.lexeme
        WHERE length(w.lexeme) >= 3 AND s.ndoc <= :max_df
    )
    SELECT c.id
    FROM repo_chunks c, q
    WHERE c.index_id = :index_id AND q.query IS NOT NULL AND c.tsv @@ q.query
    ORDER BY ts_rank_cd(c.tsv, q.query) DESC, c.id
    LIMIT :limit
    """
)

_TRACEBACK_PATHS = [
    re.compile(r'File "/work/([^"]+)"'),  # python traceback inside the sandbox
    re.compile(r"^([\w./-]+\.\w+):\d+", re.MULTILINE),  # pytest / compiler style
]


@dataclass(frozen=True)
class Hit:
    path: str
    start_line: int
    end_line: int
    content: str
    score: float

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": round(self.score, 5),
        }


def ensure_index(
    session_factory: Callable[[], Session],
    embedder: Embedder,
    *,
    repo_url: str,
    commit_sha: str,
    workspace: Path,
    max_files: int,
    max_chunks: int,
    eager_limit: int = 3000,
) -> tuple[RepoIndex, bool]:
    """Return (index, built_now). Builds atomically; concurrent builders of the
    same (repo, commit, model) converge on one row via the unique constraint.
    Repos with more than ``eager_limit`` chunks are embedded lazily."""
    key = (RepoIndex.repo_url == repo_url, RepoIndex.commit_sha == commit_sha,
           RepoIndex.embedding_model == embedder.model)  # fmt: skip
    with session_factory() as db:
        existing = db.scalar(select(RepoIndex).where(*key))
        if existing:
            db.expunge(existing)
            return existing, False

    chunks, file_count = collect_chunks(workspace, max_files=max_files, max_chunks=max_chunks)
    eager = len(chunks) <= eager_limit
    vectors = (
        embedder.embed_documents([_embed_text(c.path, c.content) for c in chunks])
        if chunks and eager
        else [None] * len(chunks)
    )

    with session_factory() as db:
        index = RepoIndex(
            repo_url=repo_url,
            commit_sha=commit_sha,
            embedding_model=embedder.model,
            file_count=file_count,
            chunk_count=len(chunks),
            fully_embedded=eager,
        )
        db.add(index)
        try:
            db.flush()
            db.add_all(
                RepoChunk(
                    index_id=index.id,
                    path=c.path,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    content=c.content,
                    embedding=v,
                )
                for c, v in zip(chunks, vectors, strict=True)
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            index = db.scalar(select(RepoIndex).where(*key))
            db.expunge(index)
            return index, False
        db.refresh(index)
        db.expunge(index)
        return index, True


def _embed_text(path: str, content: str) -> str:
    return f"{path}\n{content}"


def _embed_missing(db: Session, embedder: Embedder, chunk_ids: list[int]) -> int:
    """Embed and persist vectors for any of ``chunk_ids`` that lack one."""
    rows = db.execute(
        select(RepoChunk.id, RepoChunk.path, RepoChunk.content).where(
            RepoChunk.id.in_(chunk_ids), RepoChunk.embedding.is_(None)
        )
    ).all()
    if not rows:
        return 0
    vectors = embedder.embed_documents([_embed_text(p, c) for _, p, c in rows])
    for (chunk_id, _, _), vec in zip(rows, vectors, strict=True):
        db.execute(update(RepoChunk).where(RepoChunk.id == chunk_id).values(embedding=vec))
    db.commit()
    return len(rows)


def traceback_paths(output: str) -> set[str]:
    paths: set[str] = set()
    for pattern in _TRACEBACK_PATHS:
        paths.update(m.group(1).lstrip("./") for m in pattern.finditer(output or ""))
    return paths


def retrieve(
    db: Session,
    embedder: Embedder,
    index_id: int,
    query: str,
    *,
    boost_paths: set[str] = frozenset(),
    limit: int = _CANDIDATES_PER_LIST,
    lazy_embed: int = 150,
) -> list[Hit]:
    """Fused, ranked chunks for ``query`` within one index (best first)."""
    index = db.get(RepoIndex, index_id)
    max_df = max(25, int(0.05 * (index.chunk_count if index else 0)))
    pool = _CANDIDATES_PER_LIST if index is None or index.fully_embedded else lazy_embed
    keyword_ids = db.scalars(
        _KEYWORD_SQL,
        {"query": query, "index_id": index_id, "limit": pool, "max_df": max_df},
    ).all()
    if index is not None and not index.fully_embedded:
        _embed_missing(db, embedder, list(keyword_ids))
    keyword_ids = keyword_ids[:_CANDIDATES_PER_LIST]

    qvec = embedder.embed_query(query)
    vector_ids = db.scalars(
        select(RepoChunk.id)
        .where(RepoChunk.index_id == index_id, RepoChunk.embedding.is_not(None))
        .order_by(RepoChunk.embedding.cosine_distance(qvec), RepoChunk.id)
        .limit(_CANDIDATES_PER_LIST)
    ).all()

    scores: dict[int, float] = {}
    for ranked in (vector_ids, keyword_ids):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
    if not scores:
        return []

    rows = db.scalars(select(RepoChunk).where(RepoChunk.id.in_(scores))).all()
    hits = []
    for row in rows:
        score = scores[row.id] + (_TRACEBACK_BOOST if row.path in boost_paths else 0.0)
        hits.append(Hit(row.path, row.start_line, row.end_line, row.content, score))
    hits.sort(key=lambda h: (-h.score, h.path, h.start_line))
    return hits[:limit]


def rank_files(hits: list[Hit], limit: int = 8) -> list[str]:
    """Files ordered by their best chunk (summed score breaks ties). Using the
    max rather than the sum keeps large files with many chunks from crowding
    out a small file that matches strongly."""
    best: dict[str, float] = {}
    total: dict[str, float] = {}
    for h in hits:
        best[h.path] = max(best.get(h.path, 0.0), h.score)
        total[h.path] = total.get(h.path, 0.0) + h.score
    ranked = sorted(best, key=lambda p: (-best[p], -total[p], p))
    return ranked[:limit]


def indexed_paths(db: Session, index_id: int) -> set[str]:
    return set(db.scalars(select(RepoChunk.path).where(RepoChunk.index_id == index_id).distinct()))


def select_context(hits: list[Hit], *, budget_chars: int, exclude: set[str]) -> list[Hit]:
    """Best hits that fit the prompt budget, skipping files sent in full."""
    chosen, used = [], 0
    for h in hits:
        if h.path in exclude:
            continue
        size = len(h.content) + len(h.path) + 32
        if used + size > budget_chars:
            continue
        chosen.append(h)
        used += size
    return chosen
