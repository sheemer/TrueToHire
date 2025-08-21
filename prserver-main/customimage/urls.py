from django.urls import path
from . import views

#app_name = "customimage"

urlpatterns = [
    path('', views.custom_image_home, name='custom_image_home'),
    path("stop/<uuid:public_id>/", views.stop_instances, name="stop_instances"),
    path("test-room/<uuid:public_id>/", views.view_test_room, name="view_test_room"),
    path("create/", views.create_and_launch_test, name="create_test"),
    path("thank-you/", views.thank_you_view, name="thank_you_view"),  # Optional

]
