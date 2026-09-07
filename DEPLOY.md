# 배포

DB는 Supabase(PostgreSQL), nginx는 이 저장소 밖에서 별도로 구성한다. 이 저장소가
관리하는 건 `web`(Django+gunicorn) 컨테이너 하나뿐이다.

## 배포 흐름

`.github/workflows/deploy.yml` — `main`에 머지/푸시되면 자동으로:
1. GitHub Secret `ENV_PROD`로 `.env.prod` 파일을 만든다
2. Docker 이미지를 빌드(이때 `.env.prod`가 이미지 안에 그대로 포함됨)해 ECR에 푸시
   (`:latest` + 커밋 sha 태그)
3. EC2에 SSH로 접속해 기존 컨테이너를 내리고, 새 이미지로 `docker run` 재기동
   (마이그레이션/`collectstatic`은 `docker run`에 넘기는 커맨드에 포함돼있어 자동 적용됨)

EC2에는 git clone도, 서버에 직접 두는 설정 파일도 필요 없다 — Docker만 설치돼있으면 된다.

## 최초 1회 준비

### Supabase
1. 프로젝트 생성
2. Settings → Database → Connection info에서 호스트/포트/DB명/유저/비밀번호 확인
3. 이 값들을 `ENV_PROD` Secret에 채움 (아래 참고)

### AWS
- ECR 리포지토리 생성: `aws ecr create-repository --repository-name peerbridge --region ap-northeast-2`
- GitHub Actions가 이미지를 push할 수 있는 IAM 사용자 생성, `AmazonEC2ContainerRegistryFullAccess` 부여, Access Key 발급
- **EC2가 ECR을 pull할 수 있게 설정** (EC2 인스턴스에서 1회):
  1. EC2 인스턴스에 IAM Role을 붙이고, 그 Role에 `AmazonEC2ContainerRegistryFullAccess` 정책 추가
  2. `amazon-ecr-credential-helper` 설치
     ```bash
     sudo apt update && sudo apt install amazon-ecr-credential-helper   # Ubuntu 기준
     ```
  3. `~/.docker/config.json` 작성
     ```json
     { "credsStore": "ecr-login" }
     ```
  이렇게 해두면 `docker pull`이 알아서 인스턴스 Role로 인증한다. **주의**: `sudo docker pull ...`처럼
  sudo를 붙이면 root의 `$HOME`을 보게 되어 `no basic auth credentials` 에러가 난다 —
  SSH 배포 유저를 `docker` 그룹에 넣어서 sudo 없이 docker 명령이 되게 할 것.

### GitHub 저장소 Settings → Secrets and variables → Actions
| Secret | 값 |
|---|---|
| `AWS_ACCESS_KEY_ID` | ECR push용 IAM 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | 위 키의 시크릿 |
| `EC2_HOST` | EC2 공인 IP (탄력적 IP 권장) 또는 도메인 |
| `EC2_USER` | SSH 접속 계정 (예: ubuntu) |
| `EC2_SSH_KEY` | EC2 접속용 SSH 프라이빗 키 (PEM 파일 내용 그대로) |
| `ENV_PROD` | `.env.prod.example`을 채운 내용 전체 (SECRET_KEY, Supabase 접속정보 등) |

## nginx (직접 구성)

`web` 컨테이너는 `8000` 포트로 뜬다. 프론트(정적 파일)와 `/api` 요청을 이 포트로
넘겨주는 nginx 설정을 EC2에 직접 구성한다. 프론트를 `VITE_API_BASE_URL=""`(상대경로)로
빌드하고 nginx가 같은 origin에서 `/api`를 이 포트로 프록시하면, 브라우저 입장에서
CORS 자체가 발생하지 않는다(그 구성이 아니면 `.env.prod`의 `CORS_EXTRA_ORIGINS`를 채울 것).

## DB 접근 (운영 중 조회/디버깅)

Supabase 콘솔에서 바로 SQL 편집기/테이블 뷰로 확인 가능. 또는 `.env.prod`에 채운
접속정보로 TablePlus/DBeaver 등에서 직접 연결(Supabase가 외부 접속을 허용하는 포트/SSL
설정을 제공함 — Supabase 프로젝트의 Connection info 참고).

## 나중에 도메인이 생기면

1. nginx 설정에서 `server_name`을 도메인으로, 443 + TLS(Let's Encrypt) 추가
2. `ENV_PROD`의 `ALLOWED_HOSTS`를 IP에서 도메인으로 교체 후 재배포
3. `settings.py`에 `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`,
   `CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS` 등 HTTPS 전용 보안 설정 추가
   (`python manage.py check --deploy`로 남은 경고 확인)
