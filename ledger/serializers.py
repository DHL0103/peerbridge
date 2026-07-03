from decimal import Decimal

from rest_framework import serializers

from ledger.models import Ledger


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ledger
        fields = ['id', 'type', 'amount', 'balance_after', 'memo', 'created_at']


class AmountSerializer(serializers.Serializer):
    """충전/출금 공통 입력 검증: amount는 0보다 커야 한다."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
