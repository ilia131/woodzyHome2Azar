from django.urls import path
from .api import Login, Logout, Password, Profile, Refresh, Register
from .recovery import RecoveryConfirm, RecoveryEnroll, RecoveryEnrollConfirm, RecoveryRequest

urlpatterns = [
    path('password/recovery/', RecoveryRequest.as_view()),
    path('password/recovery/confirm/', RecoveryConfirm.as_view()),
    path('password/recovery/email/', RecoveryEnroll.as_view()),
    path('password/recovery/email/confirm/', RecoveryEnrollConfirm.as_view()),
    path('register/', Register.as_view()), path('login/', Login.as_view()),
    path('token/refresh/', Refresh.as_view()), path('logout/', Logout.as_view()),
    path('me/', Profile.as_view()), path('password/change/', Password.as_view()),
]
