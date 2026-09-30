from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Task(Base):
    """A unit of work for the agent: fix a failing test in a repo at a commit."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The command that runs the failing test inside the sandbox.
    test_command: Mapped[str] = mapped_column(String(500), nullable=False)
    # The file the agent is allowed to edit / that is sent to the LLM.
    target_path: Mapped[str] = mapped_column(String(500), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
