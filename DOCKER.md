# Docker Usage

## Start frontend and backend

```bash
docker compose up --build
```

After startup:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Backend health check: `http://localhost:8000/health`

## Run in background

```bash
docker compose up --build -d
```

## Stop services

```bash
docker compose down
```

## Notes

- The frontend runs with Vite dev server inside Docker.
- The backend runs with FastAPI + Uvicorn inside Docker.
- Source code is mounted into the containers, so code changes should hot reload.
- Local development can keep using SQLite through `.env` with `MME_DATABASE_URL=sqlite:///./data/app.db`.
- Docker uses a dedicated PostgreSQL container with `MME_DATABASE_URL=postgresql+psycopg://mme:mme@postgres:5432/mme`.
- Docker still mounts local `./data` to `/app/data` for job logs and other local files.
- PostgreSQL data is stored in the named Docker volume `postgres_data`.
