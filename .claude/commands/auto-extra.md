---
name: auto-extra
description: "보조 워크플로우 — /auto-extra {subcommand}"
level1_metadata: "api, db, security, verify, handoff, quality, worktree, branding"
triggers:
  - api
  - db
  - database
  - security
  - verify
  - handoff
  - quality
  - worktree
  - API
  - 보안
  - 마이그레이션
category: workflow
---

# /auto-extra — 보조 워크플로우 라우터

ARGUMENTS: $ARGUMENTS

| 커맨드 | 설명 |
|--------|------|
| api | REST API 설계 가이드 |
| db | DB 설계 및 마이그레이션 |
| security | OWASP Top 10 보안 감사 |
| verify | 품질 게이트 검증 |
| handoff | 세션 인수인계 |
| quality | 복잡도 기반 모델 선택 |
| worktree | 병렬 executor 격리 |
| branding | 파이프라인 진행 시각화 |

---

## /auto-extra api — REST API 설계

**명명**: 명사 복수형(`/loans`, `/investments`), 소문자, 계층 3단계 이내. HTTP 메서드: GET(멱등), POST(생성/액션), PUT(전체교체), PATCH(부분수정), DELETE(멱등).

현재 프로젝트는 `/api/auth/`, `/api/loans/`, `/api/ledger/`, `/api/notifications/` 등 버전 prefix 없이 운영 중(`CLAUDE.md` API 구조 참고) — 새 엔드포인트도 이 컨벤션을 따름. 버전이 필요해지면 그때 `/api/v1/` 도입 논의.

**상태코드**: 200 조회/수정, 201 생성(Location 헤더), 204 삭제, 400 입력오류, 401 미인증, 403 권한없음, 404 미존재, 409 충돌(예: 목표금액 초과 투자), 422 유효성실패.

응답: `{"data": {...}, "message": "success"}` / 에러: `{"error": {"code": "...", "message": "...", "details": [...]}}`

체크리스트: 명사 복수형? HTTP 메서드 의미 일치? 인증/인가(JWT) 명시? 에러 응답 일관? 페이지네이션? idempotency_key 요구 여부 명시(투자/상환 액션)?

---

## /auto-extra db — DB 설계 및 마이그레이션

데이터베이스: **MySQL** (`.env`의 DB_HOST/DB_PORT=3306)

Django 마이그레이션 프레임워크 사용 — 원시 SQL 파일 대신 `makemigrations`/`migrate` 표준 워크플로우 따름.

```bash
python manage.py makemigrations <app>
python manage.py migrate --plan     # 적용 전 확인
python manage.py migrate
```

**인덱스**: WHERE/필터에 자주 쓰이는 컬럼(FK, status) 추가, 카디널리티 낮은 컬럼 단독 지양. **N+1**: `select_related`/`prefetch_related` 활용. **트랜잭션**: 잔액·LEDGER·INVESTMENT·REPAYMENT 갱신은 `transaction.atomic()` 필수, 외부 API 호출은 트랜잭션 블록 밖으로 분리.

체크리스트: 마이그레이션이 기존 데이터와 호환(NOT NULL엔 default)? 인덱스 필요 컬럼 확인? N+1 확인? 트랜잭션 경계가 서비스/뷰 레이어에 명확히 있는지? LEDGER insert가 balance update와 같은 트랜잭션 안에 있는지?

---

## /auto-extra security — 보안 감사

OWASP Top 10: A01 접근제어, A02 암호화, A03 인젝션, A04 불안전설계, A05 설정오류, A06 취약컴포넌트, A07 인증실패, A08 무결성실패, A09 로깅실패, A10 SSRF

- 입력검증: 화이트리스트, Django ORM 파라미터 바인딩(raw SQL 지양), Log Injection 방지
- 인증/인가: JWT(simplejwt) 토큰 만료/갱신 정책, 공개 엔드포인트 점검, 타 사용자 자원 접근 차단(예: 남의 INVESTMENT 조회)
- 암호화: 비밀번호 Django 기본 해셔(PBKDF2) 이상 사용, 민감 데이터 평문 저장 금지
- 시크릿: `.env`의 DB_PASSWORD/SECRET_KEY 등이 커밋되지 않았는지, 하드코딩 금지
- 금융 로직 특화: balance 음수 방지, 이중 지불(중복 투자/상환) 방지용 idempotency_key 검증, 이자율 상한(20%) 서버측 강제

```bash
gitleaks detect --source . --no-git 2>/dev/null || echo "gitleaks not installed"
git diff HEAD~1 HEAD | grep -iE "(password|secret|api_key|token)\s*=\s*['\"][^'\"]{4,}"
```

아키텍처: DEBUG=False(운영), CORS 와일드카드(`*`) 금지, ALLOWED_HOSTS 명시.

| 판정 | 기준 |
|------|------|
| PASS | OWASP 위반 없음, 시크릿 미탐지 |
| FAIL | 취약점 발견 또는 시크릿 탐지 |

---

## /auto-extra verify — 품질 게이트

순서: **빌드 → 테스트 → 커버리지 → 린트 → EARS 대조**. 하나라도 FAIL이면 중단.

- Gate 1 빌드: `python manage.py check`
- Gate 2 테스트: `python manage.py test` (단위=앱별 tests.py, 통합=API 엔드포인트 APITestCase)
- Gate 3 커버리지: `coverage run manage.py test && coverage report` — 85% 이상
- Gate 4 린트: `flake8` 또는 `ruff check`(설치 시)
- Gate 5 EARS 대조: REQ-* 요구사항과 구현/테스트 여부 대조

PASS = 5개 게이트 모두 통과 / FAIL = 1개 이상 미통과

---

## /auto-extra handoff — 세션 인수인계

세션 인수인계 비활성화 (`session.handoff_enabled: false` 또는 미설정).

---

## /auto-extra quality — 복잡도 기반 모델 선택

| 복잡도 | 파일 수 | 변경 줄 수 | 모델 |
|--------|---------|-----------|------|
| HIGH | 3개+ | 200줄+ | `opus` |
| MEDIUM | 2개+ | 50줄+ | `sonnet` |
| LOW | 1개 미만 | 50줄 미만 | `haiku` |

기준 중 하나라도 상위 충족 시 높은 복잡도로 판정. planner는 항상 `opus`.
잔액/LEDGER/이자 계산 로직이 포함되면 파일·줄수 기준과 무관하게 최소 MEDIUM 이상으로 판정.

---

## /auto-extra worktree — 병렬 Executor 격리

전제: git 저장소, `pipeline.worktree.enabled: true`, 최대 3개 동시.

```bash
git worktree add /tmp/peerbridge-worker-{N} -b auto/worker-{N}
```

동일 파일 수정 충돌 시 순차 태스크로 합치거나 단일 executor에 할당. 완료 후 태스크 ID 오름차순 병합, `git worktree remove` + 브랜치 삭제.

비활성화: 태스크 1개, 동일 파일 수정, `pipeline.worktree.enabled: false`.

---

## /auto-extra branding — 진행 시각화

세션 시작:
```
peerbridge | balanced mode
Stack: Django 4.2 + DRF + MySQL
```

Phase 전환:
```
Pipeline ─────────────────────────
  ✓ Phase 1: Planning
  → Phase 2: Implementation [N/M tasks]
  ○ Phase 3: Testing
```
(`✓` 완료, `→` 진행 중, `○` 대기). 마일스톤 후: `── applied: {적용된 규칙 목록}`
