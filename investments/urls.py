from django.urls import path

from investments.views import InvestmentCreateView, MonthlyReturnsView, MyInvestmentListView

urlpatterns = [
    path('mine/', MyInvestmentListView.as_view(), name='investment-mine'),
    path('monthly-returns/', MonthlyReturnsView.as_view(), name='investment-monthly-returns'),
    path('', InvestmentCreateView.as_view(), name='investment-create'),
]
