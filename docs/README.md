# ML Trading Bot

## Overview

ML Trading Bot is a FastAPI + React system for research, signal generation, paper trading, and live execution across crypto and stocks.

### Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy async, Alembic, Redis, Celery
- Frontend: React, Vite, TypeScript
- Data stores: PostgreSQL with TimescaleDB, Redis

## Prerequisites

Install these first:
- Python 3.12+
- Node.js 20+
- PostgreSQL with TimescaleDB
- Redis
- PowerShell (`pwsh.exe`) or compatible shell

## Repository Layout

- `backend/` - FastAPI application, migrations, tests
- `frontend/` - React dashboard
- `docs/` - documentation
- `scripts/` - helper scripts

## Setup

### 1) Clone the repository

```powershell
git clone <repo-url>
cd AI-Quant
```

### 2) Backend setup

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

If you prefer installing dependencies explicitly:

```powershell
pip install fastapi celery httpx uvicorn[standard] pydantic pydantic-settings sqlalchemy[asyncio] asyncpg redis structlog alembic PyYAML
pip install mypy pytest pytest-asyncio ruff
```

### 3) Frontend setup

From `frontend/`:

```powershell
npm install
```

## Environment Variables

Create `backend/.env` with values like these:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trading_bot
REDIS_URL=redis://localhost:6379/0
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
TRADIER_API_KEY=...
TRADIER_ACCOUNT_ID=...
KRAKEN_API_KEY=...
KRAKEN_API_SECRET=...
```

Optional values may include:
- `TRADIER_BASE_URL`
- `KRAKEN_BASE_URL`
- `KRAKEN_PRIVATE_BASE_URL`
- `LOG_LEVEL`
- `ENVIRONMENT`

## Database Setup

Apply Alembic migrations from `backend/`:

```powershell
python -m alembic upgrade head
```

If the Alembic module is not on PATH, run:

```powershell
python -m alembic upgrade head
```

## Running the Application

### Backend

From `backend/`:

```powershell
uvicorn app.main:app --reload
```

### Frontend

From `frontend/`:

```powershell
npm run dev
```

## Supervisor Scripts

### Start the bot, backend, and frontend in separate Windows Terminal tabs

From the repository root:

```powershell
.\scripts\start-supervisor.ps1
```

This opens separate tabs for:
- `Bot` - Celery worker
- `Backend` - FastAPI/Uvicorn server
- `Frontend` - Vite development server

### Stop all running tabs and processes

From the repository root:

```powershell
.\scripts\stop.ps1
```

### Back up tracked files only

From the repository root:

```powershell
.\scripts\backup-tracked-files.ps1
```

## Testing

### Backend tests

From `backend/`:

```powershell
pytest
```

### Backend linting and type checks

From `backend/`:

```powershell
ruff check app tests
mypy app
```

### Frontend build

From `frontend/`:

```powershell
npm run build
```

## Notes

- The initial database schema lives in `backend/alembic/versions/20260419_0001_initial_schema.py`.
- The main FastAPI entrypoint is `backend/app/main.py`.
- The main frontend shell is `frontend/src/App.tsx`.
- Supervisor scripts live in `scripts/`.

## Troubleshooting

### Backend cannot connect to the database
- Confirm PostgreSQL and TimescaleDB are running.
- Verify `DATABASE_URL`.
- Re-run `python -m alembic upgrade head`.

### Frontend cannot reach the backend
- Confirm `uvicorn app.main:app --reload` is running.
- Check browser network requests to `/health` and `/ready`.

### Redis-related failures
- Confirm Redis is running and `REDIS_URL` is correct.

## Recommended Next Steps

- Run the backend tests.
- Run the frontend build.
- Start the backend and frontend locally.
- Connect the environment variables for broker and data API keys.
