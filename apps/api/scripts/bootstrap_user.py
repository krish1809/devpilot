"""Create the BOOTSTRAP_USER_EMAIL account if it doesn't exist (run on start).

The account gets an unusable random password; its owner sets one through
"Forgot password?". Idempotent, and a no-op when the variable is unset. The
Dockerfile runs it before uvicorn and never lets a failure block startup.

    python -m scripts.bootstrap_user
"""

from __future__ import annotations

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import audit
from app.services.user import ensure_bootstrap_user


def main() -> None:
    email = get_settings().bootstrap_user_email
    if not email.strip():
        print("bootstrap_user: BOOTSTRAP_USER_EMAIL not set; nothing to do.")
        return
    with SessionLocal() as db:
        user = ensure_bootstrap_user(db, email)
        if user is None:
            print("bootstrap_user: account already exists.")
            return
        audit.record_event(db, audit.USER_BOOTSTRAPPED, user_id=user.id)
        print("bootstrap_user: account created; set its password via 'Forgot password?'.")


if __name__ == "__main__":
    main()
