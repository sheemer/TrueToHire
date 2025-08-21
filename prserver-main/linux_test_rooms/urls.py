from django.urls import path
from . import views

urlpatterns = [
    path('test-room/<uuid:public_id>/', views.test_room_view, name='test_room'),
    path('stop-instance/<uuid:public_id>/', views.stop_instance, name='stop_instance'),
    path('thank-you/', views.thank_you_view, name='thank_you'),

]
