import calendar
from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from accounts.models import User
from investments.services import create_investment
from loans.models import Loan, LoanApplication
from repayments.models import RepaymentSchedule
from repayments.services import generate_schedule


def _add_months(base_date, months):
    """dateutil 없이 표준 라이브러리만으로 월 단위를 더한다 (말일 보정 포함)."""
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class ScheduleGenerationTests(APITestCase):
    """목표 모집금액 도달(대출 실행) 시 상환 스케줄 자동 생성 테스트 (REQ-011~014)."""

    def setUp(self):
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')
        self.investor_a = User.objects.create_user(username='investor_a', email='investor_a@example.com', password='S7rongPass!2024')
        self.investor_b = User.objects.create_user(username='investor_b', email='investor_b@example.com', password='S7rongPass!2024')
        self.investor_c = User.objects.create_user(username='investor_c', email='investor_c@example.com', password='S7rongPass!2024')
        for investor in (self.investor_a, self.investor_b, self.investor_c):
            investor.balance = Decimal('200000.00')
            investor.save()

    def _create_loan(self, target_amount, term_months, interest_rate=Decimal('12.00'), investor_rate=Decimal('10.00')):
        application = LoanApplication.objects.create(
            user=self.borrower, amount=target_amount, purpose='사업자금', term_months=term_months,
            status=LoanApplication.Status.APPROVED,
        )
        return Loan.objects.create(
            application=application, interest_rate=interest_rate, investor_rate=investor_rate,
            target_amount=target_amount, funded_amount=Decimal('0'), term_months=term_months,
            funding_deadline='2026-12-01', status=Loan.Status.FUNDRAISING,
        )

    def _fund_to_target(self, loan):
        """투자자 3명이 각 100,000원씩 투자해 300,000원 목표를 정확히 채운다 (대출 실행 트리거)."""
        create_investment(loan_id=loan.id, investor=self.investor_a, amount=Decimal('100000.00'), idempotency_key='fund-a')
        create_investment(loan_id=loan.id, investor=self.investor_b, amount=Decimal('100000.00'), idempotency_key='fund-b')
        create_investment(loan_id=loan.id, investor=self.investor_c, amount=Decimal('100000.00'), idempotency_key='fund-c')
        loan.refresh_from_db()

    # REQ-011
    def test_reaching_target_generates_repayment_schedule_rows(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)

        self._fund_to_target(loan)

        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.ACTIVE)
        schedules = RepaymentSchedule.objects.filter(loan=loan).order_by('installment_number')
        self.assertEqual(schedules.count(), 12)
        self.assertEqual(sum((s.principal for s in schedules), Decimal('0')), Decimal('300000.00'))
        self.assertEqual(schedules[0].installment_number, 1)
        self.assertEqual(schedules[0].status, RepaymentSchedule.Status.PENDING)

    # REQ-012
    def test_schedule_interest_declines_on_declining_balance(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)

        self._fund_to_target(loan)

        install1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        install2 = RepaymentSchedule.objects.get(loan=loan, installment_number=2)
        self.assertEqual(install1.principal, Decimal('25000.00'))
        self.assertEqual(install1.interest, Decimal('3000.00'))
        self.assertEqual(install1.total_amount, Decimal('28000.00'))
        self.assertEqual(install2.principal, Decimal('25000.00'))
        self.assertEqual(install2.interest, Decimal('2750.00'))
        self.assertEqual(install2.total_amount, Decimal('27750.00'))
        self.assertLess(install2.total_amount, install1.total_amount)

    # REQ-013
    def test_schedule_due_dates_spaced_one_month_apart(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)

        self._fund_to_target(loan)

        install1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        install2 = RepaymentSchedule.objects.get(loan=loan, installment_number=2)
        today = date.today()
        self.assertEqual(install1.due_date, _add_months(today, 1))
        self.assertEqual(install2.due_date, _add_months(today, 2))

    # REQ-014
    def test_generate_schedule_is_idempotent_on_repeated_call(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)
        self._fund_to_target(loan)
        self.assertEqual(RepaymentSchedule.objects.filter(loan=loan).count(), 12)

        generate_schedule(loan)

        self.assertEqual(RepaymentSchedule.objects.filter(loan=loan).count(), 12)
