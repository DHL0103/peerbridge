from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from repayments import services
from repayments.serializers import RepaymentCreateSerializer, RepaymentSerializer


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
