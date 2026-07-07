from decimal import Decimal

from rest_framework import serializers

from investments.models import Investment


class InvestmentCreateSerializer(serializers.Serializer):
    """투자 실행 입력 검증."""

    loan_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    idempotency_key = serializers.CharField(max_length=100)


class InvestmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investment
        fields = ['id', 'loan', 'amount', 'idempotency_key', 'created_at']
