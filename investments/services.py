from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from accounts.models import User
from investments.models import Investment
from ledger.models import Ledger
from loans.models import Loan
from repayments import services as repayments_services


class LoanNotFundraisingError(Exception):
    pass


class FundingExceededError(Exception):
    pass


class InsufficientBalanceError(Exception):
    pass


def create_investment(*, loan_id, investor, amount, idempotency_key):
    """반환: (investment, created). created=False면 idempotency_key 재사용으로 기존 걸 반환한 것."""
    try:
        with transaction.atomic():
            existing = Investment.objects.filter(investor=investor, idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

            loan = get_object_or_404(Loan.objects.select_for_update(), pk=loan_id)
            if loan.status != Loan.Status.FUNDRAISING:
                raise LoanNotFundraisingError
            if loan.funded_amount + amount > loan.target_amount:
                raise FundingExceededError

            locked_investor = User.objects.select_for_update().get(pk=investor.pk)
            if amount > locked_investor.balance:
                raise InsufficientBalanceError

            locked_investor.balance -= amount
            locked_investor.save(update_fields=['balance'])

            investment = Investment.objects.create(
                loan=loan, investor=locked_investor, amount=amount, idempotency_key=idempotency_key,
            )

            loan.funded_amount += amount
            if loan.funded_amount >= loan.target_amount:
                loan.status = Loan.Status.ACTIVE
            loan.save(update_fields=['funded_amount', 'status'])
            if loan.status == Loan.Status.ACTIVE:
                repayments_services.generate_schedule(loan)

            Ledger.objects.create(
                user=locked_investor, type=Ledger.Type.INVEST, amount=amount, balance_after=locked_investor.balance,
            )
            return investment, True
    except IntegrityError:
        return Investment.objects.get(investor=investor, idempotency_key=idempotency_key), False
