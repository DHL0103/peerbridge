from django.contrib import admin

from repayments.models import Distribution, Repayment, RepaymentSchedule

admin.site.register(RepaymentSchedule)
admin.site.register(Repayment)
admin.site.register(Distribution)
