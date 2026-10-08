# Smart Job AI - Frontend (React + Vite + Tailwind CSS)

Dashboard UI for the job-matching backend (FastAPI, `app/main.py`). It ports the behaviour of the
existing `static/` UI (untouched). In production FastAPI serves `frontend/dist` at `/` (multi-stage Dockerfile) and the old UI at `/legacy`; without `dist` it falls back to the old UI at `/`. See the root README for build/deploy.

Stack: React 19, TypeScript, Vite 8, Tailwind CSS v4 (`@tailwindcss/vite`), lucide-react (icons), Pretendard (font).

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
  App.tsx              state + data flow, page layout (header / hero / filter sidebar + results)
  components/          Header, Hero, Stepper, UploadCard, FileDropzone, FilterPanel (sidebar / mobile drawer),
                       StatCards, MatchList (sorting, empty/error/skeleton), MatchCard, ScoreGauge, Illustrations
  lib/                 api.ts, i18n.ts (ko/en), theme.ts (system/light/dark), salary.ts, score.ts, skills.ts
  index.css            design tokens (see below)
  types.ts             JobMatch, Filters, ...
```

## Design system

Defined in `src/index.css` as semantic CSS variables, exposed to Tailwind as `bg-surface`, `text-fg`, `border-line`, `bg-brand`, ...

- **Colour**: neutral canvas/surface/surface-2, text `fg` / `muted` / `subtle`, brand (indigo `#3b5bdb`), semantic `ok` / `warn` / `bad` (+ `-soft` tints). All text/background pairs are >= 4.5:1 in both themes.
- **Theme**: light / dark / system (follows `prefers-color-scheme`), choice saved in `localStorage` (`theme`). An inline script in `index.html` applies it before first paint (no flash).
- **Type**: Pretendard Variable (Korean + Latin, dynamic subset). Scale 12 / 14 / 16 / 18 / 20 / 24 / 28 / 44.
- **Shape**: controls 8-12px radius, cards 16px, pills full; shadows `--shadow-sm/md/lg`; 1px `--line` borders.
- **Motion**: fade-up / hover lift / animated gauge; all disabled under `prefers-reduced-motion`.
- **Sorting**: by match score (default) or salary. Salary is free text from the API, so it is parsed best-effort and the option is disabled when no job has a parsable salary.
