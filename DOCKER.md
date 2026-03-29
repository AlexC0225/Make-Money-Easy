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
- SQLite uses a bind mount from local `./data` to container `/app/data`.
- The database file used in Docker is `/app/data/app.db`, so local `data/app.db` and the container share the same file.
