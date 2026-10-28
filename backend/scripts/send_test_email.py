"""Check your email settings by sending one real message.

    python scripts/send_test_email.py you@gmail.com

Reads the same settings the server does (backend/.env). If EMAIL_BACKEND is still 'console' nothing is sent
and the script says so; a wrong host, port or password is reported in plain words.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services import mailer  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print(__doc__)
        return 2
    to = sys.argv[1]
    if settings.email_backend != "smtp":
        print("EMAIL_BACKEND is not 'smtp', so nothing would be sent. Set EMAIL_BACKEND=smtp and the SMTP_* values in backend/.env.")
        return 1
    if not settings.smtp_ready:
        print("SMTP_HOST is empty. Set it (and SMTP_USERNAME / SMTP_PASSWORD if your provider needs a login) in backend/.env.")
        return 1
    subject, text, page = mailer.verification_email("123456", settings.verification_code_ttl_minutes)
    try:
        mailer.send_email(to, "[Test] " + subject, "This is a test of your Relay email settings.\n\n" + text, page)
    except mailer.EmailError as e:
        print(f"Failed: {e}")
        return 1
    print(f"Sent to {to} from {settings.email_from} via {settings.smtp_host}:{settings.smtp_port}. Check the inbox (and spam).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
