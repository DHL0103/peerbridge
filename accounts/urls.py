from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView

from accounts.views import (
    AdminUserListView,
    BankAccountListCreateView,
    BankAccountSetPrimaryView,
    PasswordChangeView,
    ProfileView,
    RegisterView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('logout/', TokenBlacklistView.as_view(), name='logout'),
    path('me/', ProfileView.as_view(), name='profile'),
    path('password/', PasswordChangeView.as_view(), name='password-change'),
    path('bank-accounts/', BankAccountListCreateView.as_view(), name='bank-account-list-create'),
    path('bank-accounts/<int:pk>/set-primary/', BankAccountSetPrimaryView.as_view(), name='bank-account-set-primary'),
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
]
