"""Send one test email through the configured backend and report the result.

Use it after setting EMAIL_* on a deployment (Render shell) or locally:

    python -m scripts.send_test_email you@example.com

It prints configuration problems first (never secret values), then the
provider's answer, and exits non-zero if delivery failed.
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.integrations.email import (
    EmailError,
    EmailMessage,
    email_config_problems,
    get_email_sender,
)


def main(argv: list[str]) -> int:
    if len(argv) != 1 or "@" not in argv[0]:
        print("usage: python -m scripts.send_test_email you@example.com")
        return 2
    to = argv[0].strip()
    settings = get_settings()
    print(f"backend={settings.email_backend} from={settings.email_from!r}")
    for problem in email_config_problems(settings):
        print(f"warning: {problem}")
    message = EmailMessage(
        to=to,
        subject="DevPilot test email",
        text="If you can read this, DevPilot's outgoing email works.",
        html="<p>If you can read this, DevPilot's outgoing email works.</p>",
    )
    try:
        get_email_sender().send(message)
    except EmailError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"sent to {to} (console backend prints instead of sending)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
