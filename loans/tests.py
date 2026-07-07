from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from loans.models import Loan, LoanApplication

APPLICATIONS_URL = '/api/loans/applications/'
PENDING_URL = '/api/loans/applications/pending/'
LOANS_URL = '/api/loans/'


def approve_url(pk):
    return f'{APPLICATIONS_URL}{pk}/approve/'


def reject_url(pk):
    return f'{APPLICATIONS_URL}{pk}/reject/'


def loan_detail_url(pk):
    return f'{LOANS_URL}{pk}/'


class LoanApplicationCreateAPITests(APITestCase):
    """POST /api/loans/applications/ 대출 신청 API 테스트 (REQ-001, REQ-002, REQ-003)."""

    def setUp(self):
        self.user = User.objects.create_user(username='borrower', email='borrower@example.com', password='S7rongPass!2024')

    # REQ-001
    def test_create_with_valid_data_creates_pending_application(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(APPLICATIONS_URL, {
            'amount': '1000000.00', 'purpose': '사업자금', 'term_months': 12,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        application = LoanApplication.objects.get()
        self.assertEqual(application.user, self.user)
        self.assertEqual(application.status, LoanApplication.Status.PENDING)
        self.assertEqual(application.amount, Decimal('1000000.00'))

    # REQ-002
    def test_create_with_zero_amount_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(APPLICATIONS_URL, {
            'amount': '0', 'purpose': '사업자금', 'term_months': 12,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(LoanApplication.objects.count(), 0)

    # REQ-003
    def test_create_without_authentication_returns_401(self):
        response = self.client.post(APPLICATIONS_URL, {
            'amount': '1000000.00', 'purpose': '사업자금', 'term_months': 12,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LoanApplicationListAPITests(APITestCase):
    """GET /api/loans/applications/ 내 대출 신청 목록 API 테스트 (REQ-004, REQ-003)."""

    def setUp(self):
        self.user = User.objects.create_user(username='borrower2', email='borrower2@example.com', password='S7rongPass!2024')
        self.other_user = User.objects.create_user(username='other', email='other@example.com', password='S7rongPass!2024')

    # REQ-004
    def test_list_returns_only_own_applications_ordered_by_latest_first(self):
        older = LoanApplication.objects.create(user=self.user, amount=Decimal('500000'), purpose='A', term_months=6)
        newer = LoanApplication.objects.create(user=self.user, amount=Decimal('700000'), purpose='B', term_months=6)
        LoanApplication.objects.create(user=self.other_user, amount=Decimal('900000'), purpose='C', term_months=6)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(APPLICATIONS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], newer.id)
        self.assertEqual(results[1]['id'], older.id)

    # REQ-003
    def test_list_without_authentication_returns_401(self):
        response = self.client.get(APPLICATIONS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LoanApplicationPendingListAPITests(APITestCase):
    """GET /api/loans/applications/pending/ 관리자용 심사 대기 목록 API 테스트 (REQ-011, REQ-007, REQ-003)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin3', email='admin3@example.com', password='S7rongPass!2024', is_staff=True)
        self.borrower = User.objects.create_user(username='borrower7', email='borrower7@example.com', password='S7rongPass!2024')

    # REQ-011
    def test_pending_list_returns_only_pending_applications_across_all_users(self):
        pending = LoanApplication.objects.create(user=self.borrower, amount=Decimal('500000'), purpose='A', term_months=6)
        LoanApplication.objects.create(user=self.borrower, amount=Decimal('700000'), purpose='B', term_months=6, status=LoanApplication.Status.APPROVED)
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(PENDING_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], pending.id)

    # REQ-007
    def test_pending_list_by_non_admin_returns_403(self):
        self.client.force_authenticate(user=self.borrower)

        response = self.client.get(PENDING_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # REQ-003
    def test_pending_list_without_authentication_returns_401(self):
        response = self.client.get(PENDING_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LoanApplicationApproveAPITests(APITestCase):
    """POST /api/loans/applications/{id}/approve/ 승인 API 테스트 (REQ-005, REQ-006, REQ-007, REQ-008, REQ-012)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='S7rongPass!2024', is_staff=True)
        self.borrower = User.objects.create_user(username='borrower3', email='borrower3@example.com', password='S7rongPass!2024')
        self.application = LoanApplication.objects.create(
            user=self.borrower, amount=Decimal('1000000'), purpose='사업자금', term_months=12,
        )

    # REQ-005
    def test_approve_by_admin_creates_loan_and_sets_status_approved(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(approve_url(self.application.id), {
            'interest_rate': '15.00', 'investor_rate': '12.00', 'funding_deadline': '2026-08-01',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, LoanApplication.Status.APPROVED)
        loan = Loan.objects.get(application=self.application)
        self.assertEqual(loan.status, Loan.Status.FUNDRAISING)
        self.assertEqual(loan.target_amount, Decimal('1000000'))
        self.assertEqual(loan.interest_rate, Decimal('15.00'))
        self.assertEqual(loan.investor_rate, Decimal('12.00'))
        self.assertEqual(loan.funded_amount, Decimal('0'))

    # REQ-006
    def test_approve_with_investor_rate_gte_interest_rate_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(approve_url(self.application.id), {
            'interest_rate': '15.00', 'investor_rate': '15.00', 'funding_deadline': '2026-08-01',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Loan.objects.count(), 0)

    # REQ-012
    def test_approve_with_interest_rate_over_20_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(approve_url(self.application.id), {
            'interest_rate': '20.01', 'investor_rate': '12.00', 'funding_deadline': '2026-08-01',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Loan.objects.count(), 0)

    # REQ-007
    def test_approve_by_non_admin_returns_403(self):
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(approve_url(self.application.id), {
            'interest_rate': '15.00', 'investor_rate': '12.00', 'funding_deadline': '2026-08-01',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # REQ-008
    def test_approve_already_approved_application_returns_400(self):
        self.application.status = LoanApplication.Status.APPROVED
        self.application.save()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(approve_url(self.application.id), {
            'interest_rate': '15.00', 'investor_rate': '12.00', 'funding_deadline': '2026-08-01',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoanApplicationRejectAPITests(APITestCase):
    """POST /api/loans/applications/{id}/reject/ 거절 API 테스트 (REQ-009, REQ-007, REQ-008)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin2', email='admin2@example.com', password='S7rongPass!2024', is_staff=True)
        self.borrower = User.objects.create_user(username='borrower4', email='borrower4@example.com', password='S7rongPass!2024')
        self.application = LoanApplication.objects.create(
            user=self.borrower, amount=Decimal('1000000'), purpose='사업자금', term_months=12,
        )

    # REQ-009
    def test_reject_by_admin_sets_status_rejected_and_creates_no_loan(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(reject_url(self.application.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, LoanApplication.Status.REJECTED)
        self.assertEqual(Loan.objects.count(), 0)

    # REQ-007
    def test_reject_by_non_admin_returns_403(self):
        self.client.force_authenticate(user=self.borrower)

        response = self.client.post(reject_url(self.application.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # REQ-008
    def test_reject_already_processed_application_returns_400(self):
        self.application.status = LoanApplication.Status.REJECTED
        self.application.save()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(reject_url(self.application.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoanListAPITests(APITestCase):
    """GET /api/loans/ 대출 상품 목록 API 테스트 (REQ-010, REQ-003)."""

    def setUp(self):
        self.user = User.objects.create_user(username='viewer', email='viewer@example.com', password='S7rongPass!2024')
        self.borrower = User.objects.create_user(username='borrower5', email='borrower5@example.com', password='S7rongPass!2024')

    def _create_loan(self, amount):
        application = LoanApplication.objects.create(
            user=self.borrower, amount=amount, purpose='P', term_months=12, status=LoanApplication.Status.APPROVED,
        )
        return Loan.objects.create(
            application=application, interest_rate=Decimal('15.00'), investor_rate=Decimal('12.00'),
            target_amount=amount, term_months=12, funding_deadline='2026-08-01',
        )

    # REQ-010
    def test_list_returns_all_loans_ordered_by_latest_first(self):
        older = self._create_loan(Decimal('500000'))
        newer = self._create_loan(Decimal('700000'))
        self.client.force_authenticate(user=self.user)

        response = self.client.get(LOANS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], newer.id)
        self.assertEqual(results[1]['id'], older.id)

    # REQ-013
    def test_list_without_authentication_returns_200(self):
        self._create_loan(Decimal('500000'))

        response = self.client.get(LOANS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    # REQ-013
    def test_list_filters_by_status(self):
        fundraising = self._create_loan(Decimal('500000'))
        active = self._create_loan(Decimal('700000'))
        active.status = Loan.Status.ACTIVE
        active.save()

        response = self.client.get(f'{LOANS_URL}?status=FUNDRAISING')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], fundraising.id)


class LoanDetailAPITests(APITestCase):
    """GET /api/loans/{id}/ 대출 상품 상세 API 테스트 (REQ-010)."""

    def setUp(self):
        self.user = User.objects.create_user(username='viewer2', email='viewer2@example.com', password='S7rongPass!2024')
        self.borrower = User.objects.create_user(username='borrower6', email='borrower6@example.com', password='S7rongPass!2024')
        application = LoanApplication.objects.create(
            user=self.borrower, amount=Decimal('1000000'), purpose='P', term_months=12, status=LoanApplication.Status.APPROVED,
        )
        self.loan = Loan.objects.create(
            application=application, interest_rate=Decimal('15.00'), investor_rate=Decimal('12.00'),
            target_amount=Decimal('1000000'), term_months=12, funding_deadline='2026-08-01',
        )

    def test_detail_returns_loan(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(loan_detail_url(self.loan.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.loan.id)
        self.assertEqual(response.data['purpose'], 'P')

    def test_detail_not_found_returns_404(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(loan_detail_url(999999))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # REQ-013
    def test_detail_without_authentication_returns_200(self):
        response = self.client.get(loan_detail_url(self.loan.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
