from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(
    db: Session,
    owner_id: int,
    project_data: ProjectCreate,
) -> Project:
    project = Project(
        owner_id=owner_id,
        name=project_data.name,
        description=project_data.description,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


def get_projects(db: Session, owner_id: int) -> list[Project]:
    statement = select(Project).where(Project.owner_id == owner_id).order_by(Project.id)

    return list(db.scalars(statement).all())


def get_project(
    db: Session,
    project_id: int,
    owner_id: int,
) -> Project | None:
    statement = select(Project).where(
        Project.id == project_id,
        Project.owner_id == owner_id,
    )

    return db.scalar(statement)


def update_project(
    db: Session,
    project: Project,
    project_data: ProjectUpdate,
) -> Project:
    update_data = project_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


def delete_project(
    db: Session,
    project: Project,
) -> None:
    db.delete(project)
    db.commit()
