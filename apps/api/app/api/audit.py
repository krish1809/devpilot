from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.audit import AuditLogResponse
from app.services.audit import list_events_for_user

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
)


@router.get("/me", response_model=list[AuditLogResponse])
def read_my_audit_events(
    db: DbSession,
    current_user: CurrentUser,
) -> list[AuditLogResponse]:
    """Return the current user's own audit events, newest first."""
    return list_events_for_user(db, current_user.id)
