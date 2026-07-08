from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from repayments import services
from repayments.models import RepaymentSchedule
from repayments.serializers import NextRepaymentSerializer, RepaymentCreateSerializer, RepaymentSerializer


class NextRepaymentView(APIView):
    """GET /api/loans/mine/next-repayment/ 로그인한 차주의 다음 상환 예정 회차 조회."""

    def get(self, request):
        schedule = RepaymentSchedule.objects.filter(
            loan__application__user=request.user, status=RepaymentSchedule.Status.PENDING,
        ).order_by('due_date', 'installment_number').first()
        if schedule is None:
            return Response({'detail': '상환 예정인 회차가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        remaining = RepaymentSchedule.objects.filter(
            loan=schedule.loan, status=RepaymentSchedule.Status.PENDING,
        ).count()
        data = {
            'loan_id': schedule.loan_id,
            'purpose': schedule.loan.application.purpose,
            'installment_number': schedule.installment_number,
            'principal': schedule.principal,
            'interest': schedule.interest,
            'total_amount': schedule.total_amount,
            'due_date': schedule.due_date,
            'remaining_installments': remaining,
        }
        return Response(NextRepaymentSerializer(data).data)


class RepaymentCreateView(APIView):
    """POST /api/loans/{id}/repay/ 상환 납부 API."""

    def post(self, request, pk):
        serializer = RepaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            repayment, _created = services.repay(
                loan_id=pk, borrower=request.user, idempotency_key=data['idempotency_key'],
            )
        except services.NotBorrowerError:
            return Response({'loan': ['본인의 대출 건이 아닙니다.']}, status=status.HTTP_400_BAD_REQUEST)
        except services.LoanNotActiveError:
            return Response({'loan': ['실행 중인 대출이 아닙니다.']}, status=status.HTTP_400_BAD_REQUEST)
        except services.NoPendingInstallmentError:
            return Response({'loan': ['남은 상환 회차가 없습니다.']}, status=status.HTTP_400_BAD_REQUEST)
        except services.InsufficientBalanceError:
            return Response({'balance': ['잔액이 부족합니다.']}, status=status.HTTP_400_BAD_REQUEST)

        return Response(RepaymentSerializer(repayment).data, status=status.HTTP_201_CREATED)
