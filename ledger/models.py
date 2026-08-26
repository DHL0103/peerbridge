from django.conf import settings
from django.db import models


class Ledger(models.Model):
    """사용자의 모든 자금 이동 기록. 이번 브랜치는 CHARGE/WITHDRAW만 실제로 생성된다."""

    class Type(models.TextChoices):
        CHARGE = 'CHARGE', '예치금 충전'
        WITHDRAW = 'WITHDRAW', '예치금 출금'
        INVEST = 'INVEST', '투자 실행'
        INVEST_REFUND = 'INVEST_REFUND', '투자 환불'
        DISTRIBUTION = 'DISTRIBUTION', '상환 분배금 수령'
        REPAY = 'REPAY', '차주 상환 납부'
        PLATFORM_FEE = 'PLATFORM_FEE', '플랫폼 수수료'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ledgers')
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    memo = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id} {self.type} {self.amount}'
