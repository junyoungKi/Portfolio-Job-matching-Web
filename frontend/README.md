# Smart Job AI - Frontend (React + Vite + Tailwind CSS)

Dashboard UI for the job-matching backend (FastAPI, `app/main.py`). It ports the behaviour of the
existing `static/` UI (which is untouched and still served by FastAPI at `/`).

Stack: React 19, TypeScript, Vite 8, Tailwind CSS v4 (`@tailwindcss/vite`).

## Run (development)

```bash
# 1) backend (repo root), listening on 127.0.0.1:8000
uvicorn app.main:app --port 8000      # or: docker compose up

# 2) frontend
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

`/stats`, `/process-resume` and `/match` are proxied to `http://127.0.0.1:8000` by Vite (see `vite.config.ts`).

## Build / check

```bash
npm run build     # tsc -b && vite build -> frontend/dist
npm run lint
npm run preview
```

## Configuration

| Variable | Description |
|---|---|
| `VITE_API_BASE_URL` | Backend origin used by the built app (e.g. `https://api.example.com`). Leave empty to call the same origin / the dev proxy. See `.env.example`. |

When the build is hosted on a different origin than the API, the backend must allow it via CORS
(currently `allow_origins=["*"]`).

## API used

- `GET /stats` -> `{ total_jobs }`
- `POST /process-resume?keyword=&location=` (multipart `file`) -> `{ status, id, ... }`
- `GET /match/{id}?levels=&types=&skills=` -> `JobMatch[]` (types in `src/types.ts`)

## Layout

```
src/
  App.tsx              state + data flow
  components/          Header, UploadForm, FileDropzone, FilterPanel, MatchList, MatchCard
  lib/                 api.ts (fetch + error handling), i18n.ts (ko/en), skills.ts
  types.ts             JobMatch, Filters, ...
```
