<!--
  Author: Joonyoung Ki

  프로젝트 README (한국어): Portfolio-Job-matching-Web (Smart Job AI), 이력서 기반 AI 채용공고 매칭 서비스.
  모든 내용은 main 브랜치의 코드와 대조해 확인했습니다. TODO(owner) 표시는 직접 채우거나 확인해야 하는 항목입니다.
-->
[English](README.md) | **한국어**

# Smart Job AI (Portfolio-Job-matching-Web)

PDF 이력서를 올리면 북미 소프트웨어 채용공고 중 임베딩 유사도와 LLM 재정렬을 거친 상위 10개를 보여주고, 각 공고와의 적합도 분석을 한국어와 영어로 제공합니다.

Joonyoung Ki 제작. 미국 대학 컴퓨터공학 전공 유학생이며, 백엔드 / 일반 SWE 직무를 목표로 합니다.

- 라이브 데모: <https://ai-job-matching.com>
- 저장소: <https://github.com/junyoungKi/Portfolio-Job-matching-Web>

## 문제 정의

채용 사이트는 키워드 위주로 검색되기 때문에, 이력서와 공고를 일일이 눈으로 비교해야 합니다. 이 프로젝트는 이력서를 파싱해 의미 기반 벡터 검색으로 수집된 공고와 비교하고, 각 결과가 왜 맞는지 설명합니다. 개인 포트폴리오 프로젝트이며 상용 서비스는 아닙니다.

TODO(owner): 실제 제작 동기와 다르면 이 문단을 수정하세요.

## 데모

<!-- DEMO SCREENSHOT/GIF: insert here -->
<!-- ![대시보드 데모](docs/images/demo.gif) -->
TODO(owner): `docs/images/demo.gif`에 스크린샷 또는 GIF를 추가하세요 (이력서 업로드, 필터, 분석이 포함된 결과 화면).

## 제공 기능 (`main` 기준)

- PDF 이력서와 지역(단일 도시 또는 모든 거점 도시를 뜻하는 "North America")을 입력합니다.
- PyMuPDF로 텍스트를 추출하고 1536차원 임베딩(`text-embedding-3-small`)을 만듭니다.
- 저장된 공고에 대해 코사인 유사도로 상위 100개 후보를 검색하며, 경력 수준, 고용 형태, 기술 스택으로 필터링할 수 있습니다.
- 후보를 LLM(`gpt-4o-mini`)으로 재정렬하고 상위 10개를 반환합니다.
- 결과마다 요약과 상세 분석을 한국어/영어로 제공하며, 이력서-공고 쌍마다 한 번만 생성해 DB에 저장합니다.
- 매칭 결과를 Redis에 1시간 캐시합니다. Redis에 연결되지 않으면 캐시 없이 동작합니다.
- 백그라운드 작업: 6시간마다 LinkedIn 수집 및 AI 태깅, 매일 30일이 지난 수집 공고 삭제, 1시간이 지난 업로드 이력서 삭제.
- 한국어/영어 UI와 라이트/다크 테마를 지원하는 React 대시보드를 FastAPI가 서빙합니다. 이전 정적 UI는 `/legacy`에 남아 있습니다.

## 아키텍처

```mermaid
flowchart LR
    U[브라우저: React 대시보드] -->|POST /process-resume<br/>PDF + location| API[FastAPI]
    API -->|워커 스레드에서 파싱| P[PyMuPDF]
    API -->|텍스트 임베딩| E[OpenAI embeddings]
    API -->|이력서를 USER_UPLOAD 행으로 저장| DB[(PostgreSQL + pgvector)]
    U -->|GET /match/id| API
    API <-->|캐시, TTL 1시간| R[(Redis)]
    API -->|코사인 검색, 상위 100개<br/>embedding HNSW 인덱스| DB
    API -->|후보 재정렬<br/>gpt-4o-mini| L[OpenAI chat]
    API -->|KO/EN 분석, match_analyses에 캐시| L
    API -->|상위 10개 JSON| U
```

스케줄러 파이프라인 (APScheduler, FastAPI 프로세스 안에서 실행):

```mermaid
flowchart LR
    S1[6시간마다<br/>첫 실행은 시작 5초 후] --> C[Playwright: LinkedIn 검색 + 상세 페이지<br/>북미 8개 도시]
    C --> D{같은 LinkedIn 공고 id,<br/>또는 id 없는 기존 행의<br/>제목 + 회사 + 지역?}
    D -->|예| X[건너뜀]
    D -->|아니오| T[gpt-4o-mini: 고용 형태, 경력, 주요 기술<br/>+ 임베딩]
    T --> DB[(PostgreSQL + pgvector)]
    S2[매일 00:00] --> CL[30일 지난 수집 공고 삭제]
    S3[10분마다] --> RL[1시간 지난 USER_UPLOAD 이력서와<br/>그 매칭 분석 삭제]
    CL --> DB
    RL --> DB
```

이력서와 공고는 한 테이블(`job_postings`)에 저장됩니다. 이력서는 `company = "USER_UPLOAD"`인 행이라서 둘 다 같은 임베딩 공간에서 비교됩니다.

## 기술 스택과 선택 이유

| 구성 요소 | 용도 | 선택 이유 |
|---|---|---|
| FastAPI + uvicorn | REST API, 빌드된 대시보드 서빙 | 기본 async 지원, 타입이 있는 쿼리 파라미터로 간결한 구현 |
| SQLAlchemy(async) + asyncpg | DB 접근 | async 핸들러 안에서 DB 호출이 이벤트 루프를 막지 않음 |
| PostgreSQL + pgvector | 공고, 이력서, 임베딩, 분석 결과 | 관계형 필터와 벡터 검색을 한 DB에서 처리, 별도 벡터 저장소 불필요 |
| HNSW 인덱스 (`vector_cosine_ops`) | 유사도 검색 | 공고가 늘어날 때 전체 스캔보다 확장성이 좋은 근사 최근접 탐색 |
| Redis | 매칭 결과 캐시 | 같은 요청은 벡터 검색과 LLM 호출을 건너뜀 |
| OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) | 임베딩, 태깅, 재정렬, 분석 | 호스팅 모델이라 직접 모델을 운영할 필요 없음 |
| Playwright (Chromium) | 크롤러 | LinkedIn 페이지는 실제 브라우저 렌더링이 필요 |
| APScheduler | 수집/정리 스케줄 | 프로세스 내부 스케줄링, 별도 서비스 불필요 |
| PyMuPDF | PDF 텍스트 추출 | 빠르고 외부 의존성이 적음 |
| React 19 + TypeScript + Vite + Tailwind | 대시보드 (`frontend/`) | 타입이 있는 UI와 빠른 빌드 |
| Docker(멀티 스테이지) + Docker Compose | 패키징, 배포 | Node 단계에서 프론트를 빌드하고 `dist`만 Python 이미지에 포함 |
| Locust | 부하 테스트 | Python으로 API 시나리오를 쉽게 작성 |

## 핵심 설계 결정과 트레이드오프

- **전 구간 async.** DB 계층은 SQLAlchemy async 엔진과 asyncpg를, OpenAI 호출은 `AsyncOpenAI`를, 매칭 캐시는 애플리케이션 시작 시 만드는 `redis.asyncio` 클라이언트 하나를 씁니다. PDF 파싱은 동기 작업이라 스레드 실행기에서 돌려 이벤트 루프를 막지 않고, 세마포어(10)로 동시 파싱/임베딩 수를 제한합니다. 캐시 명령의 소켓 타임아웃은 5초라서 Redis가 멈춰도 요청이 무한정 열려 있지 않습니다.
- **HNSW 인덱스.** `app/models.py`에 `m=16`, `ef_construction=64`, 코사인 연산자로 선언했습니다. HNSW는 근사 검색이고 단순 스캔보다 메모리와 빌드 시간이 더 들기 때문에, 공고가 많을 때 효과가 있습니다. 현재 `/match` 쿼리가 계산된 `1 - cosine_distance` 점수로 정렬하기 때문에 플래너가 이 인덱스를 실제로 쓰는지는 확인하지 않았습니다: TODO(owner): `EXPLAIN ANALYZE`를 실행해 결과를 기록하세요.
- **검색 후 재정렬.** 벡터 검색으로 후보를 100개로 줄이고, LLM이 이력서 앞 500자와 각 공고의 제목, 회사, 기술 스택을 보고 순서를 정합니다. LLM 호출이 실패하면 벡터 유사도 순서를 그대로 씁니다. 단점: 요청마다 지연과 비용이 늘고, 재정렬 단계는 이력서 일부만 봅니다.
- **Redis 캐시와 분석 결과 저장.** 이력서와 필터 조합별로 결과를 1시간 캐시합니다. KO/EN 분석은 `match_analyses`에 저장해 쌍마다 한 번만 생성합니다. 단점: 캐시된 결과가 최대 1시간 지난 데이터일 수 있습니다.
- **이력서 중복 방지.** 이력서 텍스트 + location의 MD5를 `search_keyword`에 저장하고, 그 행이 남아 있는 동안 같은 조합을 다시 올리면 재임베딩 없이 기존 레코드를 반환합니다. 행이 삭제된 뒤 다시 올리면 임베딩을 다시 만듭니다. 수집된 공고는 같은 컬럼에 크롤 키워드(예: "Software Engineer")를 그대로 저장합니다.
- **이력서와 공고를 한 테이블에 저장.** 비교는 단순해지지만, 공고를 조회하는 모든 쿼리에서 `USER_UPLOAD` 행을 제외해야 합니다.

## 성능

부하 테스트(`locustfile.py`)는 `GET /stats`(가중치 2)와 `POST /process-resume`(가중치 1)를 보냅니다. 업로드는 `test_resume.pdf`와 `location=North America`를 쓰고 작업 사이에 1~3초 대기합니다. `/match/{id}`는 **호출하지 않습니다**.

모든 업로드가 같은 파일과 지역을 쓰기 때문에 첫 요청 이후에는 콘텐츠 해시 중복 검사 경로로 들어가 임베딩 호출을 건너뛸 것으로 보입니다. 따라서 아래 수치는 파싱, DB 접근, 업로드 경로의 성능이며, OpenAI 호출을 반복한 결과가 아닙니다.

<!-- LOCUST GRAPH: insert here (path: docs/images/locust-after-async.png) -->
![Locust 리포트, async 버전](docs/images/locust-after-async.jpeg)

TODO(owner): 이 이미지가 async 버전 결과로 공개할 실행이 맞는지 확인하세요 (이전에는 저장소 루트의 `job_matching_web_locustReport.jpeg`였습니다). 다른 그래프를 쓰려면 `docs/images/locust-after-async.png`로 저장하고 위 줄을 수정하세요.

| 지표 (async 버전, 사용자 100명) | 결과 |
|---|---|
| 초당 요청 수 (RPS) | TODO(owner) |
| p50 지연 | TODO(owner) |
| p95 지연 | TODO(owner) |
| 실패율 | TODO(owner) |
| 테스트 환경 (장비, 서버 실행 위치, DB 위치) | TODO(owner) |
| Locust 버전, 실행 시간, spawn rate | TODO(owner) |

<!-- 리포트 이미지에는 사용자 100명, 요청 3431건, 실패 0건, 집계 RPS 약 44.9, p50 57ms, p95 430ms로 보입니다. 해당 실행이 맞는지 확인한 뒤에만 표에 옮기세요. -->

**기준선(baseline)은 측정하지 않았습니다.** async 적용 이전 버전의 부하 테스트 결과가 없으므로, 이 README는 개선 폭에 대해 어떤 수치도 주장하지 않습니다.

아직 측정하지 않은 항목:

| 항목 | 결과 |
|---|---|
| 추천 품질 (Hit@10 / NDCG) | TODO(owner) |
| `/match` 지연 (캐시 없음 / 캐시 적중) | TODO(owner) |
| 벡터 쿼리 시간 (HNSW 사용 / 미사용) | TODO(owner) |
| 저장된 공고 수 (`GET /stats`) | TODO(owner) |
| 사용자 수 | TODO(owner) (주장하지 않음) |

## 로컬 실행

필요 조건: Python 3.11 (Dockerfile 기준), `pgvector` 확장이 설치된 PostgreSQL, OpenAI API 키, Node 20.19+ 또는 22 (대시보드 빌드에만 필요). Redis는 선택 사항입니다.

```bash
git clone https://github.com/junyoungKi/Portfolio-Job-matching-Web.git
cd Portfolio-Job-matching-Web
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                          # 크롤러를 쓸 때만 필요
```

저장소 루트에 `.env`를 만듭니다.

```bash
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/job_match
REDIS_HOST=localhost        # 선택. 기본 호스트 이름은 "redis" (Docker Compose용)
```

백엔드를 실행합니다. 시작할 때 `vector` 확장을 켜고 테이블을 만들며, 약 5초 뒤 첫 수집이 시작됩니다.

```bash
python run.py               # http://127.0.0.1:8000  (또는: uvicorn app.main:app --port 8000)
```

대시보드는 두 가지 방식 중 하나로 실행합니다.

```bash
# A) 개발 모드: Vite 개발 서버가 API를 프록시 (http://localhost:5173)
cd frontend && npm ci && npm run dev

# B) 운영과 같은 방식: 빌드 후 FastAPI가 frontend/dist를 / 에서 서빙
cd frontend && npm ci && npm run build && cd .. && python run.py
```

`frontend/dist`가 없으면 `/`는 레거시 UI로 대체됩니다. API 문서는 `/docs`, 부하 테스트는 `locust -f locustfile.py`입니다.

참고: `seed_jobs.py`는 `app/database.py`에 더 이상 없는 `SessionLocal`을 import하므로 `main`에서는 실행되지 않습니다. 크롤러가 공고를 수집할 때까지 기다리거나 다른 방법으로 공고를 넣어야 합니다.

## Docker Compose로 실행

```bash
# .env는 위와 같되, DATABASE_URL은 접근 가능한 pgvector PostgreSQL을 가리켜야 합니다.
# Caddy 프록시에는 deploy/certs/ 의 오리진 인증서 파일이 필요합니다 (배포 절 참고).
# 그 파일이 없으면 앱만 띄웁니다:
#   docker compose up -d --build web redis
docker compose up -d --build
# http://localhost:8000 은 앱에 직접 연결됩니다
# http://localhost 는 HTTPS로 리다이렉트되고, https://localhost 는 Caddy 프록시입니다
```

`docker-compose.yml`은 `web`, `redis`, `caddy`를 띄우고 PostgreSQL은 포함하지 않습니다. 데이터베이스는 `DATABASE_URL`로 직접 지정해야 합니다. `caddy`는 `"80:80"`과 `"443:443"`을 열고, 80번을 HTTPS로 리다이렉트한 뒤 compose 네트워크의 `web` 서비스 8000번 포트로 전달합니다. `web`은 인스턴스에서 직접 확인하도록 `"8000:8000"`만 열며 `"80:8000"`은 열지 않습니다. Dockerfile은 멀티 스테이지입니다. Node 22가 React 앱을 이미지에 빌드하고, Python 3.11이 uvicorn으로 FastAPI를 실행합니다. 크롤러용 Chromium도 포함됩니다.

443에 마운트하는 인증서는 Cloudflare Origin Certificate입니다. Cloudflare는 이 인증서를 신뢰하지만 브라우저와 curl은 신뢰하지 않으므로, 인스턴스 안에서는 `curl -k`로 확인합니다. 방문자에게 보이는 인증서는 이 파일이 아니라 Cloudflare의 공개 인증서입니다.

## 배포 (AWS Lightsail)

프로덕션은 AWS Lightsail 인스턴스에서 docker-compose 1.29.2로 돌아갑니다. Compose는 `web`, `redis`, `caddy`를 띄웁니다. `web`은 uvicorn으로 서빙하는 FastAPI이며, React 앱은 이미지 안에 빌드되어 있습니다. `caddy`는 Cloudflare Origin Certificate로 TLS를 종료하고 `web`으로 프록시합니다. 인스턴스 사양과 리전: TODO(owner).

공개 사이트: <https://ai-job-matching.com>

Cloudflare가 도메인을 프록시합니다 (`https://ai-job-matching.com`의 주황 구름 A 레코드). Always Use HTTPS로 HTTP를 HTTPS로 리다이렉트합니다. 방문자는 HTTPS를 사용합니다. Cloudflare가 공개 인증서에서 TLS를 종료합니다. SSL/TLS 모드는 Full (strict)로 설정되어 있습니다. 이 모드는 방문자 구간과 Cloudflare에서 Lightsail까지의 구간을 암호화하므로, 이력서 파일(계정이 생기기 전의 개인 데이터)과 이후 로그인의 자격 증명이 그 구간에서 평문으로 전송되지 않습니다. 오리진은 443번 포트에서 Cloudflare Origin Certificate를 사용합니다.

아래 순서를 지키세요. 오리진 443이 응답하기 전에 Cloudflare를 Full (strict)로 바꾸면 error 525가 납니다.

1. 오리진 인증서를 서버에 둡니다.
2. 프록시를 시작합니다.
3. `https://127.0.0.1`(오리진 443)이 동작하는지 확인합니다.
4. Lightsail에서 TCP 443을 엽니다.
5. Cloudflare SSL/TLS를 Full (strict)로 설정합니다.

2번 이후 호스트 80번은 HTTPS로 리다이렉트됩니다. Cloudflare가 아직 Flexible이면 오리진에 HTTP로 접속하므로, 5번을 끝낼 때까지 공개 사이트가 리다이렉트 루프에 빠질 수 있습니다. 인스턴스 HTTPS 확인이 되면 3–5번을 바로 이어서 하세요.

### Origin Certificate

이 존의 Cloudflare 대시보드에서 SSL/TLS → Origin Server → Create Certificate.

- 호스트 이름: `ai-job-matching.com`과 `*.ai-job-matching.com` (이 쌍이면 www와 apex가 포함됩니다. 다른 이름이 필요 없으면 `ai-job-matching.com`과 `www.ai-job-matching.com`만 적어도 됩니다).
- 인증서 키 형식: PEM.
- 더 짧게 할 이유가 없으면 기본 유효 기간을 둡니다. 개인 키는 한 번만 표시됩니다.

서버에서 저장소 루트 기준:

```bash
mkdir -p deploy/certs
# Origin Certificate 본문은 origin.pem에, Private Key는 origin-key.pem에 붙여 넣습니다.
# 예시 파일 이름 (둘 다 gitignore): deploy/certs/origin.pem, deploy/certs/origin-key.pem
chmod 644 deploy/certs/origin.pem
chmod 600 deploy/certs/origin-key.pem
```

`deploy/certs/`는 `.gitignore`와 `README.txt`를 제외하고 gitignore됩니다. 인증서와 개인 키는 커밋하지 마세요. `up` 전에 파일이 있어야 합니다. 파일이 없으면 Docker가 그 경로에 디렉터리를 만듭니다. 디렉터리를 지우고 PEM 파일을 다시 두세요.

### 배포

`main`에 병합하는 것이 배포입니다. `.github/workflows/deploy.yml`이 GitHub 호스트 러너에서 Lightsail 서버로 SSH 접속한 뒤 `deploy/lightsail.sh`를 실행합니다. 스크립트는 체크아웃을 `origin/main`으로 리셋하고, `web` 이미지를 빌드한 다음 `web`과 `caddy`를 다시 만듭니다. Redis와 `deploy/certs`는 삭제하지 않습니다 (`git reset --hard`는 gitignore된 파일을 남기고, 스크립트는 `git clean`을 하지 않으며 Redis 컨테이너도 지우지 않습니다). 스크립트가 실패하면 작업도 실패합니다. 일회성 설정은 저장소 Actions 시크릿 세 개와, 그 키 쌍의 공개 키를 서버 사용자의 `~/.ssh/authorized_keys`에 넣는 것입니다.

- `LIGHTSAIL_HOST`: 인스턴스의 공인 IP 또는 DNS
- `LIGHTSAIL_USER`: `ubuntu`
- `LIGHTSAIL_SSH_KEY`: 개인 키 PEM

개인 키, 공인 IP, 시크릿 값은 커밋하지 마세요.

인스턴스를 직접 갱신할 때:

```bash
cd ~/Portfolio-Job-matching-Web
git fetch origin && git checkout main && git pull

# docker-compose 1.29.2는 기존 컨테이너를 다시 만들 때 KeyError: 'ContainerConfig'가 납니다.
# up 전에 web 컨테이너를 docker rm으로 지웁니다. caddy가 이미 있으면 그것도 지웁니다.
# `docker-compose down -v`는 쓰지 마세요. 볼륨이 삭제됩니다.
# `docker-compose ps -q`는 서비스 단위라 디렉터리 이름에 들어 있는 "Web"과는 무관합니다.
for svc in web caddy; do
  id=$(docker-compose ps -q "$svc")
  if [ -n "$id" ]; then docker rm -f "$id"; fi
done
docker-compose up -d --build
docker-compose logs -f web             # "Application startup complete" 확인
```

Cloudflare를 바꾸기 전에 인스턴스에서 오리진 TLS를 확인합니다.

```bash
curl -s localhost:8000/stats                 # {"total_jobs": N}
curl -sI localhost:8000/ | head -1           # 200, uvicorn에 직접
curl -skI https://127.0.0.1/ | head -1       # 200, Caddy 경유 (-k: Origin CA는 공인 trust store에 없음)
curl -sI http://127.0.0.1/ | head -1         # https://127.0.0.1/ 로 301
```

Lightsail TCP 443 열기: 인스턴스 → Networking → IPv4 Firewall에서 HTTPS, TCP 443을 추가합니다. 프록시가 리다이렉트할 수 있도록 TCP 80은 열어 둡니다. 호스트 8000번은 열지 마세요. 그 매핑은 인스턴스 안의 확인용입니다.

그 다음 Cloudflare SSL/TLS → Overview를 Full (strict)로 설정합니다.

공개 사이트 확인:

```bash
curl -sI https://ai-job-matching.com/ | head -1    # 200
curl -sI http://ai-job-matching.com/ | head -1     # https://ai-job-matching.com/ 으로 301
curl -s https://ai-job-matching.com/stats          # {"total_jobs": N}
```

롤백: `git log --oneline -n 10`. 이 compose 파일이 아직 체크아웃된 상태에서 컨테이너 id를 적어둡니다 (`docker-compose ps -q web`, `docker-compose ps -q caddy`). 이전 정상 커밋으로 체크아웃한 뒤 그 id를 `docker rm -f`로 지우고 `up -d --build`를 실행합니다. `docker-compose down -v`는 쓰지 마세요. 이전 compose는 `web`이 80번을 쓰므로, 그 `up` 전에 caddy는 없어야 합니다. Cloudflare가 이미 Full (strict)이면, 오리진 80번이 다시 HTTP를 서빙한 다음에 Flexible로 되돌리세요. HTTP 오리진에 Full (strict)를 두면 error 525가 납니다. `/legacy/`는 이전 UI와 비교할 수 있도록 계속 접근 가능합니다.

## 문제 해결: 크롤러가 수집을 멈춤

공개 사이트의 `GET /stats`(`total_jobs`, 크롤된 행만, `company <> 'USER_UPLOAD'`)가 1823에서 멈춰 있었습니다. Postgres에서 그 행들의 `job_postings.created_at` 최댓값은 `2026-10-17 23:03:22`였습니다.

```sql
SELECT count(*) AS stats_count, max(created_at) AS latest
FROM job_postings
WHERE company <> 'USER_UPLOAD';
```

`docker-compose` 1.29.2의 `logs`에는 `--since`가 없습니다. `web` 컨테이너 로그에는 다음이 있었습니다.

```text
Execution of job "scheduled_north_america_crawl (trigger: interval[6:00:00], next run at: 2026-10-21 22:51:29 UTC)" skipped: maximum number of running instances reached (1)
```

크롤 한 번이 끝나지 않았습니다. 어디서 멈췄는지는 알 수 없습니다 (Playwright, OpenAI, 또는 DB 대기). `max_instances`가 1이라, 그 실행이 살아 있는 동안 6시간마다의 다음 실행은 모두 건너뛰어졌습니다.

당장 취한 조치는 `docker-compose restart web`입니다. 멈추지 않던 프로세스가 종료되었습니다. 크롤은 `2026-10-22 04:18 UTC`에 다시 시작되었습니다. 공고 수가 회복되었다는 뜻은 아니고, 아래 코드 변경이 프로덕션에서 확인되었다는 뜻도 아닙니다.

PR #19가 `main`에 병합되어 배포되면 크롤은 이렇게 바뀝니다. 도시마다 제한 시간이 있습니다 (`CRAWL_CITY_TIMEOUT_SECONDS`, 기본 1200). 한 번 전체 실행에도 6시간 간격보다 짧은 제한이 있습니다 (`CRAWL_JOB_TIMEOUT_SECONDS`, 기본 18000). Playwright의 실행, 페이지 이동, 종료와 OpenAI 클라이언트에 각각 제한 시간이 있습니다. 브라우저는 `finally`에서 닫습니다. `EPIPE` 같은 드라이버 오류는 그 도시를 끝내고 다음 도시는 계속합니다. 중복 확인과 커밋은 각각 짧은 세션을 엽니다. 풀은 `pool_pre_ping`과 `pool_recycle`(기본 1800초)을 사용합니다. 느린 await 직전에는 `[BATCH] Step {city} ({keyword}): {step}`을 찍습니다. 도시마다 수집, 저장, 중복 건너뜀, 실패 수를 찍습니다. 제한 시간을 넘기면 마지막 단계가 적힌 `[BATCH] Watchdog` 한 줄이 남습니다. 크롤 작업은 `coalesce=True`입니다 (`max_instances`는 1 유지). 중복 판별은 카드 URL에 LinkedIn 공고 id가 있으면 그 id를 씁니다. `source_job_id`가 생기기 전에 저장된 행과, URL에 id가 없는 카드는 정규화한 제목, 회사, 지역으로 비교합니다.

배포 후 서버에서:

```bash
docker-compose logs --tail=200 web
docker-compose logs --tail=500 web | grep '\[BATCH\]'
docker-compose logs --tail=200 web | grep 'maximum number of running instances'
```

`[BATCH] Starting` 다음에 `[BATCH] Step`이 나오고, 도시마다 `Collected N cards, saved X, skipped Y (duplicate), failed Z, took T s` 한 줄이 나온 뒤 `[BATCH] Finished`가 나와야 합니다. 그 프로세스의 로그에 skip 줄이 있으면 안 됩니다.

## 문제 해결: web 프로세스가 OpenSSL 안에서 SIGSEGV

이 사건은 위의 멈춘 크롤과 별개입니다. 10월 17일의 멈춤이 segfault였다는 증거는 아니고, 메모리 부족으로 죽은 것이라는 증거도 아닙니다.

2026-10-22에 `web` 컨테이너는 `2026-10-22T05:06:11Z`에 시작했습니다. 크롤 로그는 05:06:20에 실행이 시작되어 Vancouver 상세 페이지에 있었습니다. 05:12:53에 호스트 커널이 부팅 이후 유일한 segfault를 기록했습니다.

```text
[Thu Oct 22 05:12:53 2026] uvicorn[576578]: segfault at 8 ip 00007121c9b35b6d sp 000071219cff84d0 error 4 in libcrypto.so.3[3ecb6d,7121c9840000+384000] likely on CPU 1
```

`web_1`의 `docker inspect`는 종료 코드 139(128 + SIGSEGV), `OOMKilled` false, `RestartCount` 0, 컨테이너는 실행 중이 아니었습니다. 호스트 SSH는 계속 됐습니다. Redis와 Caddy는 살아 있어서, 프록시 뒤에 `web`이 없어 사이트가 오류를 반환했습니다. `error 4`는 사용자 공간 읽기입니다. 주소 8은 널 포인터에 작은 필드 오프셋을 더한 값입니다. 그 명령은 시스템 OpenSSL 3 라이브러리 `libcrypto.so.3` 안에 있습니다. 스택 포인터는 메인 스택이 아니라 스레드 스택에 있으므로, 고장난 스레드는 메인 스레드가 아닙니다. Chromium은 다른 프로세스이고, 이 줄은 `uvicorn` 프로세스입니다.

플러시된 `web` 로그의 마지막은 Vancouver의 `duplicate check` 단계와 약 40줄의 `Skipped (duplicate)`였고, `Collected ...` 요약과 Python traceback은 없었습니다. 이 코드에서 단계 줄은 조회 전에 찍히고, `Skipped (duplicate)`는 그 조회가 반환된 뒤에만 찍힙니다. 단계 줄에는 키워드도 포함됩니다. `[BATCH] Step Vancouver, BC (Software Engineer): duplicate check`. 이미지에 `PYTHONUNBUFFERED`가 없었고 Compose는 TTY를 붙이지 않으므로 Python은 stdout을 블록 버퍼링합니다. SIGSEGV는 그 버퍼를 버립니다. 이 줄들은 `docker logs`에 도달한 마지막 줄이지, 프로세스가 찍은 마지막 줄이라는 뜻은 아닙니다.

04:42 배포는 PR #19만이었고 이 고장은 나지 않았습니다. 05:05 배포가 PR #18과 PR #21을 더했습니다. pip 레이어가 캐시되어 두 배포 사이에 설치된 Python 패키지는 바뀌지 않았습니다. `Dockerfile`은 다이제스트 없는 `python:3.11-slim`입니다. `requirements.txt`는 버전을 고정하지 않습니다. 저장소에는 이미지 다이제스트나 Debian OpenSSL 패치 수준이 없습니다. 인스턴스 사양은 여기 없습니다 (위의 `TODO(owner)`).

코드에서 확인된 것: RDS는 asyncpg의 `ssl=require`로 붙고, 이는 Python `ssl`을 씁니다. OpenAI는 `AsyncOpenAI`(httpx TLS)이고 역시 Python `ssl`입니다. `hashlib.md5`(이력서 해시와 `/match` 캐시 키)는 `_hashlib`을 씁니다. 이 셋이 시스템 `libcrypto.so.3`로 들어갑니다. uvloop, asyncpg 자체 확장, httptools는 `libcrypto`에 링크되어 있지 않습니다. `app/`에서 `run_in_executor`는 `app/services/parser.py`의 PDF 파싱뿐입니다. 그 PyMuPDF 확장은 시스템 `libcrypto`에 링크되어 있지 않습니다. 크롤은 `asyncio.to_thread`를 호출하지 않습니다. `asyncio.gather`는 코루틴을 이벤트 루프 스레드에서 실행합니다. TCP keepalive 훅은 `setsockopt`만 호출합니다. 그 훅은 04:42 프로세스에 이미 있었습니다.

#18/#21이 TLS와 맞닿게 바꾼 점: 크롤러가 메타데이터와 임베딩 호출을 함께 실행하고, 동시에 최대 `LLM_MAX_CONCURRENCY`(8)개입니다. #19는 OpenAI 호출을 한 번에 하나씩 했습니다. `/match`도 한국어와 영어 분석을 같은 방식으로 함께 실행합니다. OpenSSL을 다르게 쓰는 변화로는 이것이 가장 가깝습니다. 그래도 메인 스레드가 아닌 스레드의 고장을 그 자체로 설명하지는 않으며, 이 저장소에서 크래시를 재현하지 못했습니다. 근본 원인은 단정하지 않습니다.

서버에서 커널 줄을 읽으려면:

```bash
sudo dmesg -T | grep -i segfault
```

`web`, `redis`, `caddy`는 `restart: unless-stopped`입니다. 이후 크래시가 나도 사이트를 꺼진 채로 두지 않고 컨테이너를 다시 시작합니다. 앱을 import하면 모든 스레드에 `faulthandler`가 켜지고, 다음 치명 신호에서 Python traceback을 stderr에 씁니다. stdout은 버퍼링하지 않습니다 (`PYTHONUNBUFFERED=1`).

스위치 둘은 서버 `.env`에 넣기 전에는 이전 동작을 유지합니다 (그다음 `web`을 다시 만듭니다. `docker-compose down -v`는 쓰지 마세요).

- `UVICORN_LOOP=asyncio`는 uvicorn을 `--loop asyncio`로 시작합니다. 기본값은 `uvloop`입니다.
- `DB_TCP_KEEPALIVE=0`은 연결 시 keepalive `setsockopt`를 건너뜁니다. 기본값은 켜짐입니다.

segfault가 다시 나면 먼저 `UVICORN_LOOP=asyncio`를 시도하고, 그래도 반복되면 `DB_TCP_KEEPALIVE=0`을 시도합니다. 둘 다 확인된 수정은 아닙니다.

## 한계

- 인증이 없습니다. 이력서 전문이 저장되고, `/match/{id}`는 순차 정수 id를 쓰며, CORS는 모든 출처를 허용합니다. 민감한 이력서는 올리지 마세요.
- 업로드한 이력서와 그 매칭 분석은 1시간 뒤에 삭제됩니다. 30일 정리는 수집된 공고에만 적용됩니다.
- 크롤러는 8개 도시에서 "Software Engineer"만 검색하고, 실행당 도시별로 한 페이지(카드 25개)만 읽습니다. 매칭은 이력서 임베딩, 지역, 경력/고용 형태/기술 필터를 사용합니다.
- 중복 판별은 카드 URL의 LinkedIn 공고 id를 씁니다. id가 다르면 같은 회사의 같은 제목이라도 다른 도시의 공고는 따로 저장됩니다. id가 없는 카드나, id 없이 저장된 행은 정규화한 제목, 회사, 지역으로 비교합니다.
- 연봉은 수집하지 않습니다. 수집된 모든 공고에는 "Competitive Salary"라는 고정 문구가 저장됩니다.
- LinkedIn 스크래핑은 차단되거나 HTML이 바뀌면 깨질 수 있고, 이용 약관과 충돌할 수 있습니다.
- PDF만 지원하며, 텍스트 레이어가 없는 스캔 PDF는 쓸 수 있는 텍스트가 나오지 않습니다.
- 추천 품질을 평가하지 않았고(Hit@10 / NDCG 없음) 자동화된 단위 테스트도 없습니다. `test_concurrent.py`와 `locustfile.py`는 수동 부하 스크립트입니다.
- 캐시되지 않은 결과마다 LLM을 두 번(KO, EN) 순차적으로 호출합니다.

## 로드맵

아래는 아직 병합되지 않은 열린 PR에만 있고 `main`에는 포함되지 않았습니다.

- 로그인 / 회원가입과 관심 공고 저장 (PR #7)
- 구조화된 연봉 데이터와 추가 공고 소스 (PR #8)
- Docker Compose의 PostgreSQL 서비스 (PR #2), 로컬 실행 시 Redis 연결 수정 (PR #1)

시작하지 않은 항목: 추천 품질 평가 데이터셋, 요청 속도 제한.

## 프로젝트 구조

```
app/            FastAPI 앱, 모델, 서비스 (ai, collector, parser)
frontend/       React + Vite 대시보드 (frontend/README.md 참고)
static/         /legacy 에서 서빙되는 이전 UI
Caddyfile       오리진 TLS 리버스 프록시 (Cloudflare Origin Certificate)
deploy/certs/   origin.pem, origin-key.pem (gitignore, README.txt 참고)
deploy/lightsail.sh  GitHub Actions가 실행하는 Lightsail 배포 스크립트
locustfile.py   부하 테스트
docs/images/    README 이미지
```
