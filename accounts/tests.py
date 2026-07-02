from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

REGISTER_URL = '/api/auth/register/'
LOGIN_URL = '/api/auth/login/'


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
