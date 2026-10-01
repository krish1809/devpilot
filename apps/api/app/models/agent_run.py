from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunStatus:
    """Allowed AgentRun.status values (kept as plain strings)."""

    RUNNING = "running"
    VALIDATED = "validated"  # patch produced and the target test passes
    TEST_FAILED = "test_failed"  # patch produced but the test still fails
    ERROR = "error"  # the run itself errored (LLM/sandbox/git)
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"  # PR opened
    PUBLISH_FAILED = "publish_failed"
    REVIEW_FAILED = "review_failed"  # tests pass but the automated reviewer refused the diff
    CANCELLED = "cancelled"


class AgentRun(Base):
    """One attempt by the agent to solve a Task."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.RUNNING)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # The exact commit SHA the run was executed against.
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # LangGraph agent (Phase 5): the planner's output and per-run usage counters
    # (the run's full step-by-step state lives in the LangGraph checkpointer,
    # keyed by thread id "run-<id>").
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Repository RAG (Phase 6): whether retrieval was used, the file the run
    # edited (given by the task or localized by the planner), and what was
    # retrieved (index stats, candidate files, context chunks) for inspection.
    use_rag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    target_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieval: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Security-sensitive additions flagged for the human reviewer (Phase 8).
    review_warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sandbox_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RunEvent(Base):
    """Append-only timeline of what happened during a run."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Approval(Base):
    """Human decision on a run's diff before publishing."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved | rejected
    # What was approved: the diff's SHA-256 and the commit it applies to.
    diff_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PullRequest(Base):
    """A PR opened for an approved run."""

    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
