# 자동 배포 가이드 (GitHub Actions → AWS Lightsail)

`main` 브랜치에 코드가 합쳐(머지)지면 GitHub가 자동으로 Lightsail 서버에 접속해서
새 코드를 받아오고(`git pull`), 서버를 다시 빌드/시작(`docker-compose`)합니다.

> 워크플로 파일: `.github/workflows/deploy.yml`
> 아래 **1~3단계 설정을 하기 전에는 배포가 "건너뜀(skip)" 처리**되므로 아무 영향이 없습니다.

## 동작 순서

1. `main`에 머지(또는 Actions 탭에서 수동 실행)
2. 서버에 SSH 접속 → `git pull --ff-only origin main`
3. `docker-compose down` → `docker-compose up -d --build`
   (구버전 docker-compose의 `ContainerConfig` 오류를 피하려고 항상 `down` 후 `up` 합니다)
4. 서버 안에서 `http://localhost:8000/docs`(안 되면 `/stats`)가 HTTP 200인지 최대 약 2.5분간 확인
5. 실패하면 **이전 커밋으로 자동 롤백** 후 다시 빌드/확인하고, 워크플로는 실패(빨간 X)로 표시

서버의 `.env`는 서버에 있는 파일을 그대로 사용합니다. 저장소/GitHub에는 비밀값을 넣지 않습니다.

---

## 1단계. 배포 전용 SSH 키 만들기

내 컴퓨터(Mac/리눅스는 터미널, Windows는 PowerShell)에서 실행합니다. 비밀번호(passphrase)는 **비워두세요**(엔터).

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f github_deploy_key
```

현재 폴더에 두 파일이 생깁니다.

- `github_deploy_key` : **개인키** (비밀! GitHub에만 등록, 다른 곳에 공유 금지)
- `github_deploy_key.pub` : **공개키** (서버에 등록)

## 2단계. 서버에 공개키 등록 (authorized_keys)

1. 평소처럼 Lightsail 서버에 접속합니다(Lightsail 콘솔의 "SSH를 사용하여 연결" 또는 터미널).
2. 아래 명령으로 공개키 파일 내용을 서버의 `authorized_keys`에 한 줄 추가합니다.
   `ssh-ed25519 AAAA... github-actions-deploy` 형태의 한 줄을 내 컴퓨터에서
   `cat github_deploy_key.pub`로 확인해 복사하세요.

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "여기에 공개키 한 줄 붙여넣기" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

3. 서버 사전 점검(한 번만):

```bash
cd ~/Portfolio-Job-matching-Web
git status          # 수정된 파일이 없어야 함(.env 는 git 무시 대상이라 괜찮음)
git pull origin main   # 비밀번호 없이 되어야 함
docker-compose ps
```

   - `git pull`이 인증을 요구하면, 저장소가 public이거나 서버에 읽기 전용 deploy key가
     설정되어 있어야 합니다.
   - Lightsail 방화벽(네트워킹 탭)에서 **SSH 22번 포트가 열려 있어야** 합니다.
     (GitHub 서버 IP는 고정이 아니므로 22번은 "모든 IP 허용"이어야 합니다.)

## 3단계. GitHub에 시크릿 등록

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서
아래 3개를 하나씩 등록합니다.

| 이름 | 값 |
| --- | --- |
| `LIGHTSAIL_HOST` | 서버의 고정(Static) IP 또는 도메인 (예: `13.125.xxx.xxx`) |
| `LIGHTSAIL_USER` | 서버 로그인 사용자명 (Lightsail Ubuntu 기본값은 `ubuntu`) |
| `LIGHTSAIL_SSH_KEY` | `github_deploy_key` **개인키 파일 전체 내용** (`-----BEGIN OPENSSH PRIVATE KEY-----` 줄부터 `-----END ...-----` 줄까지, 줄바꿈 포함 그대로) |

개인키 내용 복사: `cat github_deploy_key` 출력을 전부 복사해 붙여넣으세요.
등록이 끝났으면 내 컴퓨터의 `github_deploy_key` 파일은 안전하게 보관하거나 삭제하세요.

> 서버 IP가 재시작 시 바뀌지 않도록 Lightsail에서 **고정 IP(Static IP)** 를 연결해 두는 것을 권장합니다.

## 4단계. 동작 확인

1. GitHub 저장소 → **Actions** 탭 → 왼쪽 **Deploy to Lightsail** → **Run workflow** → `main` 선택 → 실행
2. 초록색 체크가 뜨고 로그 마지막에 `SUCCESS: ... is healthy` 가 보이면 성공입니다.
3. 브라우저에서 `http://서버IP:8000/docs` 가 열리는지 확인합니다.

로그에 `Deploy skipped` 안내가 보이면 시크릿 3개 중 빠진 것이 있다는 뜻입니다(3단계 확인).

## 문제가 생겼을 때

### 자동 롤백
헬스체크가 실패하면 워크플로가 자동으로 이전 커밋으로 되돌리고 다시 빌드합니다.
로그에서 `[rollback] OK` 가 보이면 서비스는 이전 버전으로 정상 복구된 상태입니다.
(워크플로 자체는 "문제가 있었다"는 표시로 빨간 X가 됩니다. 로그의 `docker-compose logs` 부분에서 원인을 확인하세요.)

### 수동 롤백
자동 롤백도 실패(`[rollback] FAILED`)했거나, 배포는 성공했지만 나중에 문제가 발견된 경우, 서버에서:

```bash
cd ~/Portfolio-Job-matching-Web
git log --oneline -10            # 되돌릴 정상 커밋 확인
git reset --hard <정상 커밋 해시>
docker-compose down
docker-compose up -d --build
```

> 주의: 서버를 이전 커밋으로 둔 상태에서 GitHub `main`은 최신이므로, 다음 배포 때 다시 최신으로 올라갑니다.
> 문제 있는 변경은 GitHub에서 해당 PR을 **Revert** 해서 `main`에도 반영하세요.

### 자주 보는 오류
- `Cannot reach ... on SSH port 22` : `LIGHTSAIL_HOST` 오타 또는 방화벽 22번 포트 닫힘
- `Permission denied (publickey)` : 공개키가 서버 `authorized_keys`에 없거나, `LIGHTSAIL_SSH_KEY`가 잘못 복사됨(앞뒤 BEGIN/END 줄 포함 확인), `LIGHTSAIL_USER` 불일치
- `git pull failed` : 서버에서 코드를 직접 수정했거나 기록이 갈라진 경우. 서버에서 `git status` 확인 후 정리(`git stash` 또는 `git reset --hard origin/main`)
- 헬스체크 실패 : 빌드 시간이 길면 늦게 뜰 수 있습니다. 서버에서 `docker-compose logs web` 로 확인

## 자동 배포 끄기

- **일시 중지(권장)**: GitHub → Actions → **Deploy to Lightsail** → 우측 상단 `...` → **Disable workflow**
  (다시 켜려면 **Enable workflow**)
- **완전히 끄기**: 시크릿 3개 중 하나(예: `LIGHTSAIL_HOST`)를 삭제하면 배포가 건너뜀 처리됩니다.
- **영구 제거**: `.github/workflows/deploy.yml` 파일을 삭제하고 머지합니다.

이후에는 평소처럼 서버에서 수동으로 `git pull` 및 `docker-compose down && docker-compose up -d --build` 로 배포할 수 있습니다.

## 보안 참고

- 배포 전용 키는 이 용도로만 쓰고, 노출되었다고 의심되면 서버 `authorized_keys`에서 해당 줄을 지우고 GitHub 시크릿을 새 키로 교체하세요.
- 이 워크플로는 첫 접속 시 서버의 호스트 키를 `ssh-keyscan`으로 받아 신뢰합니다(중간자 공격까지 막으려면 호스트 키를 시크릿으로 고정하는 방식으로 강화 가능).
- 워크플로는 `main` push 및 수동 실행에서만 동작하며, 외부 포크의 PR에서는 시크릿이 전달되지 않습니다.
