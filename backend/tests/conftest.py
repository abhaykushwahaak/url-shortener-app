"""Test fixtures.

The environment is configured *before* any application module is imported, because
`Settings` is created once at import time. Three things are swapped for the test
run:

  * PostgreSQL -> a throwaway SQLite file (no server needed to run the suite),
  * Redis      -> `fakeredis`, so cache behaviour is exercised in-process,
  * Celery     -> eager mode, so the click task runs inline and assertions can
                  check the resulting rows without a worker.
"""

import os
import tempfile
import uuid
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / "urlshortener_test.db"

os.environ.update(
    DATABASE_URL=f"sqlite:///{TEST_DB_PATH.as_posix()}",
    REDIS_URL="redis://localhost:6379/0",
    JWT_SECRET_KEY="test-secret-key",
    ACCESS_TOKEN_EXPIRE_MINUTES="60",
    BASE_URL="http://testserver",
    CELERY_TASK_ALWAYS_EAGER="true",
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import cache as cache_module  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.click import Click  # noqa: E402
from app.models.url import URL  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_PASSWORD = "password123"


@pytest.fixture(scope="session", autouse=True)
def _fake_redis():
    """Point the cache layer at an in-process fake Redis for the whole session."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    cache_module.get_redis = lambda: fake  # type: ignore[assignment]
    yield fake


@pytest.fixture(autouse=True)
def fresh_database(_fake_redis):
    """Rebuild the schema before every test and clear the cache with it."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _fake_redis.flushall()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def register(client: TestClient, email: str, password: str = TEST_PASSWORD) -> dict:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth(client):
    """A registered user plus the headers needed to call protected endpoints."""
    payload = register(client, "owner@example.com")
    token = payload["access_token"]
    return {
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "user": payload["user"],
    }


@pytest.fixture
def other_auth(client):
    """A second, unrelated user - used for cross-tenant access checks."""
    payload = register(client, "intruder@example.com")
    return {"token": payload["access_token"], "headers": {"Authorization": f"Bearer {payload['access_token']}"}}


@pytest.fixture
def make_url(client, auth):
    """Create a short URL through the API and return its response body."""

    def _make(original_url: str = "https://example.com/some/long/path", **overrides):
        body = {"original_url": original_url, **overrides}
        response = client.post("/api/urls", json=body, headers=auth["headers"])
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def as_uuid(value) -> uuid.UUID:
    """API responses carry ids as strings; the UUID column type wants a real UUID."""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def get_user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def count_clicks(db, url_id) -> int:
    """Click count read straight from the database, bypassing the API."""
    from sqlalchemy import func

    return db.scalar(select(func.count(Click.id)).where(Click.url_id == as_uuid(url_id))) or 0


def get_url_by_code(db, short_code: str) -> URL | None:
    return db.scalar(select(URL).where(URL.short_code == short_code))


def get_clicks(db, url_id) -> list[Click]:
    return list(db.scalars(select(Click).where(Click.url_id == as_uuid(url_id))))