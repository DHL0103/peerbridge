from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """차주(borrower)와 투자자(investor) 역할을 동시에 수행할 수 있는 플랫폼 사용자."""

    phone_number = models.CharField(max_length=20, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username


class BankAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=50)
    account_number = models.CharField(max_length=50)
    account_holder = models.CharField(max_length=50)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.bank_name} {self.account_number}'
