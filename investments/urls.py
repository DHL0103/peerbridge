from django.urls import path

from investments.views import InvestmentCreateView

urlpatterns = [
    path('', InvestmentCreateView.as_view(), name='investment-create'),
]
