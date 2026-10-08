<!--
  Author: Joonyoung Ki

  프로젝트 README (한국어): Portfolio-Job-matching-Web (Smart Job AI), 이력서 기반 AI 채용공고 매칭 서비스.
  모든 내용은 main 브랜치의 코드와 대조해 확인했습니다. TODO(owner) 표시는 직접 채우거나 확인해야 하는 항목입니다.
-->
[English](README.md) | **한국어**

# Smart Job AI (Portfolio-Job-matching-Web)

PDF 이력서를 올리면 북미 소프트웨어 채용공고 중 임베딩 유사도와 LLM 재정렬을 거친 상위 10개를 보여주고, 각 공고와의 적합도 분석을 한국어와 영어로 제공합니다.

Joonyoung Ki 제작. 미국 대학 컴퓨터공학 전공 유학생이며, 백엔드 / 일반 SWE 직무를 목표로 합니다.

- 라이브 데모: TODO(owner): URL 또는 "비공개"
- 저장소: <https://github.com/junyoungKi/Portfolio-Job-matching-Web>

## 문제 정의

채용 사이트는 키워드 위주로 검색되기 때문에, 이력서와 공고를 일일이 눈으로 비교해야 합니다. 이 프로젝트는 이력서를 파싱해 의미 기반 벡터 검색으로 수집된 공고와 비교하고, 각 결과가 왜 맞는지 설명합니다. 개인 포트폴리오 프로젝트이며 상용 서비스는 아닙니다.

TODO(owner): 실제 제작 동기와 다르면 이 문단을 수정하세요.

## 데모

<!-- DEMO SCREENSHOT/GIF: insert here -->
<!-- ![대시보드 데모](docs/images/demo.gif) -->
TODO(owner): `docs/images/demo.gif`에 스크린샷 또는 GIF를 추가하세요 (이력서 업로드, 필터, 분석이 포함된 결과 화면).

## 제공 기능 (`main` 기준)

- PDF 이력서, 희망 직무, 지역(단일 도시 또는 모든 거점 도시를 뜻하는 "North America")을 입력합니다.
- PyMuPDF로 텍스트를 추출하고 1536차원 임베딩(`text-embedding-3-small`)을 만듭니다.
- 저장된 공고에 대해 코사인 유사도로 상위 100개 후보를 검색하며, 경력 수준, 고용 형태, 기술 스택으로 필터링할 수 있습니다.
- 후보를 LLM(`gpt-4o-mini`)으로 재정렬하고 상위 10개를 반환합니다.
- 결과마다 요약과 상세 분석을 한국어/영어로 제공하며, 이력서-공고 쌍마다 한 번만 생성해 DB에 저장합니다.
- 매칭 결과를 Redis에 1시간 캐시합니다. Redis에 연결되지 않으면 캐시 없이 동작합니다.
- 백그라운드 작업: 6시간마다 LinkedIn 수집 및 AI 태깅, 매일 오래된 공고 정리.
- 한국어/영어 UI와 라이트/다크 테마를 지원하는 React 대시보드를 FastAPI가 서빙합니다. 이전 정적 UI는 `/legacy`에 남아 있습니다.

## 아키텍처

```mermaid
flowchart LR
    U[브라우저: React 대시보드] -->|POST /process-resume<br/>PDF + keyword + location| API[FastAPI]
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
    C --> D{같은 제목과 회사가<br/>이미 저장돼 있는가?}
    D -->|예| X[건너뜀]
    D -->|아니오| T[gpt-4o-mini: 고용 형태, 경력, 주요 기술<br/>+ 임베딩]
    T --> DB[(PostgreSQL + pgvector)]
    S2[매일 00:00] --> CL[30일 지난 공고 삭제<br/>USER_UPLOAD 이력서는 유지]
    CL --> DB
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

- **전 구간 async.** DB 계층은 SQLAlchemy async 엔진과 asyncpg, OpenAI 호출은 `AsyncOpenAI`를 씁니다. PDF 파싱은 동기 작업이라 스레드 실행기에서 돌려 이벤트 루프를 막지 않고, 세마포어(10)로 동시 파싱/임베딩 수를 제한합니다. 단점: `app/main.py`의 Redis 클라이언트는 동기식 `redis` 패키지라서 캐시 호출 동안 이벤트 루프가 잠깐 멈춥니다.
- **HNSW 인덱스.** `app/models.py`에 `m=16`, `ef_construction=64`, 코사인 연산자로 선언했습니다. HNSW는 근사 검색이고 단순 스캔보다 메모리와 빌드 시간이 더 들기 때문에, 공고가 많을 때 효과가 있습니다. 현재 `/match` 쿼리가 계산된 `1 - cosine_distance` 점수로 정렬하기 때문에 플래너가 이 인덱스를 실제로 쓰는지는 확인하지 않았습니다: TODO(owner): `EXPLAIN ANALYZE`를 실행해 결과를 기록하세요.
- **검색 후 재정렬.** 벡터 검색으로 후보를 100개로 줄이고, LLM이 이력서 앞 500자와 각 공고의 제목, 회사, 기술 스택을 보고 순서를 정합니다. LLM 호출이 실패하면 벡터 유사도 순서를 그대로 씁니다. 단점: 요청마다 지연과 비용이 늘고, 재정렬 단계는 이력서 일부만 봅니다.
- **Redis 캐시와 분석 결과 저장.** 이력서와 필터 조합별로 결과를 1시간 캐시합니다. KO/EN 분석은 `match_analyses`에 저장해 쌍마다 한 번만 생성합니다. 단점: 캐시된 결과가 최대 1시간 지난 데이터일 수 있습니다.
- **이력서 중복 방지.** 이력서 텍스트 + keyword + location의 MD5를 `search_keyword`에 저장하고, 같은 조합을 다시 올리면 재임베딩 없이 기존 레코드를 반환합니다.
- **이력서와 공고를 한 테이블에 저장.** 비교는 단순해지지만, 공고를 조회하는 모든 쿼리에서 `USER_UPLOAD` 행을 제외해야 합니다.

## 성능

부하 테스트(`locustfile.py`)는 `GET /stats`(가중치 2)와 `POST /process-resume`(가중치 1)를 보냅니다. 업로드는 `test_resume.pdf`, `keyword=Software Engineer`, `location=North America`를 쓰고 작업 사이에 1~3초 대기합니다. `/match/{id}`는 **호출하지 않습니다**.

모든 업로드가 같은 파일, 키워드, 지역을 쓰기 때문에 첫 요청 이후에는 콘텐츠 해시 중복 검사 경로로 들어가 임베딩 호출을 건너뛸 것으로 보입니다. 따라서 아래 수치는 파싱, DB 접근, 업로드 경로의 성능이며, OpenAI 호출을 반복한 결과가 아닙니다.

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
# .env는 위와 같되, DATABASE_URL은 접근 가능한 pgvector PostgreSQL을 가리켜야 합니다
docker compose up -d --build
# http://localhost:8000 접속
```

`main`의 `docker-compose.yml`은 `web`과 `redis`만 띄우고 PostgreSQL은 포함하지 않습니다. 데이터베이스는 `DATABASE_URL`로 직접 지정해야 합니다. Dockerfile은 멀티 스테이지입니다 (Node 22로 대시보드 빌드, Python 3.11에서 크롤러용 Chromium과 함께 API 실행).

## 배포 (AWS Lightsail)

AWS Lightsail 인스턴스에서 docker-compose v1로 배포합니다 (인스턴스 사양과 리전: TODO(owner)).

```bash
cd ~/Portfolio-Job-matching-Web
git fetch origin && git checkout main && git pull
docker-compose down && docker-compose up -d --build
docker-compose logs -f web             # "Application startup complete" 확인
```

`up -d --build` 전에 반드시 `down`을 먼저 실행하세요. 그렇지 않으면 구버전 `docker-compose`에서 `KeyError: 'ContainerConfig'`가 날 수 있습니다. 계속되면 남은 컨테이너를 지웁니다: `docker rm -f $(docker ps -aq --filter name=web)`.

확인:

```bash
curl -s localhost:8000/stats           # {"total_jobs": N}
curl -sI localhost:8000/ | head -1     # 200
```

롤백: `git log --oneline -n 10`으로 이전 정상 커밋을 찾아 체크아웃한 뒤 `down`, `up -d --build`를 다시 실행합니다. `/legacy/`는 이전 UI와 비교할 수 있도록 계속 접근 가능합니다. 문서화된 구성은 8000번 포트의 HTTP입니다 (HTTPS는 아래 로드맵 항목일 뿐입니다).

## 한계

- 인증이 없습니다. 이력서 전문이 저장되고, `/match/{id}`는 순차 정수 id를 쓰며, CORS는 모든 출처를 허용합니다. 민감한 이력서는 올리지 마세요.
- 업로드한 이력서는 삭제되지 않습니다. 30일 정리는 수집된 공고에만 적용됩니다.
- 크롤러는 8개 도시에서 "Software Engineer"만 검색하고, 실행당 도시별로 한 페이지(카드 25개)만 읽습니다. UI에 입력하는 희망 직무 키워드는 이력서 중복 판별에만 쓰이고 검색에는 쓰이지 않습니다.
- 중복 판별은 제목과 회사가 정확히 같은지만 보기 때문에, 서로 다른 도시의 같은 직무는 하나로 취급됩니다.
- 연봉은 수집하지 않습니다. 수집된 모든 공고에는 "Competitive Salary"라는 고정 문구가 저장됩니다.
- LinkedIn 스크래핑은 차단되거나 HTML이 바뀌면 깨질 수 있고, 이용 약관과 충돌할 수 있습니다.
- PDF만 지원하며, 텍스트 레이어가 없는 스캔 PDF는 쓸 수 있는 텍스트가 나오지 않습니다.
- 추천 품질을 평가하지 않았고(Hit@10 / NDCG 없음) 자동화된 단위 테스트도 없습니다. `test_concurrent.py`와 `locustfile.py`는 수동 부하 스크립트입니다.
- 캐시되지 않은 결과마다 LLM을 두 번(KO, EN) 순차적으로 호출합니다.

## 로드맵

아래는 아직 병합되지 않은 열린 PR에만 있고 `main`에는 포함되지 않았습니다.

- 로그인 / 회원가입과 관심 공고 저장 (PR #7)
- 구조화된 연봉 데이터와 추가 공고 소스 (PR #8)
- Caddy 리버스 프록시를 통한 선택형 HTTPS (PR #5)
- Docker Compose의 PostgreSQL 서비스 (PR #2), 로컬 실행 시 Redis 연결 수정 (PR #1)
- `main` 병합 시 Lightsail 자동 배포 (PR #4)

시작하지 않은 항목: 추천 품질 평가 데이터셋, 요청 속도 제한, async Redis 클라이언트.

## 프로젝트 구조

```
app/            FastAPI 앱, 모델, 서비스 (ai, collector, parser)
frontend/       React + Vite 대시보드 (frontend/README.md 참고)
static/         /legacy 에서 서빙되는 이전 UI
locustfile.py   부하 테스트
docs/images/    README 이미지
```
