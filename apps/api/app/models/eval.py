from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalRun(Base):
    """One benchmark batch (e.g. a seeded sample of SWE-bench Lite) across configs."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    dataset: Mapped[str] = mapped_column(String(200), nullable=False)
    split: Mapped[str] = mapped_column(String(50), nullable=False)
    instance_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    configs: Mapped[list] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # Sampling + budget settings used, so the run is reproducible.
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvalResult(Base):
    """The agent's attempt at one instance under one config, plus its score."""

    __tablename__ = "eval_results"
    __table_args__ = (UniqueConstraint("eval_run_id", "instance_id", "config"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_id: Mapped[str] = mapped_column(String(200), nullable=False)
    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False)  # agent run status
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gold_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    localized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # None until scored by the official SWE-bench harness.
    resolved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
