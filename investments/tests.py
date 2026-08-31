from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from investments.models import Investment
from investments.services import create_investment
from ledger.models import Ledger
from loans import services as loan_services
from loans.models import Loan, LoanApplication
from repayments.models import Distribution
from repayments.services import repay

INVEST_URL = '/api/investments/'
MINE_URL = '/api/investments/mine/'
MONTHLY_RETURNS_URL = '/api/investments/monthly-returns/'


class InvestmentCreateAPITests(APITestCase):
    """POST /api/investments/ 투자 실행 API 테스트 (REQ-001~010)."""

    def setUp(self):
        self.investor = User.objects.create_user(username='investor', email='investor@example.com', password='S7rongPass!2024')
        self.investor.balance = Decimal('1000000.00')
        self.investor.save()
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')

    def _create_loan(self, target_amount, funded_amount=Decimal('0'), loan_status=Loan.Status.FUNDRAISING):
        application = LoanApplication.objects.create(
            user=self.borrower, amount=target_amount, purpose='사업자금', term_months=12,
            status=LoanApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            application=application, interest_rate=Decimal('15.00'), investor_rate=Decimal('12.00'),
            target_amount=target_amount, funded_amount=funded_amount, term_months=12,
            funding_deadline='2026-08-01', status=loan_status,
        )
        return loan

    # REQ-001
    def test_create_with_valid_data_creates_investment_and_returns_201(self):
        loan = self._create_loan(target_amount=Decimal('1000000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'key-1',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        investment = Investment.objects.get()
        self.assertEqual(response.data['id'], investment.id)
        self.assertEqual(response.data['loan'], loan.id)
        self.assertEqual(Decimal(response.data['amount']), Decimal('300000.00'))
        self.assertEqual(response.data['idempotency_key'], 'key-1')
        self.assertIn('created_at', response.data)
        self.assertEqual(investment.investor, self.investor)
        self.assertEqual(investment.amount, Decimal('300000.00'))

    # REQ-002
    def test_create_deducts_balance_and_creates_invest_ledger(self):
        loan = self._create_loan(target_amount=Decimal('1000000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'key-2',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.investor.refresh_from_db()
        self.assertEqual(self.investor.balance, Decimal('700000.00'))
        ledger = Ledger.objects.get(user=self.investor)
        self.assertEqual(ledger.type, Ledger.Type.INVEST)
        self.assertEqual(ledger.amount, Decimal('300000.00'))
        self.assertEqual(ledger.balance_after, Decimal('700000.00'))

    # REQ-003
    def test_create_accumulates_loan_funded_amount(self):
        loan = self._create_loan(target_amount=Decimal('1000000'), funded_amount=Decimal('200000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'key-3',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        loan.refresh_from_db()
        self.assertEqual(loan.funded_amount, Decimal('500000.00'))

    # REQ-004
    def test_create_reaching_target_amount_sets_loan_status_active(self):
        loan = self._create_loan(target_amount=Decimal('1000000'), funded_amount=Decimal('700000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'key-4',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        loan.refresh_from_db()
        self.assertEqual(loan.funded_amount, Decimal('1000000.00'))
        self.assertEqual(loan.status, Loan.Status.ACTIVE)

    # REQ-004 (경계값 - 미달)
    def test_create_not_reaching_target_amount_keeps_fundraising(self):
        loan = self._create_loan(target_amount=Decimal('1000000'), funded_amount=Decimal('700000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '299999.99', 'idempotency_key': 'key-4b',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.FUNDRAISING)

    # REQ-005
    def test_create_when_loan_not_fundraising_returns_400_with_no_side_effects(self):
        loan = self._create_loan(target_amount=Decimal('1000000'), funded_amount=Decimal('1000000'), loan_status=Loan.Status.ACTIVE)
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '100000.00', 'idempotency_key': 'key-5',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('loan', response.data)
        self.investor.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.investor.balance, Decimal('1000000.00'))
        self.assertEqual(loan.funded_amount, Decimal('1000000.00'))
        self.assertEqual(Ledger.objects.count(), 0)
        self.assertEqual(Investment.objects.count(), 0)

    # REQ-006
    def test_create_amount_exceeding_remaining_target_returns_400_with_no_side_effects(self):
        loan = self._create_loan(target_amount=Decimal('1000000'), funded_amount=Decimal('800000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'key-6',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        self.investor.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.investor.balance, Decimal('1000000.00'))
        self.assertEqual(loan.funded_amount, Decimal('800000.00'))
        self.assertEqual(Ledger.objects.count(), 0)
        self.assertEqual(Investment.objects.count(), 0)

    # REQ-007
    def test_create_amount_exceeding_investor_balance_returns_400_with_no_side_effects(self):
        loan = self._create_loan(target_amount=Decimal('10000000'))
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '1000000.01', 'idempotency_key': 'key-7',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', response.data)
        self.investor.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.investor.balance, Decimal('1000000.00'))
        self.assertEqual(loan.funded_amount, Decimal('0'))
        self.assertEqual(Ledger.objects.count(), 0)
        self.assertEqual(Investment.objects.count(), 0)

    # REQ-008
    def test_create_with_nonexistent_loan_returns_404(self):
        self.client.force_authenticate(user=self.investor)

        response = self.client.post(INVEST_URL, {
            'loan_id': 999999, 'amount': '100000.00', 'idempotency_key': 'key-8',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # REQ-009
    def test_create_without_authentication_returns_401(self):
        loan = self._create_loan(target_amount=Decimal('1000000'))

        response = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '100000.00', 'idempotency_key': 'key-9',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-010
    def test_create_with_duplicate_idempotency_key_does_not_duplicate_side_effects(self):
        loan = self._create_loan(target_amount=Decimal('1000000'))
        self.client.force_authenticate(user=self.investor)

        first = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'shared-key',
        }, format='json')
        second = self.client.post(INVEST_URL, {
            'loan_id': loan.id, 'amount': '300000.00', 'idempotency_key': 'shared-key',
        }, format='json')

        self.assertIn(first.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertIn(second.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(Investment.objects.filter(investor=self.investor, idempotency_key='shared-key').count(), 1)
        self.investor.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(self.investor.balance, Decimal('700000.00'))
        self.assertEqual(loan.funded_amount, Decimal('300000.00'))


class MyInvestmentListAPITests(APITestCase):
    """GET /api/investments/mine/ 내 투자 목록 조회 API 테스트."""

    def setUp(self):
        self.investor = User.objects.create_user(username='investor', email='investor@example.com', password='S7rongPass!2024')
        self.investor.balance = Decimal('1000000.00')
        self.investor.save()
        self.other_investor = User.objects.create_user(username='other_inv', email='other_inv@example.com', password='S7rongPass!2024')
        self.other_investor.balance = Decimal('1000000.00')
        self.other_investor.save()
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')
        self.borrower.balance = Decimal('1000000.00')
        self.borrower.save()

    def _create_loan(self, target_amount, term_months=12, interest_rate=Decimal('12.00'), investor_rate=Decimal('10.00'), funding_deadline='2026-12-01'):
        application = LoanApplication.objects.create(
            user=self.borrower, amount=target_amount, purpose='사업자금', term_months=term_months,
            status=LoanApplication.Status.APPROVED,
        )
        return Loan.objects.create(
            application=application, interest_rate=interest_rate, investor_rate=investor_rate,
            target_amount=target_amount, funded_amount=Decimal('0'), term_months=term_months,
            funding_deadline=funding_deadline, status=Loan.Status.FUNDRAISING,
        )

    def test_returns_only_my_investments(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'))
        create_investment(loan_id=loan.id, investor=self.investor, amount=Decimal('100000.00'), idempotency_key='mine-1')
        create_investment(loan_id=loan.id, investor=self.other_investor, amount=Decimal('100000.00'), idempotency_key='other-1')
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MINE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['amount'], '100000.00')
        self.assertEqual(results[0]['purpose'], '사업자금')
        self.assertEqual(results[0]['loan_status'], Loan.Status.FUNDRAISING)

    def test_empty_list_for_investor_with_no_investments(self):
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MINE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'], [])

    def test_without_authentication_returns_401(self):
        response = self.client.get(MINE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_active_loan_includes_earned_progress_and_next_estimate(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'))
        create_investment(loan_id=loan.id, investor=self.investor, amount=Decimal('100000.00'), idempotency_key='inv-1')
        create_investment(loan_id=loan.id, investor=self.other_investor, amount=Decimal('100000.00'), idempotency_key='inv-2')
        create_investment(loan_id=loan.id, investor=self.other_investor, amount=Decimal('100000.00'), idempotency_key='inv-3')
        repay(loan_id=loan.id, borrower=self.borrower, idempotency_key='repay-1')
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MINE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['results'][0]
        self.assertEqual(item['loan_status'], Loan.Status.ACTIVE)
        # 1회차 상환분: 투자 비율대로 분배받은 실제 금액(원 단위 올림).
        self.assertEqual(item['earned'], '9167')
        # 12회차 중 1회 완납.
        self.assertEqual(item['progress'], round(1 / 12, 4))
        loan.refresh_from_db()
        schedule2 = loan.repayment_schedules.get(installment_number=2)
        self.assertEqual(item['next_due_date'], str(schedule2.due_date))
        # 2회차 예상 분배금(원금 25,000 + 투자자 몫 이자 2,291.67)의 1/3 지분, 반올림.
        self.assertEqual(item['estimated_next_amount'], '9097')

    def test_completed_loan_has_no_next_estimate(self):
        loan = self._create_loan(target_amount=Decimal('200000.00'), term_months=2)
        create_investment(loan_id=loan.id, investor=self.investor, amount=Decimal('200000.00'), idempotency_key='solo-1')
        repay(loan_id=loan.id, borrower=self.borrower, idempotency_key='final-1')
        repay(loan_id=loan.id, borrower=self.borrower, idempotency_key='final-2')
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MINE_URL)

        item = response.data['results'][0]
        self.assertEqual(item['loan_status'], Loan.Status.COMPLETED)
        self.assertIsNone(item['next_due_date'])
        self.assertIsNone(item['estimated_next_amount'])

    def test_cancelled_loan_shows_status_with_no_estimate(self):
        loan = self._create_loan(target_amount=Decimal('300000.00'), funding_deadline='2020-01-01')
        create_investment(loan_id=loan.id, investor=self.investor, amount=Decimal('100000.00'), idempotency_key='cancel-1')
        loan_services.expire_fundraising_loans()
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MINE_URL)

        item = response.data['results'][0]
        self.assertEqual(item['loan_status'], Loan.Status.CANCELLED)
        self.assertIsNone(item['next_due_date'])
        self.assertEqual(item['earned'], '0')


class MonthlyReturnsAPITests(APITestCase):
    """GET /api/investments/monthly-returns/ 월별 수익 추이 조회 API 테스트."""

    def setUp(self):
        self.investor = User.objects.create_user(username='investor', email='investor@example.com', password='S7rongPass!2024')
        self.borrower = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')
        self.borrower.balance = Decimal('1000000.00')
        self.borrower.save()

    def test_without_authentication_returns_401(self):
        response = self.client.get(MONTHLY_RETURNS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_12_months_zero_filled_with_current_month_total(self):
        application = LoanApplication.objects.create(
            user=self.borrower, amount=Decimal('200000.00'), purpose='사업자금', term_months=2,
            status=LoanApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            application=application, interest_rate=Decimal('12.00'), investor_rate=Decimal('10.00'),
            target_amount=Decimal('200000.00'), funded_amount=Decimal('0'), term_months=2,
            funding_deadline='2026-12-01', status=Loan.Status.FUNDRAISING,
        )
        create_investment(loan_id=loan.id, investor=self.investor, amount=Decimal('200000.00'), idempotency_key='mr-1')
        repay(loan_id=loan.id, borrower=self.borrower, idempotency_key='mr-repay-1')
        self.client.force_authenticate(user=self.investor)

        response = self.client.get(MONTHLY_RETURNS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        months = response.data['results']
        self.assertEqual(len(months), 12)
        this_month_total = Distribution.objects.filter(investor=self.investor).aggregate(total=Sum('amount'))['total']
        current_month_label = timezone.now().strftime('%Y-%m')
        current = next(m for m in months if m['month'] == current_month_label)
        self.assertEqual(Decimal(current['total']), this_month_total)
        other_months = [m for m in months if m['month'] != current_month_label]
        self.assertTrue(all(m['total'] == '0' for m in other_months))
        self.assertEqual(Ledger.objects.filter(user=self.investor, type=Ledger.Type.INVEST).count(), 1)
