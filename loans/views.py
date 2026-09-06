from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import PLATFORM_USERNAME, User
from loans.models import Loan, LoanApplication
from loans.serializers import LoanApplicationApproveSerializer, LoanApplicationSerializer, LoanSerializer


class LoanApplicationListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/loans/applications/ 내 대출 신청 목록 조회/등록 API."""

    serializer_class = LoanApplicationSerializer

    def get_queryset(self):
        return LoanApplication.objects.filter(user=self.request.user)


class LoanApplicationPendingListView(generics.ListAPIView):
    """GET /api/loans/applications/pending/ 관리자용 심사 대기 목록 API."""

    permission_classes = [IsAdminUser]
    serializer_class = LoanApplicationSerializer
    queryset = LoanApplication.objects.filter(status=LoanApplication.Status.PENDING)


class LoanApplicationApproveView(APIView):
    """POST /api/loans/applications/{id}/approve/ 관리자 승인 API. interest_rate/investor_rate를 함께 책정하고 Loan을 원자적으로 생성한다."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        with transaction.atomic():
            application = get_object_or_404(LoanApplication.objects.select_for_update(), pk=pk)
            if application.status != LoanApplication.Status.PENDING:
                return Response({'status': ['이미 처리된 신청서입니다.']}, status=status.HTTP_400_BAD_REQUEST)

            serializer = LoanApplicationApproveSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            application.status = LoanApplication.Status.APPROVED
            application.save(update_fields=['status'])
            loan = Loan.objects.create(
                application=application,
                interest_rate=serializer.validated_data['interest_rate'],
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
    """GET /api/loans/ 대출 상품 목록 조회 API. ?status=FUNDRAISING 등으로 필터링 가능. 메인페이지 노출용이라 비로그인도 허용."""

    permission_classes = [AllowAny]
    serializer_class = LoanSerializer

    def get_queryset(self):
        queryset = Loan.objects.all()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class LoanDetailView(generics.RetrieveAPIView):
    """GET /api/loans/{id}/ 대출 상품 상세 조회 API. 목록과 동일하게 비로그인도 허용."""

    permission_classes = [AllowAny]
    queryset = Loan.objects.all()
    serializer_class = LoanSerializer


class AdminStatsView(APIView):
    """GET /api/loans/admin/stats/ 관리자용 플랫폼 통계 요약."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        loans_by_status = {
            choice: Loan.objects.filter(status=choice).count() for choice, _ in Loan.Status.choices
        }
        overdue_count = sum(
            loans_by_status[s] for s in (Loan.Status.OVERDUE_1, Loan.Status.OVERDUE_2, Loan.Status.DEFAULT)
        )
        platform = User.objects.filter(username=PLATFORM_USERNAME).first()

        return Response({
            'total_users': User.objects.exclude(username=PLATFORM_USERNAME).count(),
            'pending_applications': LoanApplication.objects.filter(status=LoanApplication.Status.PENDING).count(),
            'loans_by_status': loans_by_status,
            'overdue_count': overdue_count,
            'platform_balance': platform.balance if platform else Decimal('0'),
        })
