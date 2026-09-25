"""Seed the database with demo data.

    python -m app.seed

Creates 2 users, 10 URLs and a few weeks of click history so the dashboard has
something to show on first run. Safe to re-run: it wipes the seeded users first.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.core.useragent import parse_all
from app.models.click import Click
from app.models.url import URL
from app.models.user import User

DEMO_PASSWORD = "password123"

DEMO_USERS = [
    ("demo@example.com", "Demo User"),
    ("abhay@example.com", "Abhay Sharma"),
]

DEMO_URLS = [
    ("https://github.com/fastapi/fastapi", "fastapi", None, True),
    ("https://docs.python.org/3/library/asyncio.html", "asyncio", None, True),
    ("https://www.postgresql.org/docs/current/index.html", None, None, True),
    ("https://redis.io/docs/latest/develop/", "redisdocs", None, True),
    ("https://docs.celeryq.dev/en/stable/", None, None, True),
    ("https://react.dev/learn", "reactlearn", None, True),
    ("https://www.typescriptlang.org/docs/handbook/intro.html", None, None, True),
    ("https://tailwindcss.com/docs/installation", None, None, False),
    ("https://recharts.org/en-US/api", "charts", -5, True),  # expired 5 days ago
    ("https://roadmap.sh/backend", "backend", 90, True),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0",
]

REFERRERS = [
    "https://www.google.com/",
    "https://twitter.com/",
    "https://www.linkedin.com/",
    "https://news.ycombinator.com/",
    None,
]

COUNTRIES = ["US", "IN", "DE", "GB", "BR", None]


def seed() -> None:
    # Mirrors the app's startup convenience: create tables if missing.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        emails = [email for email, _ in DEMO_USERS]
        existing = list(db.scalars(select(User).where(User.email.in_(emails))))
        if existing:
            print(f"Removing {len(existing)} existing demo user(s) and their data...")
            for user in existing:
                db.delete(user)  # URLs and clicks cascade
            db.commit()

        users: list[User] = []
        for email, _name in DEMO_USERS:
            user = User(email=email, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            users.append(user)
        db.commit()
        for user in users:
            db.refresh(user)

        print(f"Created {len(users)} users (password: {DEMO_PASSWORD})")

        created_urls: list[URL] = []
        for index, (original_url, alias, expires_in_days, is_active) in enumerate(DEMO_URLS):
            owner = users[index % len(users)]
            expires_at = (
                datetime.now(UTC) + timedelta(days=expires_in_days)
                if expires_in_days is not None
                else None
            )
            url = URL(
                id=uuid.uuid4(),
                user_id=owner.id,
                original_url=original_url,
                short_code=alias or f"sd{index}k{random.choice('xyzpq')}",
                custom_alias=alias,
                is_active=is_active,
                expires_at=expires_at,
                created_at=datetime.now(UTC) - timedelta(days=random.randint(5, 40)),
            )
            db.add(url)
            created_urls.append(url)
        db.commit()
        for url in created_urls:
            db.refresh(url)

        print(f"Created {len(created_urls)} URLs")

        # Weighted so the dashboard has a clear "top link" instead of a flat chart.
        weights = [30, 22, 18, 14, 10, 8, 6, 4, 0, 3]
        now = datetime.now(UTC)
        clicks: list[Click] = []
        for url, weight in zip(created_urls, weights, strict=True):
            for _ in range(weight * 3):
                days_ago = random.choices(
                    range(0, 30), weights=[30, 20, 12, 8, 6, 5, 4, 3, 2, 2] + [1] * 20
                )[0]
                clicked_at = now - timedelta(
                    days=days_ago,
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )
                ua = random.choice(USER_AGENTS)
                device, browser = parse_all(ua)
                clicks.append(
                    Click(
                        url_id=url.id,
                        clicked_at=clicked_at,
                        ip_address=f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}",
                        user_agent=ua,
                        device=device,
                        browser=browser,
                        referrer=random.choice(REFERRERS),
                        country=random.choice(COUNTRIES),
                    )
                )
        db.add_all(clicks)
        db.commit()

        print(f"Created {len(clicks)} click records")
        print("\nSeed complete. Log in with any of:")
        for email, _ in DEMO_USERS:
            print(f"  {email} / {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()