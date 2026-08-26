from datetime import date

from django.db import transaction

from accounts.models import User
from investments.models import Investment
from ledger.models import Ledger
from loans.models import Loan
from repayments.models import RepaymentSchedule


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


def mark_overdue_loans():
    """상환일 지난 회차가 있는 대출을 연체 일수에 따라 OVERDUE_1/OVERDUE_2/DEFAULT로 승급한다.

    역방향 전환(연체 해제)은 하지 않는다 — 완납 시 별도 로직(repayments.services.repay)에서 COMPLETED로 바뀐다.
    WRITTEN_OFF(상각)는 관리자가 수동으로만 처리한다.
    반환: 상태가 바뀐 Loan 목록.
    """
    today = date.today()
    escalatable_ids = Loan.objects.filter(
        status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE_1, Loan.Status.OVERDUE_2],
    ).values_list('id', flat=True)

    updated = []
    for loan_id in escalatable_ids:
        with transaction.atomic():
            loan = Loan.objects.select_for_update().get(pk=loan_id)
            if loan.status not in (Loan.Status.ACTIVE, Loan.Status.OVERDUE_1, Loan.Status.OVERDUE_2):
                continue

            oldest_pending = RepaymentSchedule.objects.filter(
                loan=loan, status=RepaymentSchedule.Status.PENDING,
            ).order_by('due_date').first()
            if oldest_pending is None or oldest_pending.due_date >= today:
                continue

            overdue_days = (today - oldest_pending.due_date).days
            if overdue_days > 90:
                new_status = Loan.Status.DEFAULT
            elif overdue_days > 30:
                new_status = Loan.Status.OVERDUE_2
            else:
                new_status = Loan.Status.OVERDUE_1

            if new_status != loan.status:
                loan.status = new_status
                loan.save(update_fields=['status'])
                updated.append(loan)

    return updated
