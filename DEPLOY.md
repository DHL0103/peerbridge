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
docker compose -f docker-compose.prod.yml up -d --build
```

`web` 컨테이너 기동 시 마이그레이션과 `collectstatic`이 자동 실행된다.

## 4. 확인

- `http://<VPS_IP>/` — 사용자용 사이트
- `http://<VPS_IP>:8081/` — 관리자 콘솔
- `http://<VPS_IP>/api/loans/` — API 응답 확인

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
