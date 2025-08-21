from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('change-password/', views.change_password_view, name='change_password'),
    path('two-factor/authenticate/', views.two_factor_authenticate_view, name='two-factor-authenticate'),
    path('signup/', views.signup_view, name='signup'),
]
