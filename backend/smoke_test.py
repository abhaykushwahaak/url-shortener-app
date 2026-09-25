"""End-to-end smoke test against a running server (see README for how to start one).

    python smoke_test.py [base_url]

Walks the full user journey and prints a PASS/FAIL line per step. This exercises
the real HTTP surface, so it catches things unit tests with a mocked transport
cannot - routing order, response serialisation and the live redirect path.
"""

import sys
from datetime import UTC, datetime, timedelta

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
EMAIL = f"smoke_{int(datetime.now(UTC).timestamp())}@example.com"
PASSWORD = "password123"

# A realistic browser UA, so the analytics breakdowns show real device/browser
# buckets instead of the "bot" bucket that httpx's default UA would produce.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> bool:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  [{extra}]' if extra else ''}")
    return ok


def main() -> int:
    client = httpx.Client(
        base_url=BASE,
        timeout=10,
        follow_redirects=False,
        headers={"User-Agent": BROWSER_UA, "Referer": "https://twitter.com/"},
    )

    print(f"\nSmoke test against {BASE}\n" + "=" * 60)

    # --- health ------------------------------------------------------------
    print("\n[health]")
    health = client.get("/health")
    check(health.status_code == 200, "GET /health", str(health.json()))
    check(client.get("/").status_code == 200, "GET /")
    check(client.get("/docs").status_code == 200, "GET /docs (Swagger UI)")
    check(client.get("/redoc").status_code == 200, "GET /redoc")

    # --- auth --------------------------------------------------------------
    print("\n[auth]")
    reg = client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
    check(reg.status_code == 201, "POST /api/auth/register", str(reg.status_code))
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    check(
        client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code
        == 409,
        "duplicate registration rejected with 409",
    )

    login = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    check(login.status_code == 200, "POST /api/auth/login")
    check(
        client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"}).status_code
        == 401,
        "wrong password rejected with 401",
    )

    me = client.get("/api/auth/me", headers=headers)
    check(me.status_code == 200 and me.json()["email"] == EMAIL, "GET /api/auth/me")
    check(client.get("/api/auth/me").status_code == 401, "GET /api/auth/me without token is 401")

    # --- create URLs -------------------------------------------------------
    print("\n[create urls]")
    created = client.post(
        "/api/urls",
        json={"original_url": "https://github.com/fastapi/fastapi"},
        headers=headers,
    )
    check(created.status_code == 201, "POST /api/urls (generated code)")
    generated = created.json()
    check(len(generated["short_code"]) == 6, "generated code is 6 characters")

    aliased = client.post(
        "/api/urls",
        json={
            "original_url": "https://docs.python.org/3/library/asyncio.html",
            "custom_alias": "asyncio",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    check(aliased.status_code == 201, "POST /api/urls (custom alias + expiry)")
    check(aliased.json()["short_url"].endswith("/asyncio"), "short_url uses the alias")

    check(
        client.post(
            "/api/urls",
            json={"original_url": "https://other.example.com", "custom_alias": "asyncio"},
            headers=headers,
        ).status_code
        == 409,
        "duplicate alias rejected with 409",
    )
    check(
        client.post(
            "/api/urls", json={"original_url": "https://x.example.com", "custom_alias": "ab"}, headers=headers
        ).status_code
        == 422,
        "short alias rejected with 422",
    )
    check(
        client.post(
            "/api/urls", json={"original_url": "not-a-url"}, headers=headers
        ).status_code
        == 422,
        "invalid URL rejected with 422",
    )

    # --- redirect ----------------------------------------------------------
    print("\n[redirect]")
    hit = client.get(f"/{generated['short_code']}")
    check(hit.status_code == 307, "GET /{code} redirects with 307", str(hit.status_code))
    check(
        hit.headers.get("location", "").startswith("https://github.com/fastapi/fastapi"),
        "redirects to the correct destination",
        hit.headers.get("location", ""),
    )
    check(client.get("/nope404").status_code == 404, "unknown code is 404")

    for _ in range(4):
        client.get(f"/{generated['short_code']}")

    # --- analytics ---------------------------------------------------------
    print("\n[analytics]")
    summary = client.get(f"/api/urls/{generated['id']}/analytics", headers=headers)
    check(summary.status_code == 200, "GET analytics summary")
    body = summary.json()
    check(body["total_clicks"] >= 5, "clicks recorded", f"total={body['total_clicks']}")
    check(
        body["devices"] == [{"key": "desktop", "count": body["total_clicks"]}],
        "device breakdown is parsed from the User-Agent",
        str(body["devices"]),
    )
    check(
        body["browsers"] and body["browsers"][0]["key"] == "Chrome",
        "browser breakdown detects Chrome",
        str(body["browsers"]),
    )
    check(
        body["referrers"] and body["referrers"][0]["key"] == "https://twitter.com/",
        "referrer is captured",
        str(body["referrers"]),
    )

    timeline = client.get(
        f"/api/urls/{generated['id']}/analytics/timeline?days=7", headers=headers
    )
    check(timeline.status_code == 200, "GET analytics timeline")
    check(len(timeline.json()["points"]) == 7, "timeline has 7 zero-filled points")

    log = client.get(f"/api/urls/{generated['id']}/analytics/clicks", headers=headers)
    check(log.status_code == 200 and log.json()["total"] >= 5, "GET raw click log")

    overview = client.get("/api/analytics/overview?days=7", headers=headers)
    check(overview.status_code == 200, "GET /api/analytics/overview")

    stats = client.get("/api/urls/stats", headers=headers)
    check(stats.status_code == 200, "GET /api/urls/stats", str(stats.json()))

    top = client.get("/api/urls/top", headers=headers)
    check(top.status_code == 200 and top.json()[0]["clicks"] >= 5, "GET /api/urls/top")

    # --- listing and pagination -------------------------------------------
    print("\n[listing]")
    listing = client.get("/api/urls?page=1&limit=10", headers=headers)
    check(listing.status_code == 200, "GET /api/urls")
    check(listing.json()["total"] == 2, "list returns both URLs", str(listing.json()["total"]))
    check(client.get("/api/urls?limit=9999", headers=headers).status_code == 422, "limit is capped")

    # --- update ------------------------------------------------------------
    print("\n[update]")
    patched = client.patch(
        f"/api/urls/{generated['id']}",
        json={"original_url": "https://example.com/updated-destination"},
        headers=headers,
    )
    check(patched.status_code == 200, "PATCH destination")
    moved = client.get(f"/{generated['short_code']}")
    check(
        moved.headers.get("location", "").startswith("https://example.com/updated-destination"),
        "edit invalidated the cache and the redirect follows the new destination",
        moved.headers.get("location", ""),
    )

    disabled = client.patch(
        f"/api/urls/{generated['id']}", json={"is_active": False}, headers=headers
    )
    check(disabled.status_code == 200 and disabled.json()["is_active"] is False, "PATCH disable")
    gone = client.get(f"/{generated['short_code']}")
    check(gone.status_code == 410, "disabled link returns 410", str(gone.status_code))

    client.patch(f"/api/urls/{generated['id']}", json={"is_active": True}, headers=headers)
    check(
        client.get(f"/{generated['short_code']}").status_code == 307,
        "re-enabled link redirects again",
    )

    # --- authorization boundaries -----------------------------------------
    print("\n[authorization]")
    other = httpx.Client(base_url=BASE, timeout=10, follow_redirects=False)
    other_email = f"other_{int(datetime.now(UTC).timestamp())}@example.com"
    other_token = other.post(
        "/api/auth/register", json={"email": other_email, "password": PASSWORD}
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    check(
        other.get(f"/api/urls/{generated['id']}", headers=other_headers).status_code == 404,
        "another user cannot read your URL",
    )
    check(
        other.get(f"/api/urls/{generated['id']}/analytics", headers=other_headers).status_code
        == 404,
        "another user cannot read your analytics",
    )
    check(
        other.delete(f"/api/urls/{generated['id']}", headers=other_headers).status_code == 404,
        "another user cannot delete your URL",
    )
    check(
        other.get("/api/urls", headers=other_headers).json()["total"] == 0,
        "another user sees an empty list",
    )

    # --- delete ------------------------------------------------------------
    print("\n[delete]")
    check(
        client.delete(f"/api/urls/{generated['id']}", headers=headers).status_code == 204,
        "DELETE /api/urls/{id}",
    )
    check(client.get(f"/api/urls/{generated['id']}", headers=headers).status_code == 404, "deleted URL is gone")
    check(client.get(f"/{generated['short_code']}").status_code == 404, "its short link is gone too")

    # --- summary -----------------------------------------------------------
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"{passed}/{total} checks passed")
    if passed != total:
        print("\nFailures:")
        for ok, label in results:
            if not ok:
                print(f"  - {label}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())