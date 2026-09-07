# 배포 (단일 VPS, IP 단계)

도메인 없이 VPS 공인 IP로 우선 접근하는 단계 기준. 도메인이 생기면
`nginx/prod.conf` 상단 주석대로 서브도메인 기반으로 바꾸고 TLS(Let's Encrypt)를 추가한다.

## 사전 준비

VPS에 Docker + Docker Compose, git, Node.js(프론트 빌드용)를 설치하고 세 저장소를
같은 부모 디렉토리에 나란히 clone:

```
~/apps/
  peerbridge/          (백엔드, 이 저장소)
  peerbridge-web/       (사용자 프론트)
  peerbridge-admin/     (관리자 프론트)
```

`peerbridge`(백엔드)는 clone해두지만, 배포 자체는 이미지를 ECR에서 pull만 하는
방식이라 Django 소스코드는 실제로 안 쓰인다 — clone하는 이유는 `docker-compose.prod.yml`,
`nginx/prod.conf`처럼 **compose가 실행 시점에 로컬에서 읽어야 하는 설정 파일들**을
git으로 최신 상태로 유지하기 위해서다(배포 스크립트가 매번 `git pull` 실행).
그래서 EC2 자체가 이 저장소를 pull할 수 있어야 한다 — GitHub repo가 private이면
EC2에 SSH 키를 만들어 GitHub repo Settings → Deploy keys에 등록(읽기 전용으로 충분).

## 1. 프론트 두 개 빌드

각 프론트 저장소에 `.env.production` 파일을 만들고 `VITE_API_BASE_URL=`(빈 값)으로 둔다.
이렇게 하면 API 요청이 `/api/...` 상대경로로 나가서, nginx가 프론트와 같은 origin에서
백엔드로 프록시해준다 — 브라우저 입장에서 CORS 자체가 발생하지 않는다.

```bash
cd ~/apps/peerbridge-web/app && npm ci && npm run build      # -> dist/
cd ~/apps/peerbridge-admin && npm ci && npm run build         # -> dist/
```

## 2. 백엔드 환경변수

설정값이 두 파일로 나뉜다.

**`.env.production`** — `docker-compose.prod.yml` 자체가 쓰는 값 (db 컨테이너 설정, ECR
이미지 태그). 서버에 직접 두는 파일이다.

```bash
cd ~/apps/peerbridge
cp .env.production.example .env.production
# DB_PASSWORD, ECR_IMAGE 등을 채운다.
```

**`.env.docker`** — Django 앱 자체의 설정(SECRET_KEY 등). CI/CD를 쓰면 GitHub Secret
(`ENV_DOCKER`)에서 빌드 시점에 자동 생성되므로 서버에 직접 만들 필요가 없다. CI 없이
로컬에서 수동으로 처음 띄워볼 때만 아래처럼 직접 만든다:

```bash
cp .env.docker.example .env.docker
# SECRET_KEY, ALLOWED_HOSTS(VPS 공인 IP), DB_PASSWORD(= .env.production과 동일값) 등을 채운다.
# SECRET_KEY 생성:
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 3. 기동

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

`web` 컨테이너 기동 시 마이그레이션과 `collectstatic`이 자동 실행된다.

## 4. 확인

- `http://<VPS_IP>/` — 사용자용 사이트
- `http://<VPS_IP>:8081/` — 관리자 콘솔
- `http://<VPS_IP>/api/loans/` — API 응답 확인

## CI/CD (자동배포)

`.github/workflows/deploy.yml` — `main`에 머지/푸시되면 자동으로:
1. GitHub Secret `ENV_DOCKER`로 `.env.docker` 파일을 만든다
2. Docker 이미지를 빌드(이때 `.env.docker`가 이미지 안에 그대로 포함됨)해 ECR에 푸시
   (`:latest` + 커밋 sha 태그)
3. EC2에 SSH로 접속해 `git pull`로 `docker-compose.prod.yml`/`nginx/prod.conf` 등을
   최신화한 뒤 `docker compose pull web && up -d web` 실행 (마이그레이션은 `web`
   컨테이너 기동 커맨드에 이미 포함돼있어 자동 적용됨)

### 최초 1회, AWS 콘솔/CLI에서 준비할 것
- ECR 리포지토리 생성: `aws ecr create-repository --repository-name peerbridge --region ap-northeast-2`
- GitHub Actions가 이미지를 push할 수 있는 IAM 사용자(액세스키/시크릿 발급)
- **EC2가 ECR을 pull할 수 있게 설정** (EC2 인스턴스에서 1회):
  1. EC2 인스턴스에 IAM Role을 붙이고, 그 Role에 `AmazonEC2ContainerRegistryFullAccess` 정책 추가
  2. `amazon-ecr-credential-helper` 설치
     ```bash
     sudo apt update && sudo apt install amazon-ecr-credential-helper   # Ubuntu 기준
     ```
  3. `~/.docker/config.json` 작성
     ```json
     {
       "credsStore": "ecr-login"
     }
     ```
  이렇게 해두면 `docker pull`이 알아서 인스턴스 Role로 인증한다 — 배포 스크립트에 별도
  로그인 스텝이 필요 없다. **주의**: 이 설정은 명령을 실행하는 유저의 `$HOME` 기준이라,
  `sudo docker pull ...`처럼 sudo를 붙이면 root의 `$HOME`(`/root/.docker/config.json`)을
  보게 되어 `no basic auth credentials` 에러가 난다 — SSH 배포 유저를 `docker` 그룹에
  넣어서 sudo 없이 docker 명령이 되게 할 것.

### GitHub 저장소 Settings → Secrets and variables → Actions에 등록할 값
| Secret | 값 |
|---|---|
| `AWS_ACCESS_KEY_ID` | ECR push용 IAM 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | 위 키의 시크릿 |
| `EC2_HOST` | VPS 공인 IP 또는 도메인 |
| `EC2_USER` | SSH 접속 계정 (예: ubuntu) |
| `EC2_SSH_KEY` | EC2 접속용 SSH 프라이빗 키 (PEM 파일 내용 그대로) |
| `ENV_DOCKER` | `.env.docker.example`을 채운 내용 전체를 그대로 붙여넣기 (SECRET_KEY 등, 이미지에 구워짐) |

### 서버의 `.env.production`에 추가로 채울 값
```
ECR_IMAGE=<AWS계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com/peerbridge:latest
```
`docker-compose.prod.yml`의 `web` 서비스가 이 값을 보고 어떤 이미지를 pull할지 정한다.

### 주의: DB_PASSWORD는 두 곳에 따로 존재한다
- `.env.production`(서버) — `db` 컨테이너 자체의 root 비밀번호로 씀
- `ENV_DOCKER`(GitHub Secret, 이미지에 구워짐) — Django가 DB 접속할 때 쓰는 비밀번호

같은 값이어야 접속이 되고, 비밀번호를 바꿀 땐 두 곳 다 바꿔야 한다(하나만 바꾸면 접속 실패).

## 5. DB 접근 (운영 중 조회/디버깅)

DB 포트는 `127.0.0.1`에만 바인딩돼 있어 외부에서 직접 못 붙는다. SSH 터널로 접근:

```bash
ssh -L 3306:localhost:3306 user@<VPS_IP>
# 로컬에서 TablePlus/DBeaver 등으로 localhost:3306 접속
```

## 나중에 도메인이 생기면

1. `nginx/prod.conf`를 서브도메인 기반(`server_name`)으로 교체하고 443 + 인증서 설정 추가
   (Let's Encrypt certbot 컨테이너 또는 host certbot으로 발급)
2. `ENV_DOCKER`(GitHub Secret, 로컬 수동 배포라면 `.env.docker`)의 `ALLOWED_HOSTS`를
   IP에서 도메인으로 교체 후 재배포
3. `settings.py`에 `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`,
   `CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS` 등 HTTPS 전용 보안 설정 추가
   (`python manage.py check --deploy`로 남은 경고 확인)
