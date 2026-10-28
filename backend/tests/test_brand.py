"""The product is called Relay. "CampusBid" is only the repository and code name."""

from pathlib import Path

from app.core.config import settings
from app.services import assistant, mailer

APP = Path(__file__).resolve().parent.parent / "app"


def test_the_configured_name_is_relay():
    assert settings.app_name == "Relay"


def test_the_old_name_is_not_in_anything_the_app_says():
    allowed = {APP / "core" / "config.py"}  # a comment there explains the naming
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py") if p not in allowed and "CampusBid" in p.read_text()]
    assert offenders == []


def test_the_assistant_introduces_itself_as_relay():
    assert assistant.SYSTEM_PROMPT.startswith("You are Relay's shopping assistant")


def test_every_email_is_from_relay():
    for subject, text, page in (
        mailer.verification_email("123456", 10),
        mailer.password_reset_email("123456", 15),
        mailer.password_changed_email(),
        mailer.auction_won_email("Hero cycle", 500, "Sam", None, "http://x"),
        mailer.sale_rejected_email("Hero cycle", "No.", "http://x"),
    ):
        assert "Relay" in text and "CampusBid" not in subject + text + page
