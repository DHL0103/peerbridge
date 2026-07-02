from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.serializers import PasswordChangeSerializer, ProfileSerializer, RegisterSerializer


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
