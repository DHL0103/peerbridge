from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from loans.models import Loan, LoanApplication
from loans.serializers import LoanApplicationApproveSerializer, LoanApplicationSerializer, LoanSerializer


class LoanApplicationListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/loans/applications/ 내 대출 신청 목록 조회/등록 API."""

    serializer_class = LoanApplicationSerializer

    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user)


class LoanApplicationApproveView(APIView):
    """POST /api/loans/applications/{id}/approve/ 관리자 승인 API. 승인 시 Loan을 원자적으로 생성한다."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        with transaction.atomic():
            application = get_object_or_404(LoanApplication.objects.select_for_update(), pk=pk)
            if application.status != LoanApplication.Status.PENDING:
                return Response({'status': ['이미 처리된 신청서입니다.']}, status=status.HTTP_400_BAD_REQUEST)

            serializer = LoanApplicationApproveSerializer(data=request.data, context={'application': application})
            serializer.is_valid(raise_exception=True)

            application.status = LoanApplication.Status.APPROVED
            application.save(update_fields=['status'])
            loan = Loan.objects.create(
                application=application,
                interest_rate=application.interest_rate,
                investor_rate=serializer.validated_data['investor_rate'],
                target_amount=application.amount,
                term_months=application.term_months,
                funding_deadline=serializer.validated_data['funding_deadline'],
            )

        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class LoanApplicationRejectView(APIView):
    """POST /api/loans/applications/{id}/reject/ 관리자 거절 API."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        with transaction.atomic():
            application = get_object_or_404(LoanApplication.objects.select_for_update(), pk=pk)
            if application.status != LoanApplication.Status.PENDING:
                return Response({'status': ['이미 처리된 신청서입니다.']}, status=status.HTTP_400_BAD_REQUEST)

            application.status = LoanApplication.Status.REJECTED
            application.save(update_fields=['status'])

        return Response(LoanApplicationSerializer(application).data, status=status.HTTP_200_OK)


class LoanListView(generics.ListAPIView):
    """GET /api/loans/ 대출 상품 목록 조회 API."""

    queryset = Loan.objects.all()
    serializer_class = LoanSerializer


class LoanDetailView(generics.RetrieveAPIView):
    """GET /api/loans/{id}/ 대출 상품 상세 조회 API."""

    queryset = Loan.objects.all()
    serializer_class = LoanSerializer
