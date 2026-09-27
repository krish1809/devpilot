from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services import audit
from app.services.project import (
    create_project,
    delete_project,
    get_project,
    get_projects,
    update_project,
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


router = APIRouter(
    prefix="/projects",
    tags=["projects"],
)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_endpoint(
    project_data: ProjectCreate,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
) -> ProjectResponse:
    project = create_project(db, current_user.id, project_data)
    audit.record_event(
        db,
        audit.PROJECT_CREATED,
        user_id=current_user.id,
        detail=f"project:{project.id}",
        ip_address=_client_ip(request),
    )
    return project


@router.get(
    "",
    response_model=list[ProjectResponse],
)
def get_projects_endpoint(
    db: DbSession,
    current_user: CurrentUser,
) -> list[ProjectResponse]:
    return get_projects(db, current_user.id)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project_endpoint(
    project_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> ProjectResponse:
    project = get_project(db, project_id, current_user.id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update_project_endpoint(
    project_id: int,
    project_data: ProjectUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ProjectResponse:
    project = get_project(db, project_id, current_user.id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return update_project(db, project, project_data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_endpoint(
    project_id: int,
    db: DbSession,
    current_user: CurrentUser,
    request: Request,
) -> None:
    project = get_project(db, project_id, current_user.id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    delete_project(db, project)
    audit.record_event(
        db,
        audit.PROJECT_DELETED,
        user_id=current_user.id,
        detail=f"project:{project_id}",
        ip_address=_client_ip(request),
    )
