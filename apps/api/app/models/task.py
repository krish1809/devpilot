from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Task(Base):
    """A unit of work for the agent: fix a failing test (optionally a GitHub issue)
    in a repo at a commit."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # GitHub binding (Phase 4). Set when the task targets a github.com repo:
    # the run is bound to (repo, base branch, base commit SHA).
    repo_full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    issue_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # The command that runs the failing test inside the sandbox. Optional since
    # Phase 7: without it the agent proposes an untested patch for human review
    # (the standard SWE-bench setting, where the tests are hidden).
    test_command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # The file the agent may edit. Optional since Phase 6: when empty, the
    # planner localizes it from retrieved repository context.
    target_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
