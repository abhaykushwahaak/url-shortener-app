"""Analytics summary, breakdowns, timelines and the user-agent parser."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.useragent import parse_all, parse_browser, parse_device
from app.models.click import Click


def add_clicks(db, url_id, count=1, days_ago=0, device="desktop", browser="Chrome", **extra):
    """Insert clicks directly, bypassing the API so dates can be controlled."""
    clicked_at = datetime.now(UTC) - timedelta(days=days_ago)
    for _ in range(count):
        db.add(
            Click(
                url_id=uuid.UUID(url_id) if isinstance(url_id, str) else url_id,
                clicked_at=clicked_at,
                device=device,
                browser=browser,
                ip_address=extra.get("ip_address", "10.0.0.1"),
                referrer=extra.get("referrer"),
                country=extra.get("country"),
                user_agent=extra.get("user_agent", "test-agent"),
            )
        )
    db.commit()


class TestUserAgentParsing:
    def test_chrome_on_windows_is_desktop(self):
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        )
        assert parse_all(ua) == ("desktop", "Chrome")

    def test_iphone_is_mobile_safari(self):
        ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
        )
        assert parse_all(ua) == ("mobile", "Safari")

    def test_ipad_is_tablet(self):
        ua = "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
        assert parse_device(ua) == "tablet"

    def test_edge_is_not_misread_as_chrome(self):
        """Edge's UA contains 'Chrome' - ordering of the rules matters."""
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0"
        )
        assert parse_browser(ua) == "Edge"

    def test_firefox_is_detected(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        assert parse_browser(ua) == "Firefox"

    def test_bots_are_flagged(self):
        assert parse_device("python-requests/2.31.0") == "bot"
        assert parse_device("Googlebot/2.1 (+http://www.google.com/bot.html)") == "bot"

    def test_missing_user_agent_is_unknown(self):
        assert parse_all(None) == ("unknown", "unknown")
        assert parse_all("") == ("unknown", "unknown")


class TestSummary:
    def test_totals_and_windows(self, client, auth, make_url, db):
        url = make_url("https://example.com/stats", custom_alias="stats")
        add_clicks(db, url["id"], count=3, days_ago=0)    # today (and this week)
        add_clicks(db, url["id"], count=2, days_ago=1)    # this week
        add_clicks(db, url["id"], count=4, days_ago=20)   # older

        body = client.get(f"/api/urls/{url['id']}/analytics", headers=auth["headers"]).json()

        assert body["total_clicks"] == 9
        assert body["clicks_today"] == 3
        # A Monday can make "this week" equal to "today"; assert the bound instead.
        assert body["clicks_today"] <= body["clicks_this_week"] <= 9

    def test_breakdowns_are_grouped_and_ordered(self, client, auth, make_url, db):
        url = make_url("https://example.com/breakdown")
        add_clicks(db, url["id"], count=5, device="mobile", browser="Safari", country="IN")
        add_clicks(db, url["id"], count=3, device="desktop", browser="Chrome", country="US")
        add_clicks(db, url["id"], count=1, device="desktop", browser="Chrome", country="US")

        body = client.get(f"/api/urls/{url['id']}/analytics", headers=auth["headers"]).json()

        devices = {row["key"]: row["count"] for row in body["devices"]}
        assert devices == {"mobile": 5, "desktop": 4}

        browsers = {row["key"]: row["count"] for row in body["browsers"]}
        assert browsers == {"Chrome": 4, "Safari": 5}

        # Highest count first.
        assert body["devices"][0]["key"] == "mobile"

        countries = {row["key"]: row["count"] for row in body["countries"]}
        assert countries == {"IN": 5, "US": 4}

    def test_unique_visitors_counts_distinct_ips(self, client, auth, make_url, db):
        url = make_url("https://example.com/visitors")
        add_clicks(db, url["id"], count=3, ip_address="1.1.1.1")
        add_clicks(db, url["id"], count=4, ip_address="2.2.2.2")

        body = client.get(f"/api/urls/{url['id']}/analytics", headers=auth["headers"]).json()
        assert body["total_clicks"] == 7
        assert body["unique_visitors"] == 2

    def test_first_and_last_click_timestamps(self, client, auth, make_url, db):
        url = make_url("https://example.com/window")
        add_clicks(db, url["id"], count=1, days_ago=10)
        add_clicks(db, url["id"], count=1, days_ago=1)

        body = client.get(f"/api/urls/{url['id']}/analytics", headers=auth["headers"]).json()
        assert body["first_click_at"] is not None
        assert body["last_click_at"] is not None
        assert body["first_click_at"] < body["last_click_at"]

    def test_url_with_no_clicks_returns_zeroes(self, client, auth, make_url):
        url = make_url("https://example.com/empty")
        body = client.get(f"/api/urls/{url['id']}/analytics", headers=auth["headers"]).json()

        assert body["total_clicks"] == 0
        assert body["clicks_today"] == 0
        assert body["devices"] == []
        assert body["first_click_at"] is None

    def test_analytics_for_a_missing_url_is_404(self, client, auth):
        response = client.get(
            f"/api/urls/{'0' * 8}-0000-0000-0000-000000000000/analytics",
            headers=auth["headers"],
        )
        assert response.status_code == 404


class TestTimeline:
    def test_one_point_per_day_including_empty_days(self, client, auth, make_url, db):
        url = make_url("https://example.com/timeline")
        add_clicks(db, url["id"], count=2, days_ago=2)
        add_clicks(db, url["id"], count=1, days_ago=0)

        body = client.get(
            f"/api/urls/{url['id']}/analytics/timeline?days=7", headers=auth["headers"]
        ).json()

        assert body["days"] == 7
        assert len(body["points"]) == 7

        by_date = {point["date"]: point["clicks"] for point in body["points"]}
        today = datetime.now(UTC).date().isoformat()
        assert by_date[today] == 1

        # Days with no clicks are present and zero-filled, keeping the x-axis continuous.
        assert sum(by_date.values()) == 3
        assert list(by_date.values()).count(0) == 5

    def test_points_are_in_ascending_date_order(self, client, auth, make_url, db):
        url = make_url("https://example.com/order")
        add_clicks(db, url["id"], count=1, days_ago=5)

        body = client.get(
            f"/api/urls/{url['id']}/analytics/timeline?days=10", headers=auth["headers"]
        ).json()
        dates = [point["date"] for point in body["points"]]
        assert dates == sorted(dates)

    def test_clicks_outside_the_window_are_excluded(self, client, auth, make_url, db):
        url = make_url("https://example.com/window2")
        add_clicks(db, url["id"], count=6, days_ago=40)

        body = client.get(
            f"/api/urls/{url['id']}/analytics/timeline?days=7", headers=auth["headers"]
        ).json()
        assert sum(point["clicks"] for point in body["points"]) == 0

    def test_days_parameter_is_validated(self, client, auth, make_url):
        url = make_url("https://example.com/validate")
        assert (
            client.get(
                f"/api/urls/{url['id']}/analytics/timeline?days=0", headers=auth["headers"]
            ).status_code
            == 422
        )
        assert (
            client.get(
                f"/api/urls/{url['id']}/analytics/timeline?days=9999", headers=auth["headers"]
            ).status_code
            == 422
        )

    def test_timeline_respects_ownership(self, client, auth, other_auth, make_url):
        url = make_url("https://example.com/private")
        response = client.get(
            f"/api/urls/{url['id']}/analytics/timeline", headers=other_auth["headers"]
        )
        assert response.status_code == 404


class TestClickLog:
    def test_click_log_is_paginated_and_newest_first(self, client, auth, make_url, db):
        url = make_url("https://example.com/log")
        add_clicks(db, url["id"], count=3, days_ago=1)
        add_clicks(db, url["id"], count=2, days_ago=0)

        body = client.get(
            f"/api/urls/{url['id']}/analytics/clicks?page=1&limit=2", headers=auth["headers"]
        ).json()

        assert body["total"] == 5
        assert len(body["items"]) == 2
        timestamps = [item["clicked_at"] for item in body["items"]]
        assert timestamps == sorted(timestamps, reverse=True)


class TestAccountAnalytics:
    def test_overview_aggregates_every_url(self, client, auth, make_url, db):
        first = make_url("https://example.com/a")
        second = make_url("https://example.com/b")
        add_clicks(db, first["id"], count=2)
        add_clicks(db, second["id"], count=3)

        body = client.get("/api/analytics/overview?days=7", headers=auth["headers"]).json()
        assert sum(point["clicks"] for point in body["points"]) == 5

    def test_top_urls_are_ranked_by_clicks(self, client, auth, make_url, db):
        low = make_url("https://example.com/low")
        high = make_url("https://example.com/high")
        add_clicks(db, low["id"], count=2)
        add_clicks(db, high["id"], count=9)

        body = client.get("/api/urls/top?limit=5", headers=auth["headers"]).json()
        assert body[0]["clicks"] == 9
        assert body[0]["url_id"] == high["id"]
        assert body[1]["clicks"] == 2

    def test_top_urls_excludes_other_users(self, client, auth, other_auth, make_url, db):
        mine = make_url("https://example.com/mine")
        add_clicks(db, mine["id"], count=4)

        response = client.get("/api/urls/top", headers=other_auth["headers"]).json()
        assert response == []