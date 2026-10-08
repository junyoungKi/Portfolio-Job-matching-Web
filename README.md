<!--
  Author: Joonyoung Ki

  Project README: Portfolio-Job-matching-Web (Smart Job AI), an AI-powered resume-to-job matching service.
  Describes the React dashboard build, local development, server deployment with Docker and rollback.
-->
# Portfolio-Job-matching-Web









![](C:/Users/gijun/AppData/Roaming/marktext/images/2026-09-30-21-25-22-job_matching_web_locustReport.jpeg)

## Frontend (React dashboard): build and deploy

`frontend/` is a React + Vite + Tailwind dashboard. FastAPI serves `frontend/dist` at `/`, and the
API (`/stats`, `/process-resume`, `/match/{id}`, `/docs`) keeps working unchanged.

| Path | Description |
|---|---|
| `/` | The React dashboard if `frontend/dist` exists; otherwise it automatically falls back to the legacy `static/` UI |
| `/legacy` | The legacy `static/` UI (always available, for comparison and rollback checks) |
| `/docs`, `/stats`, `/process-resume`, `/match/{id}` | Existing API |

The frontend calls the API through same-origin relative paths, so `VITE_API_BASE_URL` does not need to be set (leave it empty).

### Local (including Windows)

```bash
# A) Development mode: backend + Vite dev server (uses the proxy, http://localhost:5173)
uvicorn app.main:app --port 8000        # or: python run.py
cd frontend && npm ci && npm run dev

# B) Same as production: build first, then FastAPI serves dist (http://127.0.0.1:8000)
cd frontend && npm ci && npm run build && cd ..
python run.py                           # / = React, /legacy = legacy UI
```

Without `frontend/dist`, `/` shows the legacy UI. To check with Docker, run `docker compose up -d --build` and open `http://localhost:8000`.
(Node 20.19+ / 22 recommended)

### Server (Lightsail, docker-compose v1)

The `Dockerfile` is multi-stage, so Node does not need to be installed on the server (the Node stage runs `npm ci && npm run build`, and only `frontend/dist` is copied into the Python image).

```bash
cd ~/Portfolio-Job-matching-Web          # project path
git fetch origin
git checkout cursor/frontend-dashboard-695c   # use main after the PR is merged
git pull

docker-compose down && docker-compose up -d --build
docker-compose logs -f web               # confirm "Application startup complete"
```

> If the old hyphenated `docker-compose` fails with `KeyError: 'ContainerConfig'` during `up -d --build`,
> it is a conflict with the existing container metadata. Always bring the containers down first with `docker-compose down`, then run `up -d --build`
> (do not re-run `up --build` on its own). If it persists, run `docker-compose down`, remove the leftover web container with `docker rm -f $(docker ps -aq --filter name=web)`, and run it again.

Verify the deployment:

```bash
curl -s localhost:8000/stats                 # {"total_jobs": N}
curl -sI localhost:8000/ | head -1           # 200; the React app in the browser
# Browser: http://<server-ip>:8000/ (React),  /legacy/ (legacy UI),  /docs
```

### Rollback

```bash
git log --oneline -n 10                      # find the previous good commit
git checkout <previous-commit-hash>                 # or: git checkout main
docker-compose down && docker-compose up -d --build
```

If the previous commit predates the frontend integration, `/` goes back to the legacy UI. To compare without reverting the code,
check on the deployed instance that the legacy UI still works at `/legacy/`.
