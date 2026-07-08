import calendar
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from repayments.models import RepaymentSchedule


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
