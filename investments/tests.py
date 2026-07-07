from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from investments.models import Investment
from ledger.models import Ledger
from loans.models import Loan, LoanApplication

INVEST_URL = '/api/investments/'


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
        self.assertEqual(Ledger.objects.filter(user=self.investor, type=Ledger.Type.INVEST).count(), 1)
