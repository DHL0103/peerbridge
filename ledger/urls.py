from django.urls import path

from ledger.views import ChargeView, LedgerListView, WithdrawView

urlpatterns = [
    path('', LedgerListView.as_view(), name='ledger-history'),
    path('charge/', ChargeView.as_view(), name='ledger-charge'),
    path('withdraw/', WithdrawView.as_view(), name='ledger-withdraw'),
]
