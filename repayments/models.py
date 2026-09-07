from django.conf import settings
from django.db import models

from investments.models import Investment
from loans.models import Loan


class RepaymentSchedule(models.Model):
    """대출 회차별 상환 계획 (원금균등상환)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '미납'
        PAID = 'PAID', '납부완료'

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name='repayment_schedules')
    installment_number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    principal = models.DecimalField(max_digits=14, decimal_places=2)
    interest = models.DecimalField(max_digits=14, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['installment_number']
        constraints = [
            models.UniqueConstraint(fields=['loan', 'installment_number'], name='unique_loan_installment_number'),
        ]

    def __str__(self):
        return f'{self.loan_id} #{self.installment_number} {self.status}'


class Repayment(models.Model):
    """차주가 회차별로 실제 납부한 상환 내역."""

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name='repayments')
    schedule = models.OneToOneField(RepaymentSchedule, on_delete=models.PROTECT, related_name='repayment')
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='repayments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    idempotency_key = models.CharField(max_length=100)
    # 납부(이 레코드 생성)와 투자자 분배는 시점이 다르다 — 정산일(schedule.due_date) 전에 미리 냈다면
    # 분배는 정산일까지 보류되고, 그동안 이 값은 null이다. null이면 아직 미분배.
    distributed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['borrower', 'idempotency_key'], name='unique_borrower_idempotency_key'),
        ]

    def __str__(self):
        return f'{self.borrower_id} -> loan {self.loan_id} {self.amount}'


class Distribution(models.Model):
    """상환금을 투자 비율에 따라 투자자에게 분배한 내역."""

    repayment = models.ForeignKey(Repayment, on_delete=models.PROTECT, related_name='distributions')
    investment = models.ForeignKey(Investment, on_delete=models.PROTECT, related_name='distributions')
    investor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='distributions')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.investor_id} <- repayment {self.repayment_id} {self.amount}'
