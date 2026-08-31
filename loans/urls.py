from django.urls import path

from loans.views import (
    AdminRunExpireLoansView,
    AdminRunMarkOverdueView,
    AdminStatsView,
    LoanApplicationApproveView,
    LoanApplicationListCreateView,
    LoanApplicationPendingListView,
    LoanApplicationRejectView,
    LoanDetailView,
    LoanListView,
)

urlpatterns = [
    path('applications/pending/', LoanApplicationPendingListView.as_view(), name='loan-application-pending-list'),
    path('applications/', LoanApplicationListCreateView.as_view(), name='loan-application-list-create'),
    path('applications/<int:pk>/approve/', LoanApplicationApproveView.as_view(), name='loan-application-approve'),
    path('applications/<int:pk>/reject/', LoanApplicationRejectView.as_view(), name='loan-application-reject'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('admin/run-expire-loans/', AdminRunExpireLoansView.as_view(), name='admin-run-expire-loans'),
    path('admin/run-mark-overdue/', AdminRunMarkOverdueView.as_view(), name='admin-run-mark-overdue'),
    path('', LoanListView.as_view(), name='loan-list'),
    path('<int:pk>/', LoanDetailView.as_view(), name='loan-detail'),
]
