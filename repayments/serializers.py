from rest_framework import serializers

from repayments.models import Repayment


class RepaymentCreateSerializer(serializers.Serializer):
    """상환 납부 입력 검증."""

    idempotency_key = serializers.CharField(max_length=100)


class RepaymentSerializer(serializers.ModelSerializer):
    installment_number = serializers.SerializerMethodField()

    class Meta:
        model = Repayment
        fields = ['id', 'loan', 'installment_number', 'amount', 'idempotency_key', 'created_at']

    def get_installment_number(self, obj):
        return obj.schedule.installment_number


class NextRepaymentSerializer(serializers.Serializer):
    """로그인한 차주의 다음 상환 예정 회차 조회 응답."""

    loan_id = serializers.IntegerField()
    purpose = serializers.CharField()
    installment_number = serializers.IntegerField()
    principal = serializers.DecimalField(max_digits=14, decimal_places=2)
    interest = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    due_date = serializers.DateField()
    remaining_installments = serializers.IntegerField()
