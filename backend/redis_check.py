"""Verify the Redis caching layer end to end, over a real socket.

    python redis_check.py

Starts an in-process Redis-protocol server (fakeredis' TCP server) on port 6379,
points the app at it and checks the full lifecycle: prime on create, serve from
cache without touching PostgreSQL, TTL, and invalidation on edit/disable/delete.

This complements tests/test_redirect.py, which stubs Redis in-process. Here the
real `redis-py` client, connection pool and serialisation are exercised.
"""

import os
import sys
import threading
import time

PORT = int(os.environ.get("FAKE_REDIS_PORT", "6379"))

os.environ.update(
    DATABASE_URL="sqlite:///./redis_check.db",
    REDIS_URL=f"redis://127.0.0.1:{PORT}/0",
    BASE_URL="http://localhost:8000",
    JWT_SECRET_KEY="redis-check-secret-key",
    CELERY_TASK_ALWAYS_EAGER="true",
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
)

from fakeredis import TcpFakeServer  # noqa: E402

server = TcpFakeServer(("127.0.0.1", PORT), server_type="redis")
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(0.5)

from sqlalchemy import text  # noqa: E402

from app.core.cache import get_redis  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  [{extra}]' if extra else ''}")


def main() -> int:
    redis = get_redis()
    print(f"\nRedis cache check (port {PORT})\n" + "=" * 60)

    check(redis.ping() is True, "connected to Redis and PING succeeded")

    with TestClient(app) as client:
        check(client.get("/health").json()["redis"] is True, "/health reports redis=true")

        token = client.post(
            "/api/auth/register", json={"email": "cache@example.com", "password": "password123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        url = client.post(
            "/api/urls",
            json={"original_url": "https://example.com/cached-target", "custom_alias": "cached"},
            headers=headers,
        ).json()

        print("\n[cache lifecycle]")
        check(redis.get("short:cached") is not None, "creating a URL primes the cache")
        check(redis.ttl("short:cached") > 0, "the cache entry has a TTL", f"{redis.ttl('short:cached')}s")

        import json

        check(
            json.loads(redis.get("short:cached"))["original_url"].endswith("/cached-target"),
            "cached payload holds the destination",
        )

        redis.delete("short:cached")
        check(redis.get("short:cached") is None, "entry can be evicted to force a miss")

        response = client.get("/cached", follow_redirects=False)
        check(response.status_code == 307, "redirect works on a cache miss")
        check(redis.get("short:cached") is not None, "the miss repopulates the cache")

        print("\n[served from cache, not from PostgreSQL]")
        db = SessionLocal()
        db.execute(
            text(
                "UPDATE urls SET original_url = 'https://CHANGED-IN-DATABASE.example.com' "
                "WHERE short_code = 'cached'"
            )
        )
        db.commit()
        db.close()

        hit = client.get("/cached", follow_redirects=False)
        check(
            hit.headers["location"].startswith("https://example.com/cached-target"),
            "the cached copy was served, not the changed database row",
            hit.headers["location"],
        )

        print("\n[invalidation]")
        client.patch(
            f"/api/urls/{url['id']}",
            json={"original_url": "https://example.com/after-edit"},
            headers=headers,
        )
        after = client.get("/cached", follow_redirects=False)
        check(
            after.headers["location"].startswith("https://example.com/after-edit"),
            "editing a URL invalidates the cache",
            after.headers["location"],
        )

        client.patch(f"/api/urls/{url['id']}", json={"is_active": False}, headers=headers)
        check(redis.get("short:cached") is None, "disabling a URL evicts the cache")
        check(client.get("/cached").status_code == 410, "the disabled link returns 410")
        check(
            redis.get("short:cached") is None,
            "the disabled state is not cached (so re-enabling works)",
        )

        client.patch(f"/api/urls/{url['id']}", json={"is_active": True}, headers=headers)
        check(client.get("/cached", follow_redirects=False).status_code == 307, "re-enabled link redirects")

        client.delete(f"/api/urls/{url['id']}", headers=headers)
        check(redis.get("short:cached") is None, "deleting a URL evicts the cache")

    passed = sum(1 for ok, _ in results if ok)
    print("\n" + "=" * 60)
    print(f"{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    code = main()
    server.shutdown()
    sys.stdout.flush()
    # The fake server's handler threads would otherwise keep the process alive.
    os._exit(code)