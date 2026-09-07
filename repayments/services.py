import calendar
from datetime import date
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import PLATFORM_USERNAME, User
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

    # 원화는 소숫점 단위가 없다 — 원 단위(Decimal('1'))로 반올림한다.
    principal_per = (loan.target_amount / loan.term_months).quantize(Decimal('1'), rounding=ROUND_DOWN)
    outstanding = loan.target_amount
    today = date.today()
    schedules = []
    for installment_number in range(1, loan.term_months + 1):
        if installment_number == loan.term_months:
            principal = loan.target_amount - principal_per * (loan.term_months - 1)
        else:
            principal = principal_per
        interest = (outstanding * loan.interest_rate / Decimal('100') / Decimal('12')).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP,
        )
        schedules.append(RepaymentSchedule(
            loan=loan, installment_number=installment_number, due_date=_add_months(today, installment_number),
            principal=principal, interest=interest, total_amount=principal + interest,
        ))
        outstanding -= principal

    RepaymentSchedule.objects.bulk_create(schedules)


def _distribute(*, repayment, schedule, loan):
    """상환 회차의 원금+투자자 몫 이자를 투자 비율대로 분배한다.

    투자자에게는 소숫점 없는 원 단위로 올림(ROUND_CEILING)해서 지급한다 — 투자자가 잔돈을 받는 일이 없도록.
    올림으로 더 나간 금액과 이자 스프레드(interest_rate-investor_rate 차액)는 플랫폼 계좌에서 상계된다
    (플랫폼 수수료가 그만큼 줄어듦).
    """
    total_investor_interest = (schedule.interest * loan.investor_rate / loan.interest_rate).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    investors_pool = schedule.principal + total_investor_interest

    investments = list(Investment.objects.filter(loan=loan).select_for_update().order_by('id'))
    distributed_total = Decimal('0')
    for investment in investments:
        share = investment.amount / loan.funded_amount
        distribution_amount = (investors_pool * share).quantize(Decimal('1'), rounding=ROUND_CEILING)
        distributed_total += distribution_amount

        investor = User.objects.select_for_update().get(pk=investment.investor_id)
        investor.balance += distribution_amount
        investor.save(update_fields=['balance'])
        Distribution.objects.create(
            repayment=repayment, investment=investment, investor=investor, amount=distribution_amount,
        )
        Ledger.objects.create(
            user=investor, type=Ledger.Type.DISTRIBUTION, amount=distribution_amount, balance_after=investor.balance,
        )

    platform_fee = schedule.total_amount - distributed_total
    platform = User.objects.select_for_update().get(username=PLATFORM_USERNAME)
    platform.balance += platform_fee
    platform.save(update_fields=['balance'])
    Ledger.objects.create(
        user=platform, type=Ledger.Type.PLATFORM_FEE, amount=platform_fee, balance_after=platform.balance,
    )


def _late_fee(schedule, loan):
    """연체가산이자 = 회차 미납액 x 연체가산 반영 이자율(loan.effective_interest_rate) x 연체일수/365.

    연체가산이자는 투자자 분배와 무관하게 전액 플랫폼 몫으로 귀속된다(투자자 약정수익률은 불변).
    """
    if schedule.due_date >= date.today():
        return Decimal('0')
    overdue_days = (date.today() - schedule.due_date).days
    return (
        schedule.total_amount * loan.effective_interest_rate / Decimal('100') / Decimal('365') * overdue_days
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


REPAYABLE_STATUSES = (Loan.Status.ACTIVE, Loan.Status.OVERDUE_1, Loan.Status.OVERDUE_2, Loan.Status.DEFAULT)


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
            if loan.status not in REPAYABLE_STATUSES:
                raise LoanNotActiveError

            schedule = RepaymentSchedule.objects.select_for_update().filter(
                loan=loan, status=RepaymentSchedule.Status.PENDING,
            ).order_by('installment_number').first()
            if schedule is None:
                raise NoPendingInstallmentError

            late_fee = _late_fee(schedule, loan)
            total_due = schedule.total_amount + late_fee

            locked_borrower = User.objects.select_for_update().get(pk=borrower.pk)
            if locked_borrower.balance < total_due:
                raise InsufficientBalanceError

            locked_borrower.balance -= total_due
            locked_borrower.save(update_fields=['balance'])

            repayment = Repayment.objects.create(
                loan=loan, schedule=schedule, borrower=locked_borrower, amount=total_due,
                idempotency_key=idempotency_key,
            )

            schedule.status = RepaymentSchedule.Status.PAID
            schedule.paid_at = timezone.now()
            schedule.save(update_fields=['status', 'paid_at'])

            Ledger.objects.create(
                user=locked_borrower, type=Ledger.Type.REPAY, amount=total_due,
                balance_after=locked_borrower.balance,
            )

            # 정산일(schedule.due_date)이 되기 전에 미리 낸 거라면 분배는 보류한다 — 투자자는
            # 원래 예정된 날짜에 받는 게 맞고, distribute_due_repayments() 배치가 그날 처리한다.
            if schedule.due_date <= date.today():
                _distribute(repayment=repayment, schedule=schedule, loan=loan)
                repayment.distributed_at = timezone.now()
                repayment.save(update_fields=['distributed_at'])

            if late_fee > 0:
                platform = User.objects.select_for_update().get(username=PLATFORM_USERNAME)
                platform.balance += late_fee
                platform.save(update_fields=['balance'])
                Ledger.objects.create(
                    user=platform, type=Ledger.Type.PLATFORM_FEE, amount=late_fee,
                    balance_after=platform.balance, memo='연체가산이자',
                )

            if not RepaymentSchedule.objects.filter(loan=loan, status=RepaymentSchedule.Status.PENDING).exists():
                loan.status = Loan.Status.COMPLETED
                loan.save(update_fields=['status'])

            return repayment, True
    except IntegrityError:
        return Repayment.objects.get(borrower=borrower, idempotency_key=idempotency_key), False


def distribute_due_repayments():
    """정산일 전에 미리 상환해서 분배가 보류된 건 중, 정산일(due_date)이 된 것을 분배한다.

    반환: 이번에 분배 처리된 Repayment 목록.
    """
    today = date.today()
    pending_ids = Repayment.objects.filter(
        distributed_at__isnull=True, schedule__due_date__lte=today,
    ).values_list('id', flat=True)

    settled = []
    for repayment_id in pending_ids:
        with transaction.atomic():
            repayment = Repayment.objects.select_for_update().select_related('schedule', 'loan').get(pk=repayment_id)
            if repayment.distributed_at is not None:
                continue

            _distribute(repayment=repayment, schedule=repayment.schedule, loan=repayment.loan)
            repayment.distributed_at = timezone.now()
            repayment.save(update_fields=['distributed_at'])
            settled.append(repayment)

    return settled
