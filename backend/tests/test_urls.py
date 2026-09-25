"""URL creation, listing, updating, deletion and authorization boundaries."""

from datetime import UTC, datetime, timedelta

from tests.conftest import get_url_by_code


class TestCreateURL:
    def test_generates_a_six_character_code(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com/very/long/path"},
            headers=auth["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body["short_code"]) == 6
        assert body["short_url"].endswith(body["short_code"])
        assert body["custom_alias"] is None
        assert body["is_active"] is True
        assert body["is_expired"] is False
        assert body["total_clicks"] == 0

    def test_custom_alias_is_used_as_the_code(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://github.com/user/repo", "custom_alias": "github"},
            headers=auth["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert body["custom_alias"] == "github"
        assert body["short_code"] == "github"
        assert body["short_url"] == "http://testserver/github"

    def test_duplicate_alias_is_rejected(self, client, auth):
        client.post(
            "/api/urls",
            json={"original_url": "https://a.example.com", "custom_alias": "taken"},
            headers=auth["headers"],
        )
        response = client.post(
            "/api/urls",
            json={"original_url": "https://b.example.com", "custom_alias": "taken"},
            headers=auth["headers"],
        )
        assert response.status_code == 409
        assert "already taken" in response.json()["detail"]

    def test_generated_codes_are_unique(self, client, auth):
        codes = {
            client.post(
                "/api/urls",
                json={"original_url": f"https://example.com/{i}"},
                headers=auth["headers"],
            ).json()["short_code"]
            for i in range(25)
        }
        assert len(codes) == 25

    def test_expiration_in_the_past_is_rejected(self, client, auth):
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "expires_at": past},
            headers=auth["headers"],
        )
        assert response.status_code == 422
        assert "must be in the future" in response.text

    def test_future_expiration_is_saved(self, client, auth):
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "expires_at": future},
            headers=auth["headers"],
        )
        assert response.status_code == 201
        assert response.json()["expires_at"] is not None

    def test_invalid_url_is_rejected(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "javascript:alert(1)"},
            headers=auth["headers"],
        )
        assert response.status_code == 422


class TestAliasValidation:
    def test_alias_that_is_too_short_is_rejected(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "custom_alias": "ab"},
            headers=auth["headers"],
        )
        assert response.status_code == 422

    def test_alias_with_illegal_characters_is_rejected(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "custom_alias": "bad alias!"},
            headers=auth["headers"],
        )
        assert response.status_code == 422

    def test_reserved_alias_is_rejected(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "custom_alias": "docs"},
            headers=auth["headers"],
        )
        assert response.status_code == 422

    def test_alias_with_valid_symbols_is_accepted(self, client, auth):
        response = client.post(
            "/api/urls",
            json={"original_url": "https://example.com", "custom_alias": "my_link-2026"},
            headers=auth["headers"],
        )
        assert response.status_code == 201


class TestListURLs:
    def test_list_is_scoped_to_the_owner(self, client, auth, other_auth):
        client.post(
            "/api/urls", json={"original_url": "https://mine.example.com"}, headers=auth["headers"]
        )
        client.post(
            "/api/urls",
            json={"original_url": "https://theirs.example.com"},
            headers=other_auth["headers"],
        )

        body = client.get("/api/urls", headers=auth["headers"]).json()
        assert body["total"] == 1
        # Pydantic's AnyHttpUrl normalises a bare domain to an explicit root path.
        assert body["items"][0]["original_url"] == "https://mine.example.com/"

    def test_pagination_metadata_and_slices(self, client, auth):
        for i in range(15):
            client.post(
                "/api/urls",
                json={"original_url": f"https://example.com/page/{i}"},
                headers=auth["headers"],
            )

        first = client.get("/api/urls?page=1&limit=10", headers=auth["headers"]).json()
        assert first["page"] == 1 and first["limit"] == 10 and first["total"] == 15
        assert len(first["items"]) == 10

        second = client.get("/api/urls?page=2&limit=10", headers=auth["headers"]).json()
        assert len(second["items"]) == 5
        # Pages must not overlap.
        assert {u["id"] for u in first["items"]}.isdisjoint({u["id"] for u in second["items"]})

    def test_limit_is_capped_at_100(self, client, auth):
        response = client.get("/api/urls?limit=5000", headers=auth["headers"])
        assert response.status_code == 422

    def test_invalid_page_is_rejected(self, client, auth):
        assert client.get("/api/urls?page=0", headers=auth["headers"]).status_code == 422

    def test_filter_by_active_state(self, client, auth, make_url):
        active = make_url("https://active.example.com")
        disabled = make_url("https://disabled.example.com")
        client.patch(
            f"/api/urls/{disabled['id']}", json={"is_active": False}, headers=auth["headers"]
        )

        inactive = client.get("/api/urls?is_active=false", headers=auth["headers"]).json()
        assert [u["short_code"] for u in inactive["items"]] == [disabled["short_code"]]

        only_active = client.get("/api/urls?is_active=true", headers=auth["headers"]).json()
        assert [u["short_code"] for u in only_active["items"]] == [active["short_code"]]

    def test_search_matches_destination_or_code(self, client, auth, make_url):
        make_url("https://github.com/fastapi/fastapi", custom_alias="fastapi")

        by_url = client.get("/api/urls?search=github", headers=auth["headers"]).json()
        assert by_url["total"] == 1

        by_code = client.get("/api/urls?search=fastapi", headers=auth["headers"]).json()
        assert by_code["total"] == 1

        none = client.get("/api/urls?search=nothinghere", headers=auth["headers"]).json()
        assert none["total"] == 0

    def test_stats_endpoint(self, client, auth, make_url):
        make_url("https://one.example.com")
        two = make_url("https://two.example.com")
        client.patch(f"/api/urls/{two['id']}", json={"is_active": False}, headers=auth["headers"])

        stats = client.get("/api/urls/stats", headers=auth["headers"]).json()
        assert stats["total_urls"] == 2
        assert stats["active_urls"] == 1
        assert stats["total_clicks"] == 0


class TestUpdateURL:
    def test_destination_can_be_changed(self, client, auth, make_url):
        url = make_url("https://old.example.com")
        response = client.patch(
            f"/api/urls/{url['id']}",
            json={"original_url": "https://new.example.com"},
            headers=auth["headers"],
        )
        assert response.status_code == 200
        assert response.json()["original_url"] == "https://new.example.com/"

    def test_disable_and_reenable(self, client, auth, make_url):
        url = make_url("https://toggle.example.com")

        off = client.patch(
            f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"]
        ).json()
        assert off["is_active"] is False

        on = client.patch(
            f"/api/urls/{url['id']}", json={"is_active": True}, headers=auth["headers"]
        ).json()
        assert on["is_active"] is True

    def test_partial_update_leaves_other_fields_alone(self, client, auth, make_url):
        url = make_url("https://keep.example.com", custom_alias="keeper")
        updated = client.patch(
            f"/api/urls/{url['id']}", json={"is_active": False}, headers=auth["headers"]
        ).json()
        assert updated["custom_alias"] == "keeper"
        assert updated["original_url"] == url["original_url"]

    def test_adding_an_alias_renames_the_short_code(self, client, auth, make_url):
        url = make_url("https://rename.example.com")
        original_code = url["short_code"]
        assert original_code != "renamed"

        updated = client.patch(
            f"/api/urls/{url['id']}", json={"custom_alias": "renamed"}, headers=auth["headers"]
        ).json()
        assert updated["short_code"] == "renamed"
        assert updated["custom_alias"] == "renamed"

    def test_alias_collision_on_update_is_rejected(self, client, auth, make_url):
        make_url("https://first.example.com", custom_alias="occupied")
        second = make_url("https://second.example.com")

        response = client.patch(
            f"/api/urls/{second['id']}",
            json={"custom_alias": "occupied"},
            headers=auth["headers"],
        )
        assert response.status_code == 409

    def test_update_missing_url_is_404(self, client, auth):
        response = client.patch(
            f"/api/urls/{'0' * 8}-0000-0000-0000-000000000000",
            json={"is_active": False},
            headers=auth["headers"],
        )
        assert response.status_code == 404


class TestDeleteURL:
    def test_delete_then_get_is_404(self, client, auth, make_url):
        url = make_url("https://delete.example.com")
        assert client.delete(f"/api/urls/{url['id']}", headers=auth["headers"]).status_code == 204
        assert client.get(f"/api/urls/{url['id']}", headers=auth["headers"]).status_code == 404

    def test_delete_missing_url_is_404(self, client, auth):
        response = client.delete(
            f"/api/urls/{'0' * 8}-0000-0000-0000-000000000000", headers=auth["headers"]
        )
        assert response.status_code == 404


class TestAuthorization:
    def test_every_endpoint_requires_a_token(self, client):
        assert client.get("/api/urls").status_code == 401
        assert client.post("/api/urls", json={"original_url": "https://example.com"}).status_code == 401
        assert client.get(f"/api/urls/{'0' * 8}-0000-0000-0000-000000000000").status_code == 401
        assert client.get(f"/api/urls/{'0' * 8}-0000-0000-0000-000000000000/analytics").status_code == 401
        assert client.get("/api/urls/stats").status_code == 401

    def test_another_user_cannot_read_update_or_delete(self, client, auth, other_auth, make_url):
        url = make_url("https://private.example.com")

        assert client.get(f"/api/urls/{url['id']}", headers=other_auth["headers"]).status_code == 404
        assert (
            client.patch(
                f"/api/urls/{url['id']}", json={"is_active": False}, headers=other_auth["headers"]
            ).status_code
            == 404
        )
        assert client.delete(f"/api/urls/{url['id']}", headers=other_auth["headers"]).status_code == 404

        # ...and the owner's URL is untouched by those attempts.
        assert client.get(f"/api/urls/{url['id']}", headers=auth["headers"]).status_code == 200

    def test_another_user_cannot_read_analytics(self, client, auth, other_auth, make_url):
        url = make_url("https://private.example.com")
        response = client.get(f"/api/urls/{url['id']}/analytics", headers=other_auth["headers"])
        assert response.status_code == 404

    def test_another_user_cannot_reuse_your_alias(self, client, auth, other_auth, make_url):
        make_url("https://mine.example.com", custom_alias="mineonly")
        response = client.post(
            "/api/urls",
            json={"original_url": "https://theirs.example.com", "custom_alias": "mineonly"},
            headers=other_auth["headers"],
        )
        assert response.status_code == 409