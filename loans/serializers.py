from decimal import Decimal

from rest_framework import serializers

from loans.models import Loan, LoanApplication

MAX_LEGAL_INTEREST_RATE = Decimal('20.00')


class LoanApplicationSerializer(serializers.ModelSerializer):
    """대출 신청 생성/조회 시리얼라이저. 금리는 심사(승인) 단계에서 관리자가 책정하므로 여기서는 받지 않는다."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = LoanApplication
        fields = ['id', 'amount', 'purpose', 'term_months', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return LoanApplication.objects.create(user=user, **validated_data)


class LoanApplicationApproveSerializer(serializers.Serializer):
    """승인 요청 입력 검증: 관리자가 interest_rate/investor_rate를 함께 책정한다. investor_rate는 interest_rate보다 낮아야 한다(스프레드가 플랫폼 수수료)."""

    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'), max_value=MAX_LEGAL_INTEREST_RATE)
    investor_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'))
    funding_deadline = serializers.DateField()

    def validate(self, attrs):
        if attrs['investor_rate'] >= attrs['interest_rate']:
            raise serializers.ValidationError({'investor_rate': '투자자 수익률은 차주 이율보다 낮아야 합니다.'})
        return attrs


class LoanSerializer(serializers.ModelSerializer):
    purpose = serializers.CharField(source='application.purpose', read_only=True)

    class Meta:
        model = Loan
        fields = [
            'id', 'purpose', 'interest_rate', 'investor_rate', 'target_amount', 'funded_amount',
            'term_months', 'funding_deadline', 'status', 'created_at',
        ]
