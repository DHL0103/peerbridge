from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import BankAccount, User
from investments.services import create_investment
from ledger.models import Ledger
from loans.models import Loan, LoanApplication
from repayments.services import repay

DEMO_PASSWORD = 'demo1234!'


def _get_or_create_user(username, email):
    user, created = User.objects.get_or_create(username=username, defaults={'email': email})
    if created:
        user.set_password(DEMO_PASSWORD)
        user.save()
        BankAccount.objects.create(
            user=user, bank_name='카카오뱅크', account_number='3333-01-1234567',
            account_holder=user.username, is_primary=True,
        )
    return user, created


def _charge(user, amount):
    user.balance += amount
    user.save(update_fields=['balance'])
    Ledger.objects.create(user=user, type=Ledger.Type.CHARGE, amount=amount, balance_after=user.balance)


class Command(BaseCommand):
    help = '포트폴리오 데모용 테스트 데이터를 생성한다 (idempotent — 이미 있으면 건너뜀). 프로덕션에서 1회 실행 목적.'

    def handle(self, *args, **options):
        with transaction.atomic():
            bora, _ = _get_or_create_user('demo_bora', 'demo_bora@example.com')
            jihoon, _ = _get_or_create_user('demo_jihoon', 'demo_jihoon@example.com')
            minjun, minjun_new = _get_or_create_user('demo_minjun', 'demo_minjun@example.com')
            seoyeon, seoyeon_new = _get_or_create_user('demo_seoyeon', 'demo_seoyeon@example.com')
            yuna, yuna_new = _get_or_create_user('demo_yuna', 'demo_yuna@example.com')

            if minjun_new:
                _charge(minjun, Decimal('3000000'))
            if seoyeon_new:
                _charge(seoyeon, Decimal('2000000'))
            if yuna_new:
                _charge(yuna, Decimal('1500000'))

            if not LoanApplication.objects.filter(user=bora, purpose='사업 운영자금').exists():
                LoanApplication.objects.create(
                    user=bora, amount=Decimal('3000000'), purpose='사업 운영자금', term_months=6,
                )
                self.stdout.write('demo: 심사 대기중 신청서 생성')

            app_b, app_b_new = LoanApplication.objects.get_or_create(
                user=bora, purpose='전세자금 대출',
                defaults={
                    'amount': Decimal('5000000'), 'term_months': 12,
                    'status': LoanApplication.Status.APPROVED,
                },
            )
            if app_b_new:
                loan_b = Loan.objects.create(
                    application=app_b, interest_rate=Decimal('12.5'), investor_rate=Decimal('9.5'),
                    target_amount=app_b.amount, term_months=app_b.term_months,
                    funding_deadline=date.today() + timedelta(days=14),
                )
                create_investment(
                    loan_id=loan_b.id, investor=minjun, amount=Decimal('2000000'),
                    idempotency_key='demo-inv-1',
                )
                create_investment(
                    loan_id=loan_b.id, investor=seoyeon, amount=Decimal('1500000'),
                    idempotency_key='demo-inv-2',
                )
                self.stdout.write('demo: 모집중(부분 펀딩) 대출 생성')

            app_c, app_c_new = LoanApplication.objects.get_or_create(
                user=jihoon, purpose='의료비',
                defaults={
                    'amount': Decimal('2000000'), 'term_months': 6,
                    'status': LoanApplication.Status.APPROVED,
                },
            )
            if app_c_new:
                loan_c = Loan.objects.create(
                    application=app_c, interest_rate=Decimal('15.0'), investor_rate=Decimal('11.0'),
                    target_amount=app_c.amount, term_months=app_c.term_months,
                    funding_deadline=date.today() + timedelta(days=7),
                )
                create_investment(
                    loan_id=loan_c.id, investor=yuna, amount=Decimal('1200000'),
                    idempotency_key='demo-inv-3',
                )
                create_investment(
                    loan_id=loan_c.id, investor=minjun, amount=Decimal('800000'),
                    idempotency_key='demo-inv-4',
                )
                _charge(jihoon, Decimal('1000000'))

                # 방금 생성된 스케줄 중 앞 2회차는 정산일을 과거로 당겨서, repay() 호출 시
                # "정산일이 이미 지남" 경로를 타 즉시 분배(Distribution)까지 만들어지게 한다.
                schedules = list(loan_c.repayment_schedules.order_by('installment_number')[:2])
                for schedule, past_date in zip(schedules, [date.today() - timedelta(days=40), date.today() - timedelta(days=10)]):
                    schedule.due_date = past_date
                    schedule.save(update_fields=['due_date'])

                repay(loan_id=loan_c.id, borrower=jihoon, idempotency_key='demo-repay-1')
                repay(loan_id=loan_c.id, borrower=jihoon, idempotency_key='demo-repay-2')
                self.stdout.write('demo: 실행중 대출 + 상환 이력 2회 생성')

        self.stdout.write(self.style.SUCCESS(f'데모 데이터 생성 완료 (계정 비밀번호: {DEMO_PASSWORD})'))
