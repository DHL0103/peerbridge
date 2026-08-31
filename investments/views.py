from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from investments import services
from investments.models import Investment
from investments.serializers import (
    InvestmentCreateSerializer, InvestmentSerializer, MonthlyReturnSerializer, MyInvestmentSerializer,
)
from repayments.models import Distribution, RepaymentSchedule


class InvestmentCreateView(APIView):
    """POST /api/investments/ 투자 실행 API."""

    def post(self, request):
        serializer = InvestmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            investment, _created = services.create_investment(
                loan_id=data['loan_id'],
                investor=request.user,
                amount=data['amount'],
                idempotency_key=data['idempotency_key'],
            )
        except services.LoanNotFundraisingError:
            return Response({'loan': ['모집 중인 대출 상품이 아닙니다.']}, status=status.HTTP_400_BAD_REQUEST)
        except services.FundingExceededError:
            return Response({'amount': ['목표 모집 금액을 초과할 수 없습니다.']}, status=status.HTTP_400_BAD_REQUEST)
        except services.InsufficientBalanceError:
            return Response({'amount': ['잔액이 부족합니다.']}, status=status.HTTP_400_BAD_REQUEST)

        return Response(InvestmentSerializer(investment).data, status=status.HTTP_201_CREATED)


class MyInvestmentListView(APIView):
    """GET /api/investments/mine/ 로그인한 투자자의 투자 목록 조회 (누적 수익/진행률/다음 회차 예상 분배금 포함)."""

    def get(self, request):
        investments = Investment.objects.filter(investor=request.user).select_related(
            'loan', 'loan__application',
        ).order_by('-created_at')
        loan_ids = {inv.loan_id for inv in investments}

        earned_by_investment = {
            row['investment_id']: row['total']
            for row in Distribution.objects.filter(investment__in=investments)
                .values('investment_id').annotate(total=Sum('amount'))
        }
        paid_counts = {
            row['loan_id']: row['paid']
            for row in RepaymentSchedule.objects.filter(loan_id__in=loan_ids, status=RepaymentSchedule.Status.PAID)
                .values('loan_id').annotate(paid=Count('id'))
        }
        next_schedules = {}
        for schedule in RepaymentSchedule.objects.filter(
            loan_id__in=loan_ids, status=RepaymentSchedule.Status.PENDING,
        ).order_by('loan_id', 'due_date'):
            next_schedules.setdefault(schedule.loan_id, schedule)

        data = []
        for inv in investments:
            loan = inv.loan
            earned = earned_by_investment.get(inv.id)
            earned = earned.quantize(Decimal('1'), rounding=ROUND_HALF_UP) if earned else Decimal('0')
            progress = round(paid_counts.get(loan.id, 0) / loan.term_months, 4) if loan.term_months else 0

            schedule = next_schedules.get(loan.id)
            next_due_date = None
            estimated_next_amount = None
            if schedule is not None and loan.funded_amount > 0:
                investor_interest = (schedule.interest * loan.investor_rate / loan.interest_rate).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP,
                )
                pool = schedule.principal + investor_interest
                share = inv.amount / loan.funded_amount
                estimated_next_amount = (pool * share).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                next_due_date = schedule.due_date

            data.append({
                'id': inv.id, 'loan_id': loan.id, 'purpose': loan.application.purpose,
                'interest_rate': loan.interest_rate, 'investor_rate': loan.investor_rate,
                'term_months': loan.term_months, 'loan_status': loan.status,
                'amount': inv.amount, 'earned': earned, 'progress': progress,
                'next_due_date': next_due_date, 'estimated_next_amount': estimated_next_amount,
                'created_at': inv.created_at,
            })

        return Response({'results': MyInvestmentSerializer(data, many=True).data})


class MonthlyReturnsView(APIView):
    """GET /api/investments/monthly-returns/ 최근 12개월 수익(분배금) 추이. 분배 없는 달은 0으로 채운다."""

    def get(self, request):
        today = timezone.now().date()
        year, month = today.year, today.month
        month_keys = []
        for _ in range(12):
            month_keys.append(f'{year:04d}-{month:02d}')
            month -= 1
            if month == 0:
                month, year = 12, year - 1
        month_keys.reverse()

        earliest_year, earliest_month = (int(part) for part in month_keys[0].split('-'))
        range_start = timezone.make_aware(datetime(earliest_year, earliest_month, 1))

        totals = {
            row['month'].strftime('%Y-%m'): row['total']
            for row in Distribution.objects.filter(investor=request.user, created_at__gte=range_start)
                .annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('amount'))
        }

        results = [{'month': key, 'total': totals.get(key, Decimal('0'))} for key in month_keys]
        return Response({'results': MonthlyReturnSerializer(results, many=True).data})
