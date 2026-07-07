from django.conf import settings
from django.db import models

from loans.models import Loan


class Investment(models.Model):
    """투자자가 특정 대출 상품에 투자한 내역."""

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name='investments')
    investor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='investments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    idempotency_key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['investor', 'idempotency_key'], name='unique_investor_idempotency_key'),
        ]

    def __str__(self):
        return f'{self.investor_id} -> loan {self.loan_id} {self.amount}'
