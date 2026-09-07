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

## 1. 프론트 두 개 빌드

각 프론트 저장소에 `.env.production` 파일을 만들고 `VITE_API_BASE_URL=`(빈 값)으로 둔다.
이렇게 하면 API 요청이 `/api/...` 상대경로로 나가서, nginx가 프론트와 같은 origin에서
백엔드로 프록시해준다 — 브라우저 입장에서 CORS 자체가 발생하지 않는다.

```bash
cd ~/apps/peerbridge-web/app && npm ci && npm run build      # -> dist/
cd ~/apps/peerbridge-admin && npm ci && npm run build         # -> dist/
```

## 2. 백엔드 환경변수

```bash
cd ~/apps/peerbridge
cp .env.production.example .env.production
# SECRET_KEY, ALLOWED_HOSTS(VPS 공인 IP), DB_PASSWORD 등을 채운다.
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
1. Docker 이미지를 빌드해 ECR에 푸시 (`:latest` + 커밋 sha 태그)
2. EC2에 SSH로 접속해 `docker compose pull web && up -d web` 실행 (마이그레이션은
   `web` 컨테이너 기동 커맨드에 이미 포함돼있어 자동 적용됨)

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

### `.env.production`에 추가로 채울 값
```
ECR_IMAGE=<AWS계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com/peerbridge:latest
```
`docker-compose.prod.yml`의 `web` 서비스가 이 값을 보고 어떤 이미지를 pull할지 정한다.

## 5. DB 접근 (운영 중 조회/디버깅)

DB 포트는 `127.0.0.1`에만 바인딩돼 있어 외부에서 직접 못 붙는다. SSH 터널로 접근:

```bash
ssh -L 3306:localhost:3306 user@<VPS_IP>
# 로컬에서 TablePlus/DBeaver 등으로 localhost:3306 접속
```

## 나중에 도메인이 생기면

1. `nginx/prod.conf`를 서브도메인 기반(`server_name`)으로 교체하고 443 + 인증서 설정 추가
   (Let's Encrypt certbot 컨테이너 또는 host certbot으로 발급)
2. `.env.production`의 `ALLOWED_HOSTS`를 IP에서 도메인으로 교체
3. `settings.py`에 `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`,
   `CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS` 등 HTTPS 전용 보안 설정 추가
   (`python manage.py check --deploy`로 남은 경고 확인)
