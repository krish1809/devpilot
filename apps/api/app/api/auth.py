import hashlib
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.demo import get_or_create_demo_user
from app.core.rate_limit import check_rate_limit, rate_limiter
from app.core.security import create_access_token
from app.integrations.email import EmailSender, get_email_sender
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services import audit
from app.services.password_reset import (
    InvalidResetTokenError,
    issue_reset_token,
    reset_password,
    send_reset_email,
)
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
_reset_ip_limit = (
    _settings.password_reset_ip_limit_max,
    _settings.password_reset_ip_limit_window_seconds,
)

# One response for every forgot-password request, so it can't be used to find
# out which emails have accounts.
FORGOT_PASSWORD_RESPONSE = (
    "If an account exists for that email, we've sent a link to reset its password."
)
INVALID_RESET_TOKEN = "This reset link is invalid or has expired. Request a new one."


def _issue_token(user: User) -> Token:
    return Token(access_token=create_access_token(str(user.id), version=user.token_version))


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
    return _issue_token(user)


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
    return _issue_token(user)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limiter("auth:forgot:ip", *_reset_ip_limit))],
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    request: Request,
    background: BackgroundTasks,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> MessageResponse:
    """Email a reset link if the account exists. The response is always the same."""
    settings = get_settings()
    # Per-email limit (on top of per-IP), keyed by a hash so raw addresses aren't
    # held in memory. It applies to any string, so a 429 reveals nothing either.
    email_key = hashlib.sha256(payload.email.encode("utf-8")).hexdigest()
    check_rate_limit(
        f"auth:forgot:email:{email_key}",
        settings.password_reset_email_limit_max,
        settings.password_reset_email_limit_window_seconds,
    )

    issued = issue_reset_token(db, payload.email)
    if issued is not None:
        # Sent after the response, so timing doesn't reveal that it happened.
        background.add_task(send_reset_email, sender, issued.user.email, issued.raw_token)
    audit.record_event(
        db,
        audit.PASSWORD_RESET_REQUESTED,
        user_id=issued.user.id if issued else None,
        # Like failed logins: the address typed for an unknown account is kept
        # (it helps spot enumeration attempts); never the token.
        detail=None if issued else payload.email,
        ip_address=_client_ip(request),
    )
    return MessageResponse(detail=FORGOT_PASSWORD_RESPONSE)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limiter("auth:reset", *_auth_limit))],
)
def reset_password_endpoint(
    payload: ResetPasswordRequest, db: DbSession, request: Request
) -> MessageResponse:
    """Set a new password with a reset token; signs out every existing session."""
    try:
        user = reset_password(db, payload.token, payload.new_password)
    except InvalidResetTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_RESET_TOKEN
        ) from None

    audit.record_event(
        db,
        audit.PASSWORD_RESET_COMPLETED,
        user_id=user.id,
        ip_address=_client_ip(request),
    )
    return MessageResponse(detail="Your password has been reset. You can now log in.")


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: CurrentUser) -> UserResponse:
    return current_user
