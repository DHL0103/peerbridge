from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from ledger.models import Ledger
from ledger.serializers import AmountSerializer, LedgerSerializer


class LedgerListView(generics.ListAPIView):
    """GET /api/ledger/ 내 거래 내역 조회 API."""

    serializer_class = LedgerSerializer

    def get_queryset(self):
        return Ledger.objects.filter(user=self.request.user)


class ChargeView(APIView):
    """POST /api/ledger/charge/ 예치금 충전 API."""

    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            user.balance += amount
            user.save(update_fields=['balance'])
            ledger = Ledger.objects.create(
                user=user, type=Ledger.Type.CHARGE, amount=amount, balance_after=user.balance,
            )

        return Response(LedgerSerializer(ledger).data, status=status.HTTP_201_CREATED)


class WithdrawView(APIView):
    """POST /api/ledger/withdraw/ 예치금 출금 API."""

    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if amount > user.balance:
                return Response({'amount': ['잔액이 부족합니다.']}, status=status.HTTP_400_BAD_REQUEST)

            user.balance -= amount
            user.save(update_fields=['balance'])
            ledger = Ledger.objects.create(
                user=user, type=Ledger.Type.WITHDRAW, amount=amount, balance_after=user.balance,
            )

        return Response(LedgerSerializer(ledger).data, status=status.HTTP_201_CREATED)
