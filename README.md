# URL Shortener & Analytics

A full-stack URL shortener with JWT authentication, Redis caching, Celery async tasks, and a React analytics dashboard.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend API** | FastAPI 0.141 · Python 3.14 |
| **Database** | SQLite (dev) · PostgreSQL (prod) via SQLAlchemy 2 + Alembic |
| **Cache** | Redis 8 (circuit-breaker fallback when unavailable) |
| **Async tasks** | Celery 5 (click recording runs off the hot path) |
| **Auth** | JWT (PyJWT) · bcrypt password hashing |
| **Frontend** | React 18 · TypeScript · Vite 6 · Tailwind CSS 3 |
| **Charts** | Recharts 2 |
| **Routing** | React Router 6 |

---

## Project Structure

```
URL_Shortener/
├── backend/
│   ├── app/
│   │   ├── api/          # Route handlers (auth, urls, analytics, redirect)
│   │   ├── core/         # Config, database, cache, security, Celery, UA parser
│   │   ├── models/       # SQLAlchemy ORM models (User, ShortURL, Click)
│   │   ├── schemas/      # Pydantic request / response schemas
│   │   ├── services/     # Business logic (auth, url, analytics)
│   │   ├── tasks/        # Celery tasks (async click recording)
│   │   ├── main.py       # FastAPI app + lifespan
│   │   └── seed.py       # Dev seed data
│   ├── tests/            # pytest suite (46 tests)
│   ├── alembic/          # DB migrations
│   ├── requirements.txt
│   ├── alembic.ini
│   └── pytest.ini
└── frontend/
    ├── src/
    │   ├── components/   # Layout, StatCard, Charts, States, StatusBadge
    │   ├── context/      # AuthContext (JWT storage + /me validation)
    │   ├── lib/          # api.ts (typed fetch wrapper), format.ts
    │   ├── pages/        # LoginPage, DashboardPage, URLsPage, AnalyticsPage
    │   ├── App.tsx       # Router + RequireAuth guard
    │   ├── main.tsx      # React entry point
    │   └── types.ts      # Shared TypeScript types
    ├── index.html
    ├── vite.config.ts
    ├── tailwind.config.js
    └── package.json
```

---

## Quick Start (Development)

### Prerequisites

- **Python 3.12+** with `venv`
- **Node.js 18+**
- **Redis** *(optional — app degrades gracefully without it)*

### 1 — Backend

```powershell
# From URL_Shortener/backend
python -m venv ../.venv
../.venv/Scripts/python.exe -m pip install -r requirements.txt

# Run with SQLite (zero config)
$env:DATABASE_URL = "sqlite:///./dev.db"
$env:BASE_URL      = "http://localhost:8000"
$env:CELERY_TASK_ALWAYS_EAGER = "true"   # run tasks inline, no worker needed

../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload
```

API docs → **http://localhost:8000/docs**

### 2 — Frontend

```powershell
# From URL_Shortener/frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` in `frontend/.env` to the backend origin (for example,
`http://localhost:8000`), then open **http://localhost:5173**. The browser calls
the backend directly, so configure `CORS_ORIGINS` on the backend to allow the
frontend origin.

---

## Environment Variables

All variables have safe defaults for local SQLite development. Override via environment or a `.env` file inside `backend/`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./urlshortener.db` | SQLAlchemy connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (optional) |
| `BASE_URL` | `http://localhost:8000` | Prepended to short codes in responses |
| `JWT_SECRET_KEY` | `dev-secret-change-me` | **Change in production** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 24 hours |
| `SHORT_CODE_LENGTH` | `6` | Length of auto-generated codes |
| `CACHE_TTL_SECONDS` | `3600` | Redis TTL per short code |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | Set `true` to skip the worker in dev |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |

---

## API Overview

All protected endpoints require `Authorization: Bearer <token>`.

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create account → returns JWT |
| `POST` | `/api/auth/login` | Login → returns JWT |
| `GET` | `/api/auth/me` | Current user info |

### URLs
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/urls` | Create short URL |
| `GET` | `/api/urls` | List my URLs (paginated, filterable) |
| `GET` | `/api/urls/{id}` | Get single URL |
| `PATCH` | `/api/urls/{id}` | Update (destination, alias, active, expiry) |
| `DELETE` | `/api/urls/{id}` | Delete URL |
| `GET` | `/api/urls/stats` | Aggregate counts for dashboard |
| `GET` | `/api/urls/top` | Top N URLs by clicks |

### Analytics
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/urls/{id}/analytics` | Summary: clicks, devices, browsers, referrers |
| `GET` | `/api/urls/{id}/analytics/timeline` | Daily click counts (`?days=30`) |
| `GET` | `/api/urls/{id}/analytics/clicks` | Paginated raw click log |
| `GET` | `/api/analytics/overview` | Account-wide daily timeline |

### Redirect
| Method | Path | Description |
|---|---|---|
| `GET` | `/{short_code}` | Redirect → records click async via Celery |

---

## Frontend Pages

| Route | Page | Description |
|---|---|---|
| `/login` | Login / Register | Toggle between sign-in and sign-up |
| `/` | Dashboard | Stats cards, click timeline, top URLs chart |
| `/urls` | My URLs | Table with search, filter, create, edit, copy, delete |
| `/urls/:id/analytics` | Analytics | Per-URL stats, timeline, device/browser/referrer breakdowns, click log |

---

## Running Tests

```powershell
# From URL_Shortener/backend
../.venv/Scripts/python.exe -m pytest -q
```

46 tests cover:
- Auth (register, login, JWT validation, duplicate email)
- URL CRUD (create, list, update, delete, pagination, search)
- Redirect (cache hit, cache miss, expired, disabled, 404)
- Analytics (summary, timeline, click log, top URLs)
- Redis caching (15 checks over a real socket)

---

## Production Notes

1. **Use PostgreSQL** — set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`
2. **Run Alembic migrations** — `alembic upgrade head` before first start
3. **Start a Celery worker** — `celery -A app.core.celery_app worker -l info`
4. **Set a real `JWT_SECRET_KEY`** — at least 32 random bytes
5. **Point `BASE_URL`** to your public domain — e.g. `https://short.example.com`
6. **Serve the frontend build** via nginx or a CDN — `npm run build` → `dist/`

---

## License

MIT
