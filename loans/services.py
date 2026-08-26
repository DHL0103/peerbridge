from datetime import date

from django.db import transaction

from accounts.models import User
from investments.models import Investment
from ledger.models import Ledger
from loans.models import Loan


def expire_fundraising_loans():
    """마감일이 지났는데 목표 금액을 못 채운 FUNDRAISING 대출을 취소하고 투자자에게 전액 환불한다.

    반환: 취소된 Loan 목록.
    """
    expired_ids = Loan.objects.filter(
        status=Loan.Status.FUNDRAISING, funding_deadline__lt=date.today(),
    ).values_list('id', flat=True)

    cancelled = []
    for loan_id in expired_ids:
        with transaction.atomic():
            loan = Loan.objects.select_for_update().get(pk=loan_id)
            if loan.status != Loan.Status.FUNDRAISING:
                continue

            investments = Investment.objects.filter(loan=loan).select_for_update()
            for investment in investments:
                investor = User.objects.select_for_update().get(pk=investment.investor_id)
                investor.balance += investment.amount
                investor.save(update_fields=['balance'])
                Ledger.objects.create(
                    user=investor, type=Ledger.Type.INVEST_REFUND, amount=investment.amount,
                    balance_after=investor.balance,
                )

            loan.status = Loan.Status.CANCELLED
            loan.save(update_fields=['status'])
            cancelled.append(loan)

    return cancelled
