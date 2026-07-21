from django.urls import path

from repayments.views import NextRepaymentView, RepaymentCreateView

urlpatterns = [
    path('mine/next-repayment/', NextRepaymentView.as_view(), name='next-repayment'),
    path('<int:pk>/repay/', RepaymentCreateView.as_view(), name='loan-repay'),
]
