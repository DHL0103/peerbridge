from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from investments import services
from investments.serializers import InvestmentCreateSerializer, InvestmentSerializer


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
