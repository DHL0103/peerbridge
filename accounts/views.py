from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import PLATFORM_USERNAME, BankAccount, User
from accounts.serializers import (
    AdminUserSerializer, BankAccountSerializer, PasswordChangeSerializer, ProfileSerializer, RegisterSerializer,
)


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ 회원가입 API."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = RegisterSerializer


class ProfileView(generics.RetrieveAPIView):
    """GET /api/auth/me/ 본인 프로필 조회 API."""

    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.UpdateAPIView):
    """PUT /api/auth/password/ 비밀번호 변경 API."""

    serializer_class = PasswordChangeSerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': '비밀번호가 변경되었습니다.'})


class BankAccountListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/auth/bank-accounts/ 계좌 목록 조회/등록 API."""

    serializer_class = BankAccountSerializer

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user)


class BankAccountSetPrimaryView(APIView):
    """POST /api/auth/bank-accounts/{id}/set-primary/ 기본계좌 설정 API."""

    def post(self, request, pk):
        account = get_object_or_404(BankAccount, pk=pk, user=request.user)

        with transaction.atomic():
            BankAccount.objects.filter(user=request.user).exclude(pk=account.pk).update(is_primary=False)
            account.is_primary = True
            account.save(update_fields=['is_primary'])

        return Response(BankAccountSerializer(account).data, status=status.HTTP_200_OK)


class AdminUserListView(generics.ListAPIView):
    """GET /api/auth/admin/users/ 관리자용 전체 회원 목록 조회 API. 플랫폼 시스템 계정은 제외."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = User.objects.exclude(username=PLATFORM_USERNAME).order_by('-created_at')
