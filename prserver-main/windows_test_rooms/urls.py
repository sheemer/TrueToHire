from django.urls import path
from . import views


urlpatterns = [
    path('windows_test_room/<uuid:public_id>/', views.windows_test_room_view, name='windows_test_room'),
    path('windows_stop_instance/<uuid:public_id>/', views.windows_stop_instance, name='windows_stop_instance'),
    path('thank-you/', views.thank_you_view, name='thank_you'),
    path("guacamole-tunnel/", views.guacamole_tunnel, name="guacamole_tunnel"),
]
