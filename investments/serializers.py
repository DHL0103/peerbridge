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


class MyInvestmentSerializer(serializers.Serializer):
    """내 투자 목록 조회 응답 — Investment 모델 그대로가 아니라 대출/분배 정보를 조합한 값."""

    id = serializers.IntegerField()
    loan_id = serializers.IntegerField()
    purpose = serializers.CharField()
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    investor_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    term_months = serializers.IntegerField()
    loan_status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    earned = serializers.DecimalField(max_digits=14, decimal_places=0)
    progress = serializers.FloatField()
    next_due_date = serializers.DateField(allow_null=True)
    estimated_next_amount = serializers.DecimalField(max_digits=14, decimal_places=0, allow_null=True)
    created_at = serializers.DateTimeField()


class MonthlyReturnSerializer(serializers.Serializer):
    """월별 수익(분배금) 추이 응답 — 최근 12개월, 분배 없는 달은 0으로 채움."""

    month = serializers.CharField()
    total = serializers.DecimalField(max_digits=14, decimal_places=0)
