# Portfolio-Job-matching-Web









![](C:/Users/gijun/AppData/Roaming/marktext/images/2026-09-30-21-25-22-job_matching_web_locustReport.jpeg)


## 실행 방법

### 환경 변수
`.env.example` 을 `.env` 로 복사하고 `DATABASE_URL`, `OPENAI_API_KEY` 등을 채웁니다.

### Redis 설정 (선택)
Redis는 매칭 결과 캐시용이며, **없어도 앱은 정상 동작**합니다 (연결 실패 시 경고 한 줄 출력 후 캐시만 비활성화).

접속 주소 우선순위: `REDIS_URL` > `REDIS_HOST`/`REDIS_PORT` > 기본값 `redis://localhost:6379/0`

- **로컬 직접 실행 (`python run.py`)**: 기본값이 `localhost` 이므로 로컬에 Redis만 떠 있으면 됩니다.
  - Docker Desktop(Windows): `docker run -d --name redis -p 6379:6379 redis:latest`
  - 또는 WSL2: `sudo apt install redis-server && sudo service redis-server start`
  - 다른 주소를 쓰려면 PowerShell: `$env:REDIS_URL="redis://localhost:6379/0"; python run.py` 또는 `.env` 에 `REDIS_URL` 지정
  - 주의: `.env` 에 `REDIS_HOST=redis` 가 있으면 로컬에서 `getaddrinfo failed` 가 발생하므로 삭제하거나 `localhost` 로 바꾸세요.
- **docker compose**: `docker compose up --build` — `docker-compose.yml` 이 `REDIS_URL=redis://redis:6379/0` 을 주입합니다.

### AWS Lightsail 배포 시 Redis
저장소에는 Lightsail 전용 배포 스크립트가 없고 `Dockerfile` / `docker-compose.yml` 만 있습니다.

- **(a) 인스턴스에서 `docker compose up -d --build`**: compose가 `REDIS_URL=redis://redis:6379/0` 을 주입하고 `redis` 서비스가 같은 네트워크에 뜨므로 **추가 설정 없이 연결됩니다.** (`.env` 에는 `DATABASE_URL`, `OPENAI_API_KEY` 만 있으면 됩니다.) 보안을 위해 Redis 포트(6379)는 Lightsail 방화벽에서 열지 말고, 필요하면 compose의 `ports` 를 `127.0.0.1:6379:6379` 로 제한하세요.
- **(b) 인스턴스에서 직접 `python run.py`**: 같은 호스트에 Redis가 있어야 합니다. `sudo apt install redis-server` 로 설치하면 기본값(`localhost`)으로 **추가 설정 없이 연결됩니다.** 별도 Redis(ElastiCache 등)를 쓰면 `.env` 에 `REDIS_URL=redis://<호스트>:6379/0` 을 지정하세요. Redis가 없으면 캐시 없이 동작합니다.
  - 참고: `run.py` 는 `127.0.0.1:8000` 에만 바인딩하므로 외부에서 접속하려면 `host="0.0.0.0"` 로 바꾸거나 리버스 프록시(nginx)를 사용해야 합니다.
