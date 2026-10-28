import functools
import hashlib
import hmac
import os
from datetime import timedelta

import jwt

from app.core.clock import utcnow
from app.core.config import settings

ALGORITHM = "HS256"
_SCRYPT_R = 8
_MAXMEM = 128 * 1024 * 1024  # hashlib's default (32 MB) is too small for the recommended cost


def _params() -> tuple[int, int, int]:
    return settings.password_scrypt_n, _SCRYPT_R, settings.password_scrypt_p


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    """scrypt, stored as 'scrypt$N$r$p$salt$hash' so the cost can be raised later and old hashes still verify."""
    n, r, p = _params()
    salt = os.urandom(16)
    return f"scrypt${n}${r}${p}${salt.hex()}${_scrypt(password, salt, n, r, p).hex()}"


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    """-> (n, r, p, salt, digest) for both the current format and the original 'salt$hash' one."""
    try:
        parts = stored.split("$")
        if len(parts) == 6 and parts[0] == "scrypt":
            return int(parts[1]), int(parts[2]), int(parts[3]), bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
        if len(parts) == 2:  # original format, always N=2**14, r=8, p=1
            return 2**14, 8, 1, bytes.fromhex(parts[0]), bytes.fromhex(parts[1])
    except ValueError:
        pass
    return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = _scrypt(password, salt, n, r, p)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    """True when a stored hash was made with weaker settings than we use now (re-hash it at next login)."""
    parsed = _parse(stored)
    return parsed is None or parsed[:3] != _params()


@functools.lru_cache(maxsize=8)
def _dummy_hash(n: int, p: int) -> str:
    return hash_password("not-a-real-password")


def burn_password_check(password: str) -> None:
    """Do the same work as a real password check. Used when the email doesn't exist, so a login attempt
    takes the same time either way and can't be used to find out which emails have accounts."""
    verify_password(password, _dummy_hash(settings.password_scrypt_n, settings.password_scrypt_p))


def create_access_token(user_id: int) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token_claims(token: str) -> tuple[int, int] | None:
    """(user id, issued-at seconds) from a valid token, or None if invalid/expired/missing required claims."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],  # pinned: never trust the algorithm named inside the token
            options={"require": ["exp", "sub"]},  # a token that never expires is not acceptable
        )
        return int(payload["sub"]), int(payload.get("iat", 0))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if invalid/expired/missing required claims."""
    claims = decode_token_claims(token)
    return claims[0] if claims else None
