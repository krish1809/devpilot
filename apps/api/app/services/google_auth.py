"""Sign in with a verified Google identity (design: docs/google-sign-in.md).

Lookup order:
1. ``google_sub`` — the account already signed in with Google before.
2. The email — an existing password account is linked (``google_sub`` is
   stored), because Google has verified the user owns that address. That's the
   same proof the forgot-password flow relies on.
3. Otherwise a new account is created with an unusable random password (the
   user can set one later with "Forgot password?").

Unverified emails and the shared showcase demo account are refused.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.integrations.google import GoogleIdentity
from app.models.user import User
from app.services.user import get_user_by_email


class GoogleSignInError(Exception):
    """The identity can't be used to sign in (reason is for logs/audit only)."""


@dataclass(frozen=True)
class GoogleSignIn:
    user: User
    created: bool
    linked: bool


def sign_in_with_google(db: Session, identity: GoogleIdentity) -> GoogleSignIn:
    if not identity.email_verified:
        raise GoogleSignInError("email not verified by Google")
    if identity.email == get_settings().demo_user_email:
        raise GoogleSignInError("the showcase demo account can't use Google sign-in")

    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is not None:
        if not user.is_active:
            raise GoogleSignInError("account is inactive")
        return GoogleSignIn(user=user, created=False, linked=False)

    user = get_user_by_email(db, identity.email)
    if user is not None:
        if not user.is_active:
            raise GoogleSignInError("account is inactive")
        if user.google_sub is not None:
            # The address belongs to an account linked to a *different* Google
            # account; don't silently re-link it.
            raise GoogleSignInError("email is linked to another Google account")
        user.google_sub = identity.sub
        db.commit()
        db.refresh(user)
        return GoogleSignIn(user=user, created=False, linked=True)

    user = User(
        email=identity.email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        google_sub=identity.sub,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two first sign-ins raced; the other request created the account.
        db.rollback()
        raise GoogleSignInError("concurrent sign-up; try again") from None
    db.refresh(user)
    return GoogleSignIn(user=user, created=True, linked=False)
