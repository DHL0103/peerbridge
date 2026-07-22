import calendar
from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import PLATFORM_USERNAME, User
from investments.services import create_investment
from ledger.models import Ledger
from loans.models import Loan, LoanApplication
from repayments.models import Distribution, Repayment, RepaymentSchedule
from repayments.services import generate_schedule


def _repay_url(loan_id):
    return f'/api/loans/{loan_id}/repay/'


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


class RepaymentAPITests(APITestCase):
    """POST /api/loans/{id}/repay/ 상환 납부 API 테스트 (REQ-015~026)."""

    def setUp(self):
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')
        self.borrower.balance = Decimal('1000000.00')
        self.borrower.save()
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

    def _create_active_loan_three_way(self):
        """300,000원/12개월 대출을 투자자 3명이 각 100,000원(균등)씩 투자해 실행 상태로 만든다."""
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)
        create_investment(loan_id=loan.id, investor=self.investor_a, amount=Decimal('100000.00'), idempotency_key='fund-a')
        create_investment(loan_id=loan.id, investor=self.investor_b, amount=Decimal('100000.00'), idempotency_key='fund-b')
        create_investment(loan_id=loan.id, investor=self.investor_c, amount=Decimal('100000.00'), idempotency_key='fund-c')
        loan.refresh_from_db()
        return loan

    def _create_active_loan_single_investor(self, target_amount, term_months, interest_rate=Decimal('12.00'), investor_rate=Decimal('10.00')):
        loan = self._create_loan(target_amount, term_months, interest_rate, investor_rate)
        create_investment(loan_id=loan.id, investor=self.investor_a, amount=target_amount, idempotency_key='fund-solo')
        loan.refresh_from_db()
        return loan

    # REQ-015
    def test_repay_happy_path_deducts_balance_and_marks_schedule_paid(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-1'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        repayment = Repayment.objects.get(idempotency_key='repay-1')
        self.assertEqual(response.data['id'], repayment.id)
        self.assertEqual(response.data['loan'], loan.id)
        self.assertEqual(response.data['installment_number'], 1)
        self.assertEqual(Decimal(response.data['amount']), Decimal('28000.00'))
        self.assertEqual(response.data['idempotency_key'], 'repay-1')
        self.assertIn('created_at', response.data)

        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('972000.00'))

        schedule1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        self.assertEqual(schedule1.status, RepaymentSchedule.Status.PAID)
        self.assertIsNotNone(schedule1.paid_at)

        ledger = Ledger.objects.get(user=self.borrower, type=Ledger.Type.REPAY)
        self.assertEqual(ledger.amount, Decimal('28000.00'))
        self.assertEqual(ledger.balance_after, Decimal('972000.00'))

    # REQ-016
    def test_repay_next_call_pays_next_installment(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)
        self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-1'}, format='json')

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-2'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['installment_number'], 2)
        schedule1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        schedule2 = RepaymentSchedule.objects.get(loan=loan, installment_number=2)
        self.assertEqual(schedule1.status, RepaymentSchedule.Status.PAID)
        self.assertEqual(schedule2.status, RepaymentSchedule.Status.PAID)
        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('944250.00'))

    # REQ-017
    def test_repay_distributes_to_investors_rounded_down_evenly(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-1'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.investor_a.refresh_from_db()
        self.investor_b.refresh_from_db()
        self.investor_c.refresh_from_db()
        # 원금 25,000.00 + 투자자 몫 이자 2,500.00 = 27,500.00을 1/3씩 분배.
        # 투자자별로 원 단위 절사(ROUND_DOWN)해서 모두 동일하게 9,166.66을 받고,
        # 절사로 남은 0.02원은 스프레드와 함께 플랫폼 계좌로 귀속된다.
        # 투자자 잔액은 100,000원 투자 후 100,000원으로 줄어든 상태에서 분배금이 더해진다.
        self.assertEqual(self.investor_a.balance, Decimal('109166.66'))
        self.assertEqual(self.investor_b.balance, Decimal('109166.66'))
        self.assertEqual(self.investor_c.balance, Decimal('109166.66'))

        self.assertEqual(Distribution.objects.count(), 3)
        dist_a = Distribution.objects.get(investor=self.investor_a)
        dist_b = Distribution.objects.get(investor=self.investor_b)
        dist_c = Distribution.objects.get(investor=self.investor_c)
        self.assertEqual(dist_a.amount, Decimal('9166.66'))
        self.assertEqual(dist_b.amount, Decimal('9166.66'))
        self.assertEqual(dist_c.amount, Decimal('9166.66'))
        self.assertEqual(dist_a.amount + dist_b.amount + dist_c.amount, Decimal('27499.98'))

        self.assertEqual(Ledger.objects.filter(type=Ledger.Type.DISTRIBUTION).count(), 3)
        ledger_c = Ledger.objects.get(user=self.investor_c, type=Ledger.Type.DISTRIBUTION)
        self.assertEqual(ledger_c.amount, Decimal('9166.66'))
        self.assertEqual(ledger_c.balance_after, Decimal('109166.66'))

    # REQ-017
    def test_repay_credits_platform_account_with_spread_and_rounding_remainder(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)

        self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-1'}, format='json')

        # 스프레드(이자 3,000 - 투자자 몫 2,500 = 500.00) + 원금/이자 절사 잔여분(0.01+0.01) = 500.02.
        platform = User.objects.get(username=PLATFORM_USERNAME)
        platform.refresh_from_db()
        self.assertEqual(platform.balance, Decimal('500.02'))
        ledger = Ledger.objects.get(user=platform, type=Ledger.Type.PLATFORM_FEE)
        self.assertEqual(ledger.amount, Decimal('500.02'))
        self.assertEqual(ledger.balance_after, Decimal('500.02'))

    # REQ-018
    def test_repay_duplicate_idempotency_key_does_not_double_deduct_or_distribute(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)

        first = self.client.post(_repay_url(loan.id), {'idempotency_key': 'shared-key'}, format='json')
        second = self.client.post(_repay_url(loan.id), {'idempotency_key': 'shared-key'}, format='json')

        self.assertIn(first.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertIn(second.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(Repayment.objects.filter(borrower=self.borrower, idempotency_key='shared-key').count(), 1)
        self.assertEqual(Distribution.objects.count(), 3)
        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('972000.00'))
        self.investor_a.refresh_from_db()
        self.assertEqual(self.investor_a.balance, Decimal('109166.66'))

    # REQ-019
    def test_repay_by_non_borrower_returns_400_with_no_side_effects(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.investor_a)

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'not-borrower'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('loan', response.data)
        self.assertEqual(Repayment.objects.count(), 0)
        schedule1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        self.assertEqual(schedule1.status, RepaymentSchedule.Status.PENDING)
        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('1000000.00'))

    # REQ-020
    def test_repay_when_loan_not_active_returns_400_with_no_side_effects(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), term_months=12)
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'not-active'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('loan', response.data)
        self.assertEqual(Repayment.objects.count(), 0)
        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('1000000.00'))

    # REQ-021
    def test_repay_with_insufficient_balance_returns_400_with_no_side_effects(self):
        loan = self._create_active_loan_three_way()
        self.borrower.balance = Decimal('100.00')
        self.borrower.save()
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'poor'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('balance', response.data)
        self.assertEqual(Repayment.objects.count(), 0)
        schedule1 = RepaymentSchedule.objects.get(loan=loan, installment_number=1)
        self.assertEqual(schedule1.status, RepaymentSchedule.Status.PENDING)
        self.borrower.refresh_from_db()
        self.assertEqual(self.borrower.balance, Decimal('100.00'))
        self.assertEqual(Ledger.objects.filter(type=Ledger.Type.REPAY).count(), 0)

    # REQ-022 / REQ-023
    def test_repay_last_installment_completes_loan_and_further_repay_returns_400(self):
        loan = self._create_active_loan_single_investor(target_amount=Decimal('200000.00'), term_months=2)
        self.client.force_authenticate(user=self.borrower)

        first = self.client.post(_repay_url(loan.id), {'idempotency_key': 'final-1'}, format='json')
        second = self.client.post(_repay_url(loan.id), {'idempotency_key': 'final-2'}, format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.COMPLETED)

        third = self.client.post(_repay_url(loan.id), {'idempotency_key': 'final-3'}, format='json')
        self.assertEqual(third.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('loan', third.data)
        self.assertEqual(Repayment.objects.filter(loan=loan).count(), 2)

    # REQ-024
    def test_repay_without_authentication_returns_401(self):
        loan = self._create_active_loan_three_way()

        response = self.client.post(_repay_url(loan.id), {'idempotency_key': 'anon'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-025
    def test_repay_with_nonexistent_loan_returns_404(self):
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(999999), {'idempotency_key': 'none'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # REQ-026
    def test_repay_without_idempotency_key_returns_400(self):
        loan = self._create_active_loan_three_way()
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(_repay_url(loan.id), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


NEXT_REPAYMENT_URL = '/api/loans/mine/next-repayment/'


class NextRepaymentAPITests(APITestCase):
    """GET /api/loans/mine/next-repayment/ 다음 상환 예정 회차 조회 테스트."""

    def setUp(self):
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')
        self.borrower.balance = Decimal('1000000.00')
        self.borrower.save()
        self.other_borrower = User.objects.create_user(username='other', email='other@example.com', password='S7rongPass!2024')
        self.investor = User.objects.create_user(username='investor', email='investor@example.com', password='S7rongPass!2024')
        self.investor.balance = Decimal('1000000.00')
        self.investor.save()

    def _create_active_loan(self, user, target_amount=Decimal('300000.00'), term_months=12):
        application = LoanApplication.objects.create(
            user=user, amount=target_amount, purpose='사업자금', term_months=term_months,
            status=LoanApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            application=application, interest_rate=Decimal('12.00'), investor_rate=Decimal('10.00'),
            target_amount=target_amount, funded_amount=Decimal('0'), term_months=term_months,
            funding_deadline='2026-12-01', status=Loan.Status.FUNDRAISING,
        )
        create_investment(loan_id=loan.id, investor=self.investor, amount=target_amount, idempotency_key=f'fund-{loan.id}')
        loan.refresh_from_db()
        return loan

    def test_returns_next_pending_schedule_for_borrower(self):
        loan = self._create_active_loan(self.borrower)
        self.client.force_authenticate(user=self.borrower)

        response = self.client.get(NEXT_REPAYMENT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['loan_id'], loan.id)
        self.assertEqual(response.data['purpose'], '사업자금')
        self.assertEqual(response.data['installment_number'], 1)
        self.assertEqual(Decimal(response.data['total_amount']), Decimal('28000.00'))
        self.assertEqual(response.data['remaining_installments'], 12)

    def test_remaining_installments_decreases_after_a_repay(self):
        loan = self._create_active_loan(self.borrower)
        self.client.force_authenticate(user=self.borrower)
        self.client.post(_repay_url(loan.id), {'idempotency_key': 'repay-1'}, format='json')

        response = self.client.get(NEXT_REPAYMENT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['installment_number'], 2)
        self.assertEqual(response.data['remaining_installments'], 11)

    def test_not_scoped_to_other_borrowers_loans(self):
        self._create_active_loan(self.other_borrower)
        self.client.force_authenticate(user=self.borrower)

        response = self.client.get(NEXT_REPAYMENT_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_404_when_no_active_loan(self):
        self.client.force_authenticate(user=self.borrower)

        response = self.client.get(NEXT_REPAYMENT_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_without_authentication_returns_401(self):
        response = self.client.get(NEXT_REPAYMENT_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
