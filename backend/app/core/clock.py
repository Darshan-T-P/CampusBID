from datetime import datetime, timezone


def utcnow() -> datetime:
    """Server time: the only clock the auction rules trust.

    Services take a `now` argument defaulting to this, so tests can inject a fixed time.
    """
    return datetime.now(timezone.utc)
