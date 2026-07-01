---
name: auto
description: "7-Phase 파이프라인 — /auto {subcommand} [flags]"
level1_metadata: "triage, plan, go, fix, review, test, ship"
triggers:
  - auto
  - plan
  - go
  - fix
  - review
  - test
  - ship
  - 구현
  - 버그
  - 리뷰
  - 계획
  - 수정
category: workflow
---

# /auto — 7-Phase Pipeline

ARGUMENTS: $ARGUMENTS

## Global Flags

| 플래그 | 설명 |
|--------|------|
| --solo | 메인 세션 직접 (에이전트 없이) |
| --team | Agent Teams 모드 (TeamCreate) |
| --multi | codex/gemini 멀티모델 참여 |
| --auto | 게이트 자동 승인 |
| --loop | 실패 시 자동 재시도 (최대 3회) |

## 서브커맨드 라우팅

첫 단어 매칭. 없으면 triage 자동 실행.

| 커맨드 | 실행 Phase |
|--------|-----------|
| triage | Phase 0 |
| plan | Phase 1 + Gate 1 |
| go | Phase 0~6 풀 파이프라인 |
| fix | Phase 0, 3, 4, 5, 6 (Plan 생략) |
| review | Phase 4만 |
| test | Phase 5만 |
| ship | Phase 6만 |

---

## /auto triage — 자연어 → 난이도 → 워크플로우

| Signal | IDEA | LOW | MEDIUM | HIGH |
|--------|------|-----|--------|------|
| 변경 유형 | 고민, brainstorm | fix, typo, config | 리팩토링, 개선 | 새로운 feature, 모듈 |
| 범위 | 불명확, 탐색적 | 특정 파일/함수 | 앱/모듈 | 다중 도메인 (예: 투자+상환+분배 동시) |
| 동사 | think, 고민 | change, update | add, enhance | design, build, create |

| 난이도 | 워크플로우 |
|--------|-----------|
| IDEA | 브레인스토밍 → /auto plan |
| LOW | 바로 수정 (Plan 생략) |
| MEDIUM | plan → go |
| HIGH | plan → go (풀 파이프라인) |
| CRITICAL | 즉시 수정 + security 추가 (잔액/LEDGER 정합성 이슈는 기본 CRITICAL) |

```
## Triage
- 요청: "{request}"
- 난이도: {IDEA|LOW|MEDIUM|HIGH|CRITICAL}
- 추천: {recommended flow}

진행할까요?
```
MEDIUM 이상은 사용자 승인 후 진행.

---

## /auto plan — 계획

**Step 1**: What / Why / Who / When 정리

**Step 2: EARS 요구사항**
```
WHEN <행동>, THE SYSTEM SHALL <반응>.
```
각 요구사항에 ID 부여: REQ-001, REQ-002, ...

**Step 3: 엣지케이스** — 빈 입력, 잔액 부족, 동시 투자/상환 요청, 중복 idempotency_key, 목표금액 초과 투자, 상환 마감일 도과

**Step 4: 태스크 분해**
```
- [T-01] 파일: peerbridge/loans/models.py | 유형: add | 의존: 없음 | 병렬: YES
- [T-02] 파일: peerbridge/loans/serializers.py | 유형: modify | 의존: T-01 | 병렬: NO
```
한 태스크가 한 파일 소유. 동일 파일 수정 시 순차로 합침.

Gate: 태스크 목록 + EARS 제시 → 사용자 승인 후 진행.

---

## /auto go [flags] — 7-Phase 풀 파이프라인

### Phase 0: Triage
- 자연어 입력 분석 → 문제/기능 파악
- grep/read로 영향 범위 측정
- 난이도 판정

### Phase 1: Plan
- planner 에이전트(`opus`) 스폰
- EARS 요구사항 + 태스크 분해
- 복잡도 → adaptive quality 모델 결정

### Gate 1: 승인
계획 보고서 제시 → 사용자 승인 대기.
--auto 시 스킵.

### Phase 2: RED (TDD)
- tester 에이전트(`sonnet`) 스폰
- 실패 테스트 먼저 작성 → 실제 FAIL 확인

### Phase 3: GREEN
- executor 에이전트(`sonnet`, acceptEdits) 스폰
- --solo: 메인 세션 직접 구현
- --team: TeamCreate → 팀원에게 위임
- 계획에 없는 파일 수정 금지

### Phase 4: Review
- reviewer 에이전트(`sonnet`) — TRUST 5

### Gate 2: 재빌드 승인

### Phase 5: Rebuild + Test

테스트 단계별 실행 (하나 실패 시 중단):

1. 정적 검사: `python manage.py check`
2. 마이그레이션 무결성: `python manage.py makemigrations --check --dry-run`
3. 단위/통합: `python manage.py test`
4. 커버리지: `coverage run manage.py test && coverage report`

FAIL → Phase 3 루프 (--loop 시)

### Gate 3: 커밋 승인
변경 요약 + 테스트 결과 보고서 제시.
사용자 승인 대기. --auto 시 스킵.

### Phase 6: Ship
```bash
git add -A
git commit -m "<type> : <설명>"
git push
```
type은 CLAUDE.md 커밋 컨벤션(`feat`/`fix`/`etc`) 준수.

---

## /auto fix — 경량 파이프라인

Phase 0(Triage) + Phase 3(GREEN) + Phase 4(Review) + Phase 5(Test) + Phase 6(Ship).
Plan 생략, Gate 1 생략.

**재현 → 격리 → 원인 분석 → 수정 → 검증** 순서 준수.
수정 범위 최소화, 관련 없는 리팩토링 금지.

```bash
python manage.py test
```

---

## /auto review — 리뷰만 (Phase 4)

```bash
git diff HEAD~1 HEAD --stat
git diff HEAD~1 HEAD
```
diff + 주변 컨텍스트(±20줄) 기반. 전체 파일 읽기 금지.

**T — Tested**: 대응 테스트 존재? 커버리지 85%+?
**R — Readable**: 네이밍 명확? 메서드 50줄↓, 파일 300줄↓?
**U — Unified**: 기존 패턴 일치? 중복 없음? 공통 컴포넌트 활용?
**S — Secured**: 입력값 검증? 시크릿 하드코딩 없음? 인증/인가 누락 없음? LEDGER/트랜잭션 정합성?
**T — Trackable**: 에러 로그 충분? 변경 이유 추적 가능?

| 판정 | 기준 |
|------|------|
| PASS | 모든 TRUST 항목 충족 |
| CONDITIONAL PASS | 경미한 지적, 수정 후 재리뷰 없이 진행 |
| FAIL | TRUST 위반, 보안 이슈, 파일 크기 초과 |

---

## /auto test — 테스트만 (Phase 5)

```bash
python manage.py check
python manage.py test
coverage run manage.py test && coverage report
```

---

## /auto ship — 커밋만 (Phase 6)

```bash
git status
git diff --stat
git add -A
git commit -m "<type> : <설명>"
git push
```

---

## 진행 표시

각 Phase 전환 시 출력:
```
Pipeline ─────────────────────────
  ✓ Phase 1: Plan
  → Phase 3: GREEN [2/5 tasks]
  ○ Phase 4: Review
  ○ Phase 5: Test
  ○ Phase 6: Ship
```
