import threading

from django.db import connection
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import PLATFORM_USERNAME, BankAccount, User

REGISTER_URL = '/api/auth/register/'
LOGIN_URL = '/api/auth/login/'
PROFILE_URL = '/api/auth/me/'
PASSWORD_URL = '/api/auth/password/'
LOGOUT_URL = '/api/auth/logout/'
BANK_ACCOUNTS_URL = '/api/auth/bank-accounts/'


def set_primary_url(pk):
    return f'/api/auth/bank-accounts/{pk}/set-primary/'


class RegisterAPITests(APITestCase):
    """POST /api/auth/register/ 에 대한 회원가입 API 테스트 (REQ-001~008)."""

    def valid_payload(self, **overrides):
        payload = {
            'username': 'newuser01',
            'email': 'newuser01@example.com',
            'password': 'S7rongPass!2024',
            'password_confirm': 'S7rongPass!2024',
            'first_name': '홍길동',
        }
        payload.update(overrides)
        return payload

    # REQ-001
    def test_register_with_valid_data_creates_user_and_returns_201(self):
        response = self.client.post(REGISTER_URL, self.valid_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['first_name'], '홍길동')
        self.assertEqual(User.objects.get(username='newuser01').first_name, '홍길동')

    # REQ-007 (성공 응답에 비밀번호 관련 필드가 없어야 함)
    def test_register_success_response_does_not_expose_password_fields(self):
        response = self.client.post(REGISTER_URL, self.valid_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_confirm', response.data)

    # REQ-002
    def test_register_with_mismatched_password_confirm_returns_400_and_no_user_created(self):
        payload = self.valid_payload(password_confirm='DifferentPass!9999')

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username='newuser01').exists())

    # REQ-003
    def test_register_with_duplicate_username_returns_400(self):
        User.objects.create_user(
            username='dupuser',
            email='original@example.com',
            password='S7rongPass!2024',
        )

        payload = self.valid_payload(username='dupuser', email='another@example.com')
        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-004
    def test_register_with_duplicate_email_returns_400(self):
        User.objects.create_user(
            username='original_owner',
            email='dupemail@example.com',
            password='S7rongPass!2024',
        )

        payload = self.valid_payload(username='newuser02', email='dupemail@example.com')
        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-005: 비밀번호가 너무 짧음 (MinimumLengthValidator)
    def test_register_with_too_short_password_returns_400(self):
        payload = self.valid_payload(password='abc123', password_confirm='abc123')

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-005: 숫자로만 이루어진 비밀번호 (NumericPasswordValidator)
    def test_register_with_numeric_only_password_returns_400(self):
        payload = self.valid_payload(password='394857203984', password_confirm='394857203984')

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-005: 흔한 비밀번호 (CommonPasswordValidator)
    def test_register_with_common_password_returns_400(self):
        payload = self.valid_payload(password='password123', password_confirm='password123')

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-005: username과 유사한 비밀번호 (UserAttributeSimilarityValidator)
    def test_register_with_password_similar_to_username_returns_400(self):
        payload = self.valid_payload(username='similaruser99', password='similaruser99', password_confirm='similaruser99')

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-006: 필드 누락
    def test_register_missing_username_returns_400(self):
        payload = self.valid_payload()
        del payload['username']

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_email_returns_400(self):
        payload = self.valid_payload()
        del payload['email']

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_password_returns_400(self):
        payload = self.valid_payload()
        del payload['password']

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_password_confirm_returns_400(self):
        payload = self.valid_payload()
        del payload['password_confirm']

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_first_name_returns_400(self):
        payload = self.valid_payload()
        del payload['first_name']

        response = self.client.post(REGISTER_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-008: 비로그인 상태(인증 헤더 없음)로 접근 가능해야 함
    def test_register_is_accessible_without_authentication(self):
        # APIClient는 기본적으로 인증 헤더를 보내지 않는다 (비로그인 상태).
        response = self.client.post(REGISTER_URL, self.valid_payload(), format='json')

        self.assertNotIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class LoginAPITests(APITestCase):
    """POST /api/auth/login/ 에 대한 로그인 API 테스트 (REQ-009~012)."""

    def setUp(self):
        self.existing_user = User.objects.create_user(
            username='loginuser',
            email='loginuser@example.com',
            password='S7rongPass!2024',
        )

    # REQ-009
    def test_login_with_correct_credentials_returns_200_with_tokens(self):
        response = self.client.post(
            LOGIN_URL,
            {'username': 'loginuser', 'password': 'S7rongPass!2024'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    # REQ-010: 존재하지 않는 계정
    def test_login_with_nonexistent_username_returns_401(self):
        response = self.client.post(
            LOGIN_URL,
            {'username': 'ghost_user', 'password': 'WhateverPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-010: 틀린 비밀번호
    def test_login_with_wrong_password_returns_401(self):
        response = self.client.post(
            LOGIN_URL,
            {'username': 'loginuser', 'password': 'WrongPassword!999'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-010: 두 케이스(계정 없음/비밀번호 오류) 모두 동일하게 401로 응답해야 함
    def test_login_failure_reason_is_not_distinguishable_between_no_account_and_wrong_password(self):
        response_no_account = self.client.post(
            LOGIN_URL,
            {'username': 'ghost_user', 'password': 'WhateverPass123!'},
            format='json',
        )
        response_wrong_password = self.client.post(
            LOGIN_URL,
            {'username': 'loginuser', 'password': 'WrongPassword!999'},
            format='json',
        )

        self.assertEqual(response_no_account.status_code, response_wrong_password.status_code)
        self.assertEqual(response_no_account.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response_no_account.data, response_wrong_password.data)

    # REQ-011: 필드 누락
    def test_login_missing_username_returns_400(self):
        response = self.client.post(
            LOGIN_URL,
            {'password': 'S7rongPass!2024'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_missing_password_returns_400(self):
        response = self.client.post(
            LOGIN_URL,
            {'username': 'loginuser'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-012: 비로그인 상태(인증 헤더 없음)로 접근 가능해야 함
    def test_login_is_accessible_without_authentication(self):
        # APIClient는 기본적으로 인증 헤더를 보내지 않는다 (비로그인 상태).
        response = self.client.post(
            LOGIN_URL,
            {'username': 'loginuser', 'password': 'S7rongPass!2024'},
            format='json',
        )

        self.assertNotIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProfileAPITests(APITestCase):
    """GET /api/auth/me/ 에 대한 본인 프로필 조회 API 테스트 (REQ-013~015)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='profileuser',
            email='profileuser@example.com',
            password='S7rongPass!2024',
            first_name='홍길동',
            phone_number='010-1234-5678',
        )

    # REQ-013
    def test_get_profile_with_authenticated_user_returns_200_with_expected_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field in ('id', 'username', 'email', 'first_name', 'phone_number', 'balance', 'created_at'):
            self.assertIn(field, response.data)
        self.assertEqual(response.data['username'], 'profileuser')
        self.assertEqual(response.data['email'], 'profileuser@example.com')

    # REQ-014: 비밀번호 관련 필드가 응답에 없어야 함
    def test_get_profile_response_does_not_expose_password_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('password', response.data)

    # REQ-015: 인증 없이 요청하면 401
    def test_get_profile_without_authentication_returns_401(self):
        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordChangeAPITests(APITestCase):
    """PUT /api/auth/password/ 에 대한 비밀번호 변경 API 테스트 (REQ-016~024)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='pwchangeuser',
            email='pwchangeuser@example.com',
            password='OldPass!2024',
        )

    def valid_payload(self, **overrides):
        payload = {
            'current_password': 'OldPass!2024',
            'new_password': 'NewStr0ngPass!2025',
            'new_password_confirm': 'NewStr0ngPass!2025',
        }
        payload.update(overrides)
        return payload

    # REQ-016
    def test_change_password_with_valid_data_returns_200_and_new_password_works(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(PASSWORD_URL, self.valid_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStr0ngPass!2025'))

    # REQ-017: current_password가 틀림
    def test_change_password_with_wrong_current_password_returns_400_and_password_unchanged(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(current_password='WrongCurrent!999'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass!2024'))

    # REQ-018: new_password != new_password_confirm
    def test_change_password_with_mismatched_confirmation_returns_400_and_password_unchanged(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(new_password_confirm='Different!9999'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass!2024'))

    # REQ-019: new_password == current_password
    def test_change_password_with_same_as_current_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(new_password='OldPass!2024', new_password_confirm='OldPass!2024'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-020: 새 비밀번호가 검증 규칙 위반 (너무 짧음)
    def test_change_password_with_too_short_new_password_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(new_password='abc123', new_password_confirm='abc123'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-020: 새 비밀번호가 숫자로만 이루어짐
    def test_change_password_with_numeric_only_new_password_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(new_password='394857203984', new_password_confirm='394857203984'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-020: 흔한 비밀번호
    def test_change_password_with_common_new_password_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            PASSWORD_URL,
            self.valid_payload(new_password='password123', new_password_confirm='password123'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-021: 필드 누락
    def test_change_password_missing_current_password_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self.valid_payload()
        del payload['current_password']

        response = self.client.put(PASSWORD_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_missing_new_password_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self.valid_payload()
        del payload['new_password']

        response = self.client.put(PASSWORD_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_missing_new_password_confirm_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self.valid_payload()
        del payload['new_password_confirm']

        response = self.client.put(PASSWORD_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-022: 인증 없이 요청 → 401
    def test_change_password_without_authentication_returns_401(self):
        response = self.client.put(PASSWORD_URL, self.valid_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-023: 인증 없이 요청 시 비밀번호가 변경되지 않아야 함
    def test_change_password_without_authentication_does_not_change_password(self):
        self.client.put(PASSWORD_URL, self.valid_payload(), format='json')

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass!2024'))

    # REQ-024: PATCH로 current_password를 빼도 부분 검증으로 우회되지 않아야 함
    def test_change_password_with_patch_and_missing_current_password_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self.valid_payload()
        del payload['current_password']

        response = self.client.patch(PASSWORD_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass!2024'))


class LogoutAPITests(APITestCase):
    """POST /api/auth/logout/ 에 대한 로그아웃(refresh 토큰 블랙리스트) API 테스트 (REQ-025~028)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser',
            email='logoutuser@example.com',
            password='S7rongPass!2024',
        )
        self.refresh = str(RefreshToken.for_user(self.user))

    # REQ-025
    def test_logout_with_valid_refresh_returns_200(self):
        response = self.client.post(LOGOUT_URL, {'refresh': self.refresh}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # REQ-025: 블랙리스트 등록으로 재발급(refresh)에 더 이상 쓸 수 없어야 함
    def test_logout_reused_refresh_token_returns_401(self):
        self.client.post(LOGOUT_URL, {'refresh': self.refresh}, format='json')

        response = self.client.post(LOGOUT_URL, {'refresh': self.refresh}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-026: refresh 필드 누락
    def test_logout_missing_refresh_returns_400(self):
        response = self.client.post(LOGOUT_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-027: 잘못된(위조/손상) refresh 토큰
    def test_logout_with_malformed_refresh_returns_401(self):
        response = self.client.post(LOGOUT_URL, {'refresh': 'not-a-real-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-028: 인증 헤더(access 토큰) 없이도 refresh 토큰만으로 접근 가능해야 함
    def test_logout_is_accessible_without_authentication_header(self):
        response = self.client.post(LOGOUT_URL, {'refresh': self.refresh}, format='json')

        self.assertNotIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class BankAccountAPITests(APITestCase):
    """GET/POST /api/auth/bank-accounts/, POST .../set-primary/ 에 대한 계좌 관리 API 테스트 (REQ-001~004)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='bankuser', email='bankuser@example.com', password='S7rongPass!2024',
        )
        self.other_user = User.objects.create_user(
            username='otheruser', email='otheruser@example.com', password='S7rongPass!2024',
        )

    def valid_payload(self, **overrides):
        payload = {'bank_name': 'KB국민', 'account_number': '123-456-789', 'account_holder': '홍길동'}
        payload.update(overrides)
        return payload

    # REQ-001
    def test_list_returns_only_own_accounts(self):
        BankAccount.objects.create(user=self.user, bank_name='KB국민', account_number='111', account_holder='홍길동')
        BankAccount.objects.create(user=self.other_user, bank_name='신한', account_number='222', account_holder='김철수')
        self.client.force_authenticate(user=self.user)

        response = self.client.get(BANK_ACCOUNTS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bank_name'], 'KB국민')

    # REQ-010
    def test_list_without_authentication_returns_401(self):
        response = self.client.get(BANK_ACCOUNTS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # REQ-002: 첫 계좌는 자동으로 기본계좌가 되어야 함
    def test_create_first_account_is_automatically_primary(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(BANK_ACCOUNTS_URL, self.valid_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['is_primary'])

    # REQ-002: 두 번째 계좌는 기본계좌로 지정하지 않는 한 기본계좌가 아니어야 함
    def test_create_second_account_is_not_primary_by_default(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(BANK_ACCOUNTS_URL, self.valid_payload(), format='json')

        response = self.client.post(BANK_ACCOUNTS_URL, self.valid_payload(account_number='999'), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['is_primary'])

    def test_create_missing_required_field_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self.valid_payload()
        del payload['bank_name']

        response = self.client.post(BANK_ACCOUNTS_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # REQ-003
    def test_set_primary_switches_primary_atomically(self):
        self.client.force_authenticate(user=self.user)
        first = BankAccount.objects.create(user=self.user, bank_name='KB국민', account_number='111', account_holder='홍길동', is_primary=True)
        second = BankAccount.objects.create(user=self.user, bank_name='신한', account_number='222', account_holder='홍길동', is_primary=False)

        response = self.client.post(set_primary_url(second.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    # REQ-004
    def test_set_primary_on_other_users_account_returns_404(self):
        self.client.force_authenticate(user=self.user)
        other_account = BankAccount.objects.create(user=self.other_user, bank_name='신한', account_number='222', account_holder='김철수')

        response = self.client.post(set_primary_url(other_account.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BankAccountRaceConditionAPITests(TransactionTestCase):
    """계좌 동시 등록 시 기본계좌 중복 지정 레이스컨디션 재현 테스트 (실제 스레드/DB 트랜잭션 필요)."""

    # TransactionTestCase는 테스트 후 전체 테이블을 flush하는데, serialized_rollback 없이는
    # 데이터 마이그레이션으로 심어둔 row(예: platform 계좌)까지 같이 날아가 이후 테스트에 영향을 준다.
    serialized_rollback = True

    def setUp(self):
        self.user = User.objects.create_user(
            username='raceuser', email='raceuser@example.com', password='S7rongPass!2024',
        )

    def test_concurrent_first_account_creation_results_in_single_primary(self):
        barrier = threading.Barrier(5)
        responses = []

        def worker(i):
            client = APIClient()
            client.force_authenticate(user=self.user)
            barrier.wait()
            responses.append(client.post(
                BANK_ACCOUNTS_URL,
                {'bank_name': 'KB국민', 'account_number': str(i), 'account_holder': '홍길동'},
                format='json',
            ))
            connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(all(r.status_code == status.HTTP_201_CREATED for r in responses))
        primary_count = BankAccount.objects.filter(user=self.user, is_primary=True).count()
        self.assertEqual(primary_count, 1)


ADMIN_USERS_URL = '/api/auth/admin/users/'


class AdminUserListAPITests(APITestCase):
    """GET /api/auth/admin/users/ 관리자용 회원 목록 조회 API 테스트."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_ul', email='admin_ul@example.com', password='S7rongPass!2024', is_staff=True,
        )
        self.member = User.objects.create_user(username='member_ul', email='member_ul@example.com', password='S7rongPass!2024')
        User.objects.get_or_create(username=PLATFORM_USERNAME, defaults={'email': 'platform_ul@example.com'})

    def test_admin_sees_all_users_excluding_platform_account(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(ADMIN_USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u['username'] for u in response.data['results']]
        self.assertIn('admin_ul', usernames)
        self.assertIn('member_ul', usernames)
        self.assertNotIn(PLATFORM_USERNAME, usernames)

    def test_non_admin_returns_403(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.get(ADMIN_USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_without_authentication_returns_401(self):
        response = self.client.get(ADMIN_USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
