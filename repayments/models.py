from django.db import models

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
