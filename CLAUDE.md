# peerbridge

## 프로젝트 개요

P2P 대출 시뮬레이션 플랫폼. 차주(대출 신청자)와 투자자가 연결되어 대출 모집, 투자, 상환, 분배까지 전 사이클을 처리한다.

## 기술 스택

- Python 3.x
- Django 4.2
- Django REST Framework
- MySQL 3306

## 개발 환경 설정

```bash
pip install django djangorestframework mysqlclient python-dotenv djangorestframework-simplejwt drf-spectacular django-cors-headers
```

## 실행 방법

```bash
python manage.py migrate
python manage.py runserver
```

## DB 설정

`.env` 파일에 아래 환경변수를 설정하세요.

```
DB_NAME=peerbridge
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=3306
```

## 도메인 개념

### 사용자 (USER)
- 차주(borrower)와 투자자(investor) 역할을 동시에 수행 가능
- `balance`: 플랫폼 내 예치금 (실제 입출금 없는 가상 잔액)
- 모든 자금 이동은 LEDGER에 기록됨

### 대출 신청 → 대출 상품 흐름
1. 차주가 `LOAN_APPLICATION` 생성 (status=PENDING). 신청 시점엔 금액/목적/기간만 받고 금리는 받지 않음
2. 관리자 심사 → APPROVED 시 `LOAN` 생성 (status=FUNDRAISING). 이 시점에 관리자가 `interest_rate`/`investor_rate`를 함께 책정해 확정
3. 투자자들이 `INVESTMENT` 생성 → `funded_amount` 누적
4. 목표 달성 or 마감일 도래 → LOAN status=ACTIVE, 대출 실행
5. `REPAYMENT_SCHEDULE` 자동 생성 (균등분할 상환)

### 상환 흐름
1. 차주가 회차별 `REPAYMENT` 납부
2. 해당 회차 `REPAYMENT_SCHEDULE` status=PAID
3. 투자 비율에 따라 `DISTRIBUTION` 자동 생성 → 투자자 balance 증가
4. 모든 회차 완료 시 LOAN status=COMPLETED

### 이자율 구조
- `interest_rate`: 차주 연이율 (법정 최고 20% 이내)
- `investor_rate`: 투자자 수익률 (`interest_rate` 미만)
- 차액(스프레드)이 플랫폼 수수료
- 금리는 차주 자기신고가 아니라 관리자가 승인 시점에 신용도를 보고 책정 (`LOAN_APPLICATION`에는 금리 필드 자체가 없음)

### 연체 처리
- LOAN status: `ACTIVE → OVERDUE_1 → OVERDUE_2 → DEFAULT → WRITTEN_OFF`

### LEDGER 타입
| type | 설명 |
|------|------|
| CHARGE | 예치금 충전 |
| WITHDRAW | 예치금 출금 |
| INVEST | 투자 실행 (잔액 차감) |
| DISTRIBUTION | 상환 분배금 수령 |
| REPAY | 차주 상환 납부 (잔액 차감) |
| PLATFORM_FEE | 플랫폼 수수료 |

## ERD 요약

```
USER ──< BANK_ACCOUNT
USER ──< LOAN_APPLICATION ──○ LOAN ──< INVESTMENT >── USER
                                   ──< REPAYMENT_SCHEDULE
                                   ──< REPAYMENT ──< DISTRIBUTION >── INVESTMENT
USER ──< LEDGER
USER ──< NOTIFICATION
```

## App 분리 계획

엔티티는 도메인 경계에 따라 아래 app으로 분리한다. 독립적인 라이프사이클/서비스 로직이 없는 하위 리소스(BANK_ACCOUNT 등)는 소유 엔티티와 같은 app에 둔다.

| app | 엔티티 | 핵심 역할 |
|-----|--------|-----------|
| accounts | User, BankAccount | 회원, 인증, 예치금 잔액, 계좌 정보 |
| loans | LoanApplication, Loan | 대출 신청서(심사 전) / 승인된 대출 상품(모집·상환 대상) |
| investments | Investment | 투자자의 투자 행위 |
| repayments | RepaymentSchedule, Repayment, Distribution | 회차별 상환 계획 / 실제 상환 / 투자자별 분배 |
| ledger | Ledger | 모든 자금 이동 기록(원장) |
| notifications | Notification | 알림 |

## API 구조

### loans (구현 완료)

| Method | Endpoint | 설명 | 인증 |
|--------|----------|------|------|
| GET/POST | /api/loans/applications/ | 내 대출 신청 목록 조회 / 등록 | 로그인 필요 |
| GET | /api/loans/applications/pending/ | 관리자용 심사 대기 목록 | 관리자만 |
| POST | /api/loans/applications/{id}/approve/ | 승인 (`interest_rate`/`investor_rate`/`funding_deadline` 확정, Loan 생성) | 관리자만 |
| POST | /api/loans/applications/{id}/reject/ | 거절 | 관리자만 |
| GET | /api/loans/ | 대출 상품 목록 (`?status=FUNDRAISING` 등 필터) | 비로그인 허용 (메인페이지 노출용) |
| GET | /api/loans/{id}/ | 대출 상품 상세 | 비로그인 허용 |

### 그 외 (예정)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /api/auth/register/ | 회원가입 (구현 완료) |
| POST | /api/auth/login/ | 로그인 (구현 완료) |
| GET | /api/ledger/ | 내 거래 내역 (구현 완료) |
| POST | /api/loans/{id}/invest/ | 투자 실행 (investments 앱 예정) |
| POST | /api/loans/{id}/repay/ | 상환 납부 (repayments 앱 예정) |
| GET | /api/notifications/ | 알림 목록 (예정) |

## 커밋 컨벤션

```
<type> : <설명>
```

| type | 설명 |
|------|------|
| feat | 새 기능 추가 |
| fix | 버그 수정 |
| etc | 그 외 (설정 변경, 리팩토링, 문서 등) |

예시:
```
feat : 투자 실행 API 구현
fix : 상환 분배 금액 계산 오류 수정
etc : MySQL DB 세팅 및 DRF 초기 설정
```

### 커밋 단위

기능 하나를 통째로 계획 승인받았더라도, 커밋은 논리 단위로 쪼갠다. 모델/서비스/API 레이어를 한 커밋에 다 몰아넣지 않는다 (예: 모델+마이그레이션+서비스+시리얼라이저+뷰+URL+테스트를 커밋 하나로 — 이렇게 하지 말 것).

새 기능 하나를 만들 때 예시 순서:
```
test : investments 실패 테스트 작성 (RED)
feat : Investment 모델 생성
feat : 투자 실행 서비스 레이어 구현
feat : 투자 실행 API(뷰/URL) 연결
```

## 주의사항

- `idempotency_key`가 있는 테이블(INVESTMENT, REPAYMENT)은 중복 요청 방지 필수
- 잔액 변경은 항상 LEDGER 기록과 원자적으로 처리 (트랜잭션)
