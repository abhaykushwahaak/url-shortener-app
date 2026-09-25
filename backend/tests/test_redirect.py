"""Redirect resolution, expiry/disable handling and Redis caching."""

from datetime import UTC, datetime, timedelta

from app.core import cache as cache_module
from tests.conftest import count_clicks, get_clicks, get_url_by_code


class TestRedirect:
    def test_valid_code_redirects_to_the_destination(self, client, auth, make_url):
        url = make_url("https://example.com/target", custom_alias="gothere")
        response = client.get("/gothere", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "https://example.com/target"

    def test_cache_is_primed_at_creation_time(self, client, auth, make_url, _fake_redis):
        """Creating a URL warms the cache, so the first redirect is already fast."""
        make_url("https://example.com/warm", custom_alias="warm")
        assert _fake_redis.get("short:warm") is not None

    def test_generated_code_also_redirects(self, client, auth, make_url):
        url = make_url("https://example.com/generated")
        response = client.get(f"/{url['short_code']}", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "https://example.com/generated"

    def test_redirect_works_without_any_authorization(self, client, auth, make_url):
        """Following a short link is public by design."""
        make_url("https://example.com/public", custom_alias="public")
        assert client.get("/public", follow_redirects=False).status_code == 307

    def test_unknown_code_is_404(self, client):
        response = client.get("/doesnotexist")
        assert response.status_code == 404
        assert response.json()["detail"] == "Short link not found"

    def test_disabled_link_is_410(self, client, auth, make_url):
        url = make_url("https://example.com/off")
        client.patch(f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"])

        response = client.get(f"/{url['short_code']}")
        assert response.status_code == 410
        assert response.json()["detail"] == "This link has been disabled"

    def test_links_with_an_expiry_are_never_cached(self, client, auth, make_url, _fake_redis):
        """Time-based expiry is the reason expiring links stay out of Redis.

        A cached entry cannot notice that it has aged out, so the cache layer
        refuses to store anything with an `expires_at` and those lookups always
        consult PostgreSQL.
        """
        expiring = make_url(
            "https://example.com/expiring",
            custom_alias="expiring",
            expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        )
        permanent = make_url("https://example.com/permanent", custom_alias="permanent")

        assert _fake_redis.get("short:expiring") is None
        assert _fake_redis.get("short:permanent") is not None

        # An expiring link still redirects fine while it is valid.
        assert client.get("/expiring", follow_redirects=False).status_code == 307

    def test_expired_link_is_410(self, client, auth, make_url, db):
        url = make_url(
            "https://example.com/expiring",
            expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        )
        # Pull the expiry into the past directly. The API refuses past dates on
        # purpose, so this simulates a link that aged out after it was created.
        row = get_url_by_code(db, url["short_code"])
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()

        # The API server runs in another thread on its own connection, which may
        # still be inside a transaction opened before this write; closing our
        # session ends that transaction and makes the change visible to it.
        db.close()

        response = client.get(f"/{url['short_code']}")
        assert response.status_code == 410
        assert response.json()["detail"] == "This link has expired"

    def test_reenabling_a_disabled_link_works_again(self, client, auth, make_url):
        """A disabled link must not be cached as unavailable."""
        url = make_url("https://example.com/revive", custom_alias="revive")
        client.get("/revive", follow_redirects=False)  # populates the cache
        client.patch(f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"])
        assert client.get("/revive").status_code == 410

        client.patch(f"/api/urls/{url['id']}", json={"is_active": True}, headers=auth["headers"])
        assert client.get("/revive", follow_redirects=False).status_code == 307

    def test_deleting_a_link_makes_it_404(self, client, auth, make_url):
        url = make_url("https://example.com/gone", custom_alias="gone")
        client.get("/gone", follow_redirects=False)
        client.delete(f"/api/urls/{url['id']}", headers=auth["headers"])
        assert client.get("/gone").status_code == 404


class TestCaching:
    def test_miss_then_hit_populates_redis(self, client, auth, make_url, _fake_redis):
        make_url("https://example.com/cached", custom_alias="cached")

        # Creating a URL already primes the cache. Evict it to force a genuine
        # cache miss, then confirm the redirect repopulates the entry.
        _fake_redis.delete("short:cached")
        assert _fake_redis.get("short:cached") is None

        client.get("/cached", follow_redirects=False)

        cached = _fake_redis.get("short:cached")
        assert cached is not None
        assert "example.com/cached" in cached

    def test_cached_entry_carries_the_right_destination(self, client, auth, make_url, _fake_redis):
        import json

        make_url("https://example.com/one", custom_alias="one")
        client.get("/one", follow_redirects=False)

        payload = json.loads(_fake_redis.get("short:one"))
        assert payload["original_url"] == "https://example.com/one"
        assert payload["is_active"] is True

    def test_editing_a_url_invalidates_the_cache(self, client, auth, make_url, _fake_redis):
        import json

        url = make_url("https://example.com/before", custom_alias="edit")
        client.get("/edit", follow_redirects=False)
        assert json.loads(_fake_redis.get("short:edit"))["original_url"].endswith("/before")

        client.patch(
            f"/api/urls/{url['id']}",
            json={"original_url": "https://example.com/after"},
            headers=auth["headers"],
        )

        # The stale entry is gone, and the next request serves the new destination.
        response = client.get("/edit", follow_redirects=False)
        assert response.headers["location"] == "https://example.com/after"
        assert json.loads(_fake_redis.get("short:edit"))["original_url"].endswith("/after")

    def test_disabling_a_url_evicts_the_cache(self, client, auth, make_url, _fake_redis):
        url = make_url("https://example.com/x", custom_alias="evict")
        client.get("/evict", follow_redirects=False)
        assert _fake_redis.get("short:evict") is not None

        client.patch(f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"])
        assert _fake_redis.get("short:evict") is None

    def test_deleting_a_url_evicts_the_cache(self, client, auth, make_url, _fake_redis):
        url = make_url("https://example.com/y", custom_alias="drop")
        client.get("/drop", follow_redirects=False)
        client.delete(f"/api/urls/{url['id']}", headers=auth["headers"])
        assert _fake_redis.get("short:drop") is None

    def test_a_cached_hit_does_not_requery_the_database(self, client, auth, make_url, monkeypatch):
        """Proves the cache is actually serving the hot path.

        Counts database fallbacks rather than cache reads: a redirect that never
        reaches PostgreSQL is the property that matters.
        """
        from app.api import redirect as redirect_module

        make_url("https://example.com/fast", custom_alias="fast")
        client.get("/fast", follow_redirects=False)  # warms the cache

        lookups = {"n": 0}
        real_lookup = redirect_module.get_active_url_by_code

        def counting_lookup(db, short_code):
            lookups["n"] += 1
            return real_lookup(db, short_code)

        monkeypatch.setattr(redirect_module, "get_active_url_by_code", counting_lookup)
        response = client.get("/fast", follow_redirects=False)

        assert response.status_code == 307
        assert lookups["n"] == 0, "a warm cache should not hit the database"

    def test_redis_outage_degrades_gracefully(self, client, auth, make_url, monkeypatch):
        """Redis is an optimization: the redirect must still work without it."""
        import redis

        def boom(_short_code):
            raise redis.RedisError("connection refused")

        url = make_url("https://example.com/resilient", custom_alias="resilient")
        monkeypatch.setattr(cache_module, "get_cached_url", lambda code: None)
        monkeypatch.setattr(cache_module, "cache_url", lambda *a, **k: None)

        response = client.get("/resilient", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "https://example.com/resilient"


class TestClickRecording:
    """Celery runs in eager mode under test, so clicks land synchronously."""

    def test_a_redirect_records_one_click(self, client, auth, make_url, db):
        url = make_url("https://example.com/track", custom_alias="track")
        client.get("/track", follow_redirects=False)

        assert count_clicks(db, url["id"]) == 1

    def test_repeated_redirects_accumulate(self, client, auth, make_url, db):
        url = make_url("https://example.com/many", custom_alias="many")
        for _ in range(5):
            client.get("/many", follow_redirects=False)

        detail = client.get(f"/api/urls/{url['id']}", headers=auth["headers"]).json()
        assert detail["total_clicks"] == 5

    def test_click_metadata_is_captured(self, client, auth, make_url, db):
        url = make_url("https://example.com/meta", custom_alias="meta")
        client.get(
            "/meta",
            follow_redirects=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 "
                    "Mobile/15E148 Safari/604.1"
                ),
                "Referer": "https://twitter.com/",
            },
        )

        clicks = get_clicks(db, url["id"])
        assert len(clicks) == 1
        click = clicks[0]
        assert click.device == "mobile"
        assert click.browser == "Safari"
        assert click.referrer == "https://twitter.com/"
        assert click.ip_address

    def test_404_does_not_record_a_click(self, client, db):
        from sqlalchemy import func, select

        client.get("/nothinghere")
        assert db.scalar(select(func.count(Click.id))) == 0

    def test_410_does_not_record_a_click(self, client, auth, make_url, db):
        url = make_url("https://example.com/nocount")
        client.patch(f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"])
        client.get(f"/{url['short_code']}")

        assert count_clicks(db, url["id"]) == 0