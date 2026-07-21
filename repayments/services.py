import calendar
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User
from investments.models import Investment
from ledger.models import Ledger
from loans.models import Loan
from repayments.models import Distribution, Repayment, RepaymentSchedule


class NotBorrowerError(Exception):
    pass


class LoanNotActiveError(Exception):
    pass


class NoPendingInstallmentError(Exception):
    pass


class InsufficientBalanceError(Exception):
    pass


def _add_months(base_date, months):
    """dateutil 없이 표준 라이브러리만으로 월 단위를 더한다 (말일 보정 포함)."""
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_schedule(loan):
    """대출 실행 시 회차별 상환 스케줄을 원금균등상환 방식으로 생성한다 (호출 측 트랜잭션 안에서 실행, idempotent)."""
    if RepaymentSchedule.objects.filter(loan=loan).exists():
        return

    principal_per = (loan.target_amount / loan.term_months).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    outstanding = loan.target_amount
    today = date.today()
    schedules = []
    for installment_number in range(1, loan.term_months + 1):
        if installment_number == loan.term_months:
            principal = loan.target_amount - principal_per * (loan.term_months - 1)
        else:
            principal = principal_per
        interest = (outstanding * loan.interest_rate / Decimal('100') / Decimal('12')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        schedules.append(RepaymentSchedule(
            loan=loan, installment_number=installment_number, due_date=_add_months(today, installment_number),
            principal=principal, interest=interest, total_amount=principal + interest,
        ))
        outstanding -= principal

    RepaymentSchedule.objects.bulk_create(schedules)


def _distribute(*, repayment, schedule, loan):
    """상환 회차의 원금+투자자 몫 이자를 투자 비율대로 분배한다 (마지막 투자건이 반올림 잔여분 흡수)."""
    total_investor_interest = (schedule.interest * loan.investor_rate / loan.interest_rate).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    investments = list(Investment.objects.filter(loan=loan).select_for_update().order_by('id'))
    principal_running_total = Decimal('0')
    interest_running_total = Decimal('0')
    for index, investment in enumerate(investments):
        share = investment.amount / loan.funded_amount
        if index == len(investments) - 1:
            principal_share = schedule.principal - principal_running_total
            interest_share = total_investor_interest - interest_running_total
        else:
            principal_share = (schedule.principal * share).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            interest_share = (total_investor_interest * share).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            principal_running_total += principal_share
            interest_running_total += interest_share

        distribution_amount = principal_share + interest_share
        investor = User.objects.select_for_update().get(pk=investment.investor_id)
        investor.balance += distribution_amount
        investor.save(update_fields=['balance'])
        Distribution.objects.create(
            repayment=repayment, investment=investment, investor=investor, amount=distribution_amount,
        )
        Ledger.objects.create(
            user=investor, type=Ledger.Type.DISTRIBUTION, amount=distribution_amount, balance_after=investor.balance,
        )
    # ponytail: 스프레드(schedule.interest - total_investor_interest)는 플랫폼 소유 User가 아직 없어 PLATFORM_FEE
    # Ledger로 남기지 않는다. 플랫폼 계정 모델링 시 여기에 추가.


def repay(*, loan_id, borrower, idempotency_key):
    """반환: (repayment, created). created=False면 idempotency_key 재사용으로 기존 걸 반환한 것."""
    try:
        with transaction.atomic():
            existing = Repayment.objects.filter(borrower=borrower, idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

            loan = get_object_or_404(Loan.objects.select_for_update(), pk=loan_id)
            if loan.borrower != borrower:
                raise NotBorrowerError
            if loan.status != Loan.Status.ACTIVE:
                raise LoanNotActiveError

            schedule = RepaymentSchedule.objects.select_for_update().filter(
                loan=loan, status=RepaymentSchedule.Status.PENDING,
            ).order_by('installment_number').first()
            if schedule is None:
                raise NoPendingInstallmentError

            locked_borrower = User.objects.select_for_update().get(pk=borrower.pk)
            if locked_borrower.balance < schedule.total_amount:
                raise InsufficientBalanceError

            locked_borrower.balance -= schedule.total_amount
            locked_borrower.save(update_fields=['balance'])

            repayment = Repayment.objects.create(
                loan=loan, schedule=schedule, borrower=locked_borrower, amount=schedule.total_amount,
                idempotency_key=idempotency_key,
            )

            schedule.status = RepaymentSchedule.Status.PAID
            schedule.paid_at = timezone.now()
            schedule.save(update_fields=['status', 'paid_at'])

            Ledger.objects.create(
                user=locked_borrower, type=Ledger.Type.REPAY, amount=schedule.total_amount,
                balance_after=locked_borrower.balance,
            )

            _distribute(repayment=repayment, schedule=schedule, loan=loan)

            if not RepaymentSchedule.objects.filter(loan=loan, status=RepaymentSchedule.Status.PENDING).exists():
                loan.status = Loan.Status.COMPLETED
                loan.save(update_fields=['status'])

            return repayment, True
    except IntegrityError:
        return Repayment.objects.get(borrower=borrower, idempotency_key=idempotency_key), False
