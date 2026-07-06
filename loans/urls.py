from django.urls import path

from loans.views import (
    LoanApplicationApproveView,
    LoanApplicationListCreateView,
    LoanApplicationRejectView,
    LoanDetailView,
    LoanListView,
)

urlpatterns = [
    path('applications/', LoanApplicationListCreateView.as_view(), name='loan-application-list-create'),
    path('applications/<int:pk>/approve/', LoanApplicationApproveView.as_view(), name='loan-application-approve'),
    path('applications/<int:pk>/reject/', LoanApplicationRejectView.as_view(), name='loan-application-reject'),
    path('', LoanListView.as_view(), name='loan-list'),
    path('<int:pk>/', LoanDetailView.as_view(), name='loan-detail'),
]
