"""Mobile numbers: accept the ways people type them, store one canonical form (+<country code><number>)."""

import re

_HELP = "Enter a valid mobile number, like 98765 43210 or +91 98765 43210"


def normalize_phone(raw: str) -> str:
    """'98765 43210', '098765-43210', '+91 98765 43210' -> '+919876543210'. Raises ValueError if it isn't a number.

    A bare 10-digit number starting 6-9 is taken as an Indian mobile; anything else must carry its own +country code.
    """
    text = re.sub(r"[\s\-().]", "", raw.strip())
    if text.startswith("+"):
        digits = text[1:]
        if digits.isdigit() and 8 <= len(digits) <= 15 and digits[0] != "0":
            return "+" + digits
        raise ValueError(_HELP)
    if not text.isdigit():
        raise ValueError(_HELP)
    if len(text) == 11 and text.startswith("0"):
        text = text[1:]
    elif len(text) == 12 and text.startswith("91"):
        text = text[2:]
    if len(text) == 10 and text[0] in "6789":
        return "+91" + text
    raise ValueError(_HELP)


def clean_phone(value: str | None) -> str | None:
    """For request schemas: blank means 'none'; anything else must normalise."""
    if value is None or not value.strip():
        return None
    return normalize_phone(value)
