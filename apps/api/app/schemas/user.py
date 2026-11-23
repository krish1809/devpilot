import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pragmatic email check. Pydantic's EmailStr needs the optional
# `email-validator` package; when it is added, swap `email: str` for
# `email: EmailStr` and drop this validator.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def validate_new_password(value: str) -> str:
    """The one password policy, shared by registration and password reset."""
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"password must be at most {PASSWORD_MAX_LENGTH} characters")
    return value


class UserCreate(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("invalid email address")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_new_password(value)


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    # Deliberately not format-validated: a malformed address simply matches no
    # account and gets the same generic response as everything else.
    email: str = Field(max_length=255)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_new_password(value)


class MessageResponse(BaseModel):
    detail: str
