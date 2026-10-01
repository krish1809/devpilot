from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

# Canonical action names (kept as constants so they stay consistent).
USER_REGISTERED = "user.registered"
USER_LOGIN_SUCCEEDED = "user.login.succeeded"
USER_LOGIN_FAILED = "user.login.failed"
PROJECT_CREATED = "project.created"
PROJECT_DELETED = "project.deleted"
TASK_IMPORTED = "task.imported_from_issue"
RUN_APPROVED = "run.approved"
RUN_REJECTED = "run.rejected"


def record_event(
    db: Session,
    action: str,
    *,
    user_id: int | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Append an audit event and commit it.

    Detail is truncated defensively; audit rows never store secrets (callers
    must not pass passwords, tokens, or full payloads).
    """
    event = AuditLog(
        action=action,
        user_id=user_id,
        detail=detail[:255] if detail else None,
        ip_address=ip_address,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_events_for_user(db: Session, user_id: int, limit: int = 50) -> list[AuditLog]:
    statement = (
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())
