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
