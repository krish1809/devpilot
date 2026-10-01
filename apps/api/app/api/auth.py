from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.demo import get_or_create_demo_user
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse
from app.services import audit
from app.services.user import (
    EmailAlreadyExistsError,
    authenticate_user,
    create_user,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

_settings = get_settings()
_auth_limit = (_settings.auth_rate_limit_max, _settings.auth_rate_limit_window_seconds)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter("auth:register", *_auth_limit))],
)
def register(user_data: UserCreate, db: DbSession, request: Request) -> UserResponse:
    try:
        user = create_user(db, user_data)
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None

    audit.record_event(
        db,
        audit.USER_REGISTERED,
        user_id=user.id,
        detail=user.email,
        ip_address=_client_ip(request),
    )
    return user


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(rate_limiter("auth:login", *_auth_limit))],
)
def login(credentials: UserLogin, db: DbSession, request: Request) -> Token:
    user = authenticate_user(db, credentials.email, credentials.password)
    ip = _client_ip(request)

    if user is None:
        audit.record_event(
            db,
            audit.USER_LOGIN_FAILED,
            detail=credentials.email,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    audit.record_event(
        db,
        audit.USER_LOGIN_SUCCEEDED,
        user_id=user.id,
        ip_address=ip,
    )
    return Token(access_token=create_access_token(subject=str(user.id)))


@router.post(
    "/demo",
    response_model=Token,
    dependencies=[Depends(rate_limiter("auth:demo", *_auth_limit))],
)
def demo_login(db: DbSession) -> Token:
    """Showcase only: sign in as the read-only demo user (404 otherwise)."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user = get_or_create_demo_user(db)
    return Token(access_token=create_access_token(subject=str(user.id)))


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: CurrentUser) -> UserResponse:
    return current_user
