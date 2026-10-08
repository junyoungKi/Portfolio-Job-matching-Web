# Portfolio-Job-matching-Web









![](C:/Users/gijun/AppData/Roaming/marktext/images/2026-09-30-21-25-22-job_matching_web_locustReport.jpeg)

## Frontend (React dashboard) 빌드 & 배포

`frontend/`는 React + Vite + Tailwind 대시보드입니다. FastAPI가 `frontend/dist`를 `/`에서 서빙하고,
API(`/stats`, `/process-resume`, `/match/{id}`, `/docs`)는 그대로 동작합니다.

| 경로 | 내용 |
|---|---|
| `/` | `frontend/dist`가 있으면 React 대시보드, 없으면 기존 `static/` UI로 자동 fallback |
| `/legacy` | 기존 `static/` UI (항상 접근 가능, 비교/롤백 확인용) |
| `/docs`, `/stats`, `/process-resume`, `/match/{id}` | 기존 API |

프론트엔드는 같은 오리진의 상대경로로 API를 호출하므로 `VITE_API_BASE_URL` 설정이 필요 없습니다(비워 두세요).

### 로컬 (Windows 포함)

```bash
# A) 개발 모드: 백엔드 + Vite dev server (프록시 사용, http://localhost:5173)
uvicorn app.main:app --port 8000        # 또는 python run.py
cd frontend && npm ci && npm run dev

# B) 운영과 동일한 방식: 빌드 후 FastAPI가 dist 서빙 (http://127.0.0.1:8000)
cd frontend && npm ci && npm run build && cd ..
python run.py                           # / = React, /legacy = 기존 UI
```

`frontend/dist`가 없으면 `/`는 기존 UI로 보입니다. Docker로 확인하려면 `docker compose up -d --build` 후 `http://localhost:8000`.
(Node 20.19+ / 22 권장)

### 서버 (Lightsail, docker-compose v1)

`Dockerfile`이 멀티스테이지라서 서버에 Node를 설치할 필요가 없습니다(Node 스테이지에서 `npm ci && npm run build` 후 `frontend/dist`만 Python 이미지로 복사).

```bash
cd ~/Portfolio-Job-matching-Web          # 프로젝트 경로
git fetch origin
git checkout cursor/frontend-dashboard-695c   # PR 머지 후에는 main
git pull

docker-compose down && docker-compose up -d --build
docker-compose logs -f web               # "Application startup complete" 확인
```

> 구버전 `docker-compose`(하이픈)에서 `up -d --build` 도중 `KeyError: 'ContainerConfig'`가 나면
> 기존 컨테이너 메타데이터 충돌입니다. 반드시 `docker-compose down` 으로 컨테이너를 먼저 내린 뒤 `up -d --build` 하세요
> (`up --build`만 단독으로 재실행하지 마세요). 계속되면 `docker-compose down` 후 `docker rm -f $(docker ps -aq --filter name=web)` 로 남은 web 컨테이너를 지우고 다시 실행합니다.

배포 확인:

```bash
curl -s localhost:8000/stats                 # {"total_jobs": N}
curl -sI localhost:8000/ | head -1           # 200, 브라우저에서 React 화면
# 브라우저: http://<서버IP>:8000/  (React),  /legacy/ (기존 UI),  /docs
```

### 롤백

```bash
git log --oneline -n 10                      # 이전 정상 커밋 확인
git checkout <이전-커밋-해시>                 # 또는 git checkout main
docker-compose down && docker-compose up -d --build
```

이전 커밋에 프론트엔드 통합이 없던 시점이면 `/`가 기존 UI로 돌아갑니다. 코드를 되돌리지 않고 비교만 하려면
배포된 상태에서 `/legacy/` 로 기존 UI가 그대로 동작하는지 확인하세요.
