from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.views import PasswordChangeView, ProfileView, RegisterView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('me/', ProfileView.as_view(), name='profile'),
    path('password/', PasswordChangeView.as_view(), name='password-change'),
]
