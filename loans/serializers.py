from decimal import Decimal

from rest_framework import serializers

from loans.models import Loan, LoanApplication

MAX_LEGAL_INTEREST_RATE = Decimal('20.00')


class LoanApplicationSerializer(serializers.ModelSerializer):
    """대출 신청 생성/조회 시리얼라이저. interest_rate는 법정 최고금리(20%) 이내여야 한다."""

    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'), max_value=MAX_LEGAL_INTEREST_RATE)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = LoanApplication
        fields = ['id', 'amount', 'purpose', 'term_months', 'interest_rate', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return LoanApplication.objects.create(user=user, **validated_data)


class LoanApplicationApproveSerializer(serializers.Serializer):
    """승인 요청 입력 검증: investor_rate는 신청서의 interest_rate보다 낮아야 한다(스프레드가 플랫폼 수수료)."""

    investor_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'))
    funding_deadline = serializers.DateField()

    def validate(self, attrs):
        application = self.context['application']
        if attrs['investor_rate'] >= application.interest_rate:
            raise serializers.ValidationError({'investor_rate': '투자자 수익률은 차주 이율보다 낮아야 합니다.'})
        return attrs


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            'id', 'interest_rate', 'investor_rate', 'target_amount', 'funded_amount',
            'term_months', 'funding_deadline', 'status', 'created_at',
        ]
