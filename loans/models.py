from django.conf import settings
from django.db import models


class LoanApplication(models.Model):
    """차주가 제출하는 대출 신청서(심사 전)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '심사중'
        APPROVED = 'APPROVED', '승인'
        REJECTED = 'REJECTED', '거절'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loan_applications')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    purpose = models.CharField(max_length=200)
    term_months = models.PositiveSmallIntegerField()
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id} {self.amount} {self.status}'


class Loan(models.Model):
    """승인된 대출 상품. 모집(FUNDRAISING)부터 완료/부실까지의 전체 라이프사이클을 관리한다."""

    class Status(models.TextChoices):
        FUNDRAISING = 'FUNDRAISING', '모집중'
        ACTIVE = 'ACTIVE', '실행중'
        OVERDUE_1 = 'OVERDUE_1', '연체1'
        OVERDUE_2 = 'OVERDUE_2', '연체2'
        DEFAULT = 'DEFAULT', '부실'
        WRITTEN_OFF = 'WRITTEN_OFF', '상각'
        COMPLETED = 'COMPLETED', '완료'

    application = models.OneToOneField(LoanApplication, on_delete=models.PROTECT, related_name='loan')
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    investor_rate = models.DecimalField(max_digits=5, decimal_places=2)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    funded_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    term_months = models.PositiveSmallIntegerField()
    funding_deadline = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.FUNDRAISING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.pk} {self.status}'

    @property
    def borrower(self):
        return self.application.user
