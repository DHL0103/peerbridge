from django.contrib import admin

from .models import Loan, LoanApplication

admin.site.register(LoanApplication)
admin.site.register(Loan)
