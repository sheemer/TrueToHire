from django.urls import path
from .views import submit_improvement

urlpatterns = [
    path('submit-improvement/', submit_improvement, name='submit_improvement'),
]