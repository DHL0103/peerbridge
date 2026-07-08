from django.urls import path

from repayments.views import RepaymentCreateView

urlpatterns = [
    path('<int:pk>/repay/', RepaymentCreateView.as_view(), name='loan-repay'),
]
