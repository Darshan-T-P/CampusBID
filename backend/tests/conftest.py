import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.db.session import Base, get_db, make_engine
from app.main import app


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
