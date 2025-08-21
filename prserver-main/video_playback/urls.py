from django.urls import path
from . import views


app_name = 'video_playback'

urlpatterns = [
    path('play/<uuid:public_id>/', views.play_video, name='play_video'),
]