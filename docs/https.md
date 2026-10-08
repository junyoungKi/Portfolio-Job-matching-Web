# HTTPS 적용 가이드 (Caddy + Let's Encrypt)

<!-- Author: Joonyoung Ki -->
<!-- Purpose: Step-by-step guide (Korean text, English commands) for enabling HTTPS on the Lightsail server. -->

이 문서는 도메인을 연결해 `https://내도메인` 으로 서비스하는 방법을 설명합니다.
**Caddy** 라는 프록시 컨테이너가 80/443 포트를 받아 `web:8000` 으로 전달하고,
Let's Encrypt 인증서를 **자동으로 발급/갱신**합니다. 인증서를 직접 다룰 필요가 없습니다.

- 옵트인 방식입니다. `docker-compose.https.yml` 을 함께 지정하지 않으면 기존처럼 `http://<서버IP>:8000` 으로 동작합니다.
- 서버는 AWS Lightsail Ubuntu + 구버전 `docker-compose` (하이픈 버전) 기준입니다.

## 전체 순서 요약

1. 도메인 준비 (유료 또는 무료 DuckDNS)
2. Lightsail **고정 IP** 할당
3. DNS **A 레코드**를 고정 IP로 설정
4. Lightsail **방화벽**에서 80, 443 열기
5. 서버 `.env` 에 `DOMAIN` 추가
6. 서버에서 HTTPS 파일과 함께 실행
7. 확인

## 1. 도메인 구하기

| 방법 | 비용 | 비고 |
| --- | --- | --- |
| 도메인 등록 업체 (가비아, Namecheap, Cloudflare Registrar, Route 53 등) | 연 1~2만 원대 | 가장 안정적. `example.com` 같은 형태 |
| [DuckDNS](https://www.duckdns.org) | 무료 | `내이름.duckdns.org` 형태. 학습/포트폴리오용으로 충분 |

DuckDNS 사용법: 사이트에 GitHub/Google 계정으로 로그인 → 원하는 서브도메인 입력 후 `add domain` →
`current ip` 칸에 3번 단계의 **Lightsail 고정 IP**를 입력하고 `update ip`.
(DuckDNS는 이 과정이 곧 A 레코드 설정이므로 3번 단계를 대신합니다.)

## 2. Lightsail 고정 IP 할당

고정 IP가 없으면 인스턴스를 재시작할 때 IP가 바뀌어 DNS가 깨집니다.

1. Lightsail 콘솔 → **Networking** → **Create static IP**
2. 인스턴스를 선택해 연결(attach)하고 이름을 정해 생성
3. 표시된 IP 주소(예: `3.35.xxx.xxx`)를 메모

## 3. DNS A 레코드 설정

도메인 등록 업체(또는 DNS 서비스)의 DNS 관리 화면에서:

| 타입 | 이름(호스트) | 값 |
| --- | --- | --- |
| A | `@` (루트 도메인) 또는 `www` 등 원하는 서브도메인 | 2번에서 메모한 고정 IP |

- 서브도메인 하나만 써도 됩니다. 이 경우 `DOMAIN` 에는 그 전체 이름(예: `app.example.com`)을 씁니다.
- 같은 이름에 CNAME 이나 다른 A 레코드가 남아 있으면 삭제하세요.
- AAAA(IPv6) 레코드가 있다면 서버가 IPv6를 받도록 설정돼 있지 않은 한 삭제하세요.
- 전파에는 보통 몇 분, 길면 몇 시간 걸립니다. 확인:

```bash
dig +short 내도메인.com        # 고정 IP가 출력되면 OK
# dig 가 없으면: nslookup 내도메인.com
```

## 4. Lightsail 방화벽 열기

Lightsail 콘솔 → 인스턴스 → **Networking** 탭 → **IPv4 Firewall** 에서 규칙 추가:

| Application | Protocol | Port |
| --- | --- | --- |
| HTTP | TCP | 80 |
| HTTPS | TCP | 443 |

- **80 포트도 반드시 열어야 합니다.** 인증서 발급 확인(HTTP-01)과 http→https 리다이렉트에 쓰입니다.
- (선택) HTTP/3 를 쓰려면 Custom / UDP / 443 도 추가합니다. 없어도 동작합니다.
- **8000 포트 규칙은 HTTPS 적용 후 삭제**하세요. 8000을 열어 두면 HTTPS를 우회해 접속할 수 있습니다.
- `6379`(Redis) 포트는 인터넷에 열려 있으면 안 됩니다. 규칙에 있다면 삭제하세요.

## 5. 서버 설정 (`.env`)

서버에 SSH 접속 후 프로젝트 폴더에서 `.env` 파일 끝에 도메인을 추가합니다 (`https://` 없이 도메인만).

```bash
cd ~/Portfolio-Job-matching-Web
echo 'DOMAIN=app.example.com' >> .env
tail -n 3 .env     # 확인 (비밀 값이 들어 있으니 화면 공유 시 주의)
```

`DOMAIN` 이 비어 있으면 Caddy가 시작되지 않습니다. 오타가 없는지 꼭 확인하세요.

## 6. 실행

이 PR/브랜치의 코드가 서버에 있어야 합니다 (`git pull`).

```bash
git fetch origin
git pull

# 구버전 docker-compose 에서는 먼저 down 하는 것이 안전합니다 (KeyError: 'ContainerConfig' 예방)
docker-compose -f docker-compose.yml -f docker-compose.https.yml down
docker-compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

> `-f` 옵션 두 개는 **매번 똑같이** 붙여야 합니다. 빼고 실행하면 caddy 가 빠진 채로 다시 뜹니다.
> 편하게 쓰려면 `alias dch='docker-compose -f docker-compose.yml -f docker-compose.https.yml'` 처럼 별칭을 만들어도 됩니다.

> `KeyError: 'ContainerConfig'` 가 나면 `down` 을 먼저 실행하고, 계속되면 남은 컨테이너를 지운 뒤
> (`docker rm -f $(docker ps -aq --filter name=web)`) 다시 `up -d --build` 하세요.

## 7. 확인

```bash
docker-compose -f docker-compose.yml -f docker-compose.https.yml ps      # web, redis, caddy 모두 Up
docker-compose -f docker-compose.yml -f docker-compose.https.yml logs caddy | tail -n 30
curl -I https://내도메인.com                  # HTTP/2 200 (또는 앱이 주는 정상 응답)
curl -I http://내도메인.com                   # 308 Permanent Redirect -> https://...
```

브라우저에서 `https://내도메인.com` 을 열었을 때 주소창에 자물쇠가 보이면 성공입니다.
첫 접속 직후 몇 초~1분 정도는 인증서 발급 중이라 오류가 날 수 있으니 잠시 후 다시 시도하세요.

## 인증서 발급이 안 될 때 점검

먼저 로그를 봅니다.

```bash
docker-compose -f docker-compose.yml -f docker-compose.https.yml logs caddy
```

| 증상 / 로그 | 원인 | 조치 |
| --- | --- | --- |
| `NXDOMAIN`, `no such host`, `DNS problem` | DNS 미전파 또는 오타 | `dig +short 내도메인.com` 이 고정 IP를 가리키는지 확인. 아니면 A 레코드 수정 후 대기 |
| `Timeout during connect`, `connection refused` | 방화벽에서 80/443 이 막힘 | Lightsail IPv4 Firewall 의 80, 443 규칙 확인. 서버 내부 방화벽(`sudo ufw status`)이 켜져 있으면 `sudo ufw allow 80,443/tcp` |
| `too many failed authorizations` / `rate limit` | 짧은 시간에 실패 반복 | 원인을 고친 뒤 1시간 정도 기다렸다가 재시도 (Let's Encrypt 제한) |
| caddy 컨테이너가 바로 종료됨 | `DOMAIN` 미설정/오타 | `.env` 의 `DOMAIN` 확인 후 `up -d` 재실행 |
| `bind: address already in use` | 80/443 을 다른 프로그램이 사용 중 | `sudo ss -ltnp \| grep -E ':80\|:443'` 로 확인 후 해당 프로세스 중지 (예: 호스트에 설치된 nginx/apache) |
| 502 Bad Gateway | `web` 이 아직 안 떴거나 오류 | `docker-compose ... logs web` 확인 |
| DuckDNS 에서 실패 | IP 미등록 | DuckDNS 에서 `current ip` 가 고정 IP인지 확인 |

수정 후 재시도: `docker-compose -f docker-compose.yml -f docker-compose.https.yml restart caddy`

인증서는 `caddy_data` 볼륨에 저장되어 컨테이너를 재생성해도 유지되고, 만료 전에 자동 갱신됩니다.
`docker-compose down -v` 는 이 볼륨까지 지우므로 사용하지 마세요.

## 앱 쪽 참고 사항 (개발자용)

- `docker-compose.https.yml` 은 `web` 의 실행 명령을 override 하여 uvicorn 에 `--proxy-headers --forwarded-allow-ips "*"` 를 붙입니다
  (Dockerfile 은 수정하지 않음). 덕분에 앱은 프록시가 보내는 `X-Forwarded-Proto: https` 를 믿고
  `request.url.scheme == "https"`, 올바른 클라이언트 IP 로 인식합니다.
- **쿠키 `Secure` 플래그**: 로그인 기능에서 세션/토큰 쿠키에 `Secure` 를 켜면 **HTTPS 에서만** 쿠키가 전송됩니다.
  따라서 HTTPS 적용 후에 `Secure` 를 켜야 하고, `http://<IP>:8000` 으로 접속하는 로컬/롤백 환경에서는
  로그인이 유지되지 않을 수 있습니다 (환경변수로 `Secure` 를 끄고 켤 수 있게 만드는 것을 권장).
  `SameSite=Lax`, `HttpOnly` 도 함께 설정하세요.
- `--forwarded-allow-ips "*"` 는 8000 포트가 인터넷에 닫혀 있다는 전제입니다. 8000 이 열려 있으면 외부에서
  `X-Forwarded-*` 헤더를 위조할 수 있습니다. (compose 는 `ports` 목록을 병합하므로 override 에서 8000 매핑을 제거할 수 없어서,
  방화벽으로 막는 방식을 사용합니다.)

## 롤백 (HTTPS 끄고 원래대로)

```bash
docker-compose -f docker-compose.yml -f docker-compose.https.yml down
docker-compose up -d --build              # https 파일 없이 원래 명령
```

- 다시 `http://<서버IP>:8000` 으로 접속합니다 (Lightsail 방화벽에서 8000 을 이미 닫았다면 다시 열어야 합니다).
- `.env` 의 `DOMAIN` 줄은 남겨 둬도 무해합니다.
- 인증서 볼륨까지 정리하려면 (선택): `docker volume rm $(docker volume ls -q | grep caddy_)`

## 검증 범위 안내

이 설정은 다음까지만 사전 검증되었습니다: `Caddyfile` 문법(`caddy validate`), compose 파일 병합 결과(`docker compose config`).
실제 도메인과 서버가 없어 **인증서 발급 및 실서버 동작은 검증되지 않았습니다.** 위 7번의 확인 절차로 직접 확인해 주세요.
