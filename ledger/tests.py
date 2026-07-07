from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from ledger.models import Ledger

CHARGE_URL = '/api/ledger/charge/'
WITHDRAW_URL = '/api/ledger/withdraw/'
HISTORY_URL = '/api/ledger/'


class ChargeAPITests(APITestCase):
    """POST /api/ledger/charge/ 에 대한 예치금 충전 API 테스트 (REQ-005, REQ-006, REQ-010)."""

    def setUp(self):
        self.user = User.objects.create_user(username='chargeuser', email='chargeuser@example.com', password='S7rongPass!2024')
        self.user.balance = Decimal('10000.00')
        self.user.save()

    # REQ-005
    def test_charge_with_positive_amount_increases_balance_and_creates_ledger(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(CHARGE_URL, {'amount': '5000.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('15000.00'))
        ledger = Ledger.objects.get(user=self.user)
        self.assertEqual(ledger.type, Ledger.Type.CHARGE)
        self.assertEqual(ledger.amount, Decimal('5000.00'))
        self.assertEqual(ledger.balance_after, Decimal('15000.00'))

    # REQ-006
    def test_charge_with_zero_amount_returns_400_and_does_not_change_balance(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(CHARGE_URL, {'amount': '0'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('10000.00'))
        self.assertEqual(Ledger.objects.count(), 0)

    # REQ-006
    def test_charge_with_negative_amount_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(CHARGE_URL, {'amount': '-100'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-006
    def test_charge_missing_amount_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(CHARGE_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-010
    def test_charge_without_authentication_returns_401(self):
        response = self.client.post(CHARGE_URL, {'amount': '5000.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class WithdrawAPITests(APITestCase):
    """POST /api/ledger/withdraw/ 에 대한 예치금 출금 API 테스트 (REQ-007, REQ-008, REQ-010)."""

    def setUp(self):
        self.user = User.objects.create_user(username='withdrawuser', email='withdrawuser@example.com', password='S7rongPass!2024')
        self.user.balance = Decimal('10000.00')
        self.user.save()

    # REQ-007
    def test_withdraw_with_sufficient_balance_decreases_balance_and_creates_ledger(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(WITHDRAW_URL, {'amount': '4000.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('6000.00'))
        ledger = Ledger.objects.get(user=self.user)
        self.assertEqual(ledger.type, Ledger.Type.WITHDRAW)
        self.assertEqual(ledger.amount, Decimal('4000.00'))
        self.assertEqual(ledger.balance_after, Decimal('6000.00'))

    # REQ-008
    def test_withdraw_exceeding_balance_returns_400_and_does_not_change_balance(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(WITHDRAW_URL, {'amount': '10000.01'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, Decimal('10000.00'))
        self.assertEqual(Ledger.objects.count(), 0)

    # REQ-006 (동일 검증 로직 공유)
    def test_withdraw_with_zero_amount_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(WITHDRAW_URL, {'amount': '0'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-010
    def test_withdraw_without_authentication_returns_401(self):
        response = self.client.post(WITHDRAW_URL, {'amount': '1000.00'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LedgerHistoryAPITests(APITestCase):
    """GET /api/ledger/ 에 대한 거래 내역 조회 API 테스트 (REQ-009, REQ-010)."""

    def setUp(self):
        self.user = User.objects.create_user(username='historyuser', email='historyuser@example.com', password='S7rongPass!2024')
        self.other_user = User.objects.create_user(username='otheruser2', email='otheruser2@example.com', password='S7rongPass!2024')

    # REQ-009
    def test_history_returns_only_own_records_ordered_by_latest_first(self):
        older = Ledger.objects.create(user=self.user, type=Ledger.Type.CHARGE, amount=Decimal('1000'), balance_after=Decimal('1000'))
        newer = Ledger.objects.create(user=self.user, type=Ledger.Type.WITHDRAW, amount=Decimal('200'), balance_after=Decimal('800'))
        Ledger.objects.create(user=self.other_user, type=Ledger.Type.CHARGE, amount=Decimal('5000'), balance_after=Decimal('5000'))
        self.client.force_authenticate(user=self.user)

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], newer.id)
        self.assertEqual(results[1]['id'], older.id)

    # REQ-010
    def test_history_without_authentication_returns_401(self):
        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
