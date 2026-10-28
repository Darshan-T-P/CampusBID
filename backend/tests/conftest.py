import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.session import Base, get_db, make_engine
from app.main import app


@pytest.fixture(autouse=True)
def account_defaults(monkeypatch):
    """Keep unrelated tests simple: accounts start verified, no domain rule, no rate limits.

    The account/trust tests (test_accounts.py) switch the real behaviour back on.
    """
    monkeypatch.setattr(settings, "auto_verify", True)
    monkeypatch.setattr(settings, "allowed_email_domains", "")
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "password_scrypt_n", 2**4)  # real cost is deliberately slow; tests needn't pay it
    monkeypatch.setattr(settings, "password_scrypt_p", 1)
    limiter.reset()


@pytest.fixture(autouse=True)
def media_dir(tmp_path, monkeypatch):
    """Send uploaded photos to a throwaway folder instead of the real media dir."""
    path = tmp_path / "media"
    monkeypatch.setattr(settings, "media_dir", str(path))
    return path


@pytest.fixture()
def db_session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        yield session
    engine.dispose()


@pytest.fixture()
def client(db_session, tmp_path):
    engine = db_session.get_bind()
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # No `with`: skip lifespan so init_db doesn't touch the real database file.
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, email="a@campus.edu", password="password123", name="Asha"):
    r = client.post(
        "/auth/register", json={"email": email, "password": password, "display_name": name}
    )
    return r


def auth_header(client, **kwargs):
    token = register(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
