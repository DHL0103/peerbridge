from rest_framework import generics
from rest_framework.permissions import AllowAny

from accounts.serializers import RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ 회원가입 API."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = RegisterSerializer
