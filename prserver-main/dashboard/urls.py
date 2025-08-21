from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('new-request/', views.new_request_view, name='new_request'),
    path('dashboard/delete/<uuid:public_id>/', views.delete_test_request, name='delete_test_request'),
    path("rooms/", views.rooms_view, name="rooms"),
    path("rooms/create/", views.create_room_view, name="create_room"),
    path("rooms/<int:room_id>/", views.room_detail_view, name="room_detail"),
    path('rooms/<int:room_id>/create-test/', views.create_test_request, name='create_test_request'),
    path("rooms/delete/<int:room_id>/", views.delete_room, name="delete_room"),
    path('dashboard/email/', views.send_test_link, name='send_test_link'),
    path("get-subtests/", views.get_subtests, name="get_subtests"),
    path('api/sub-tests/', views.sub_tests_api, name='sub_tests_api'),
    path("get_sub_tests/", views.get_sub_tests, name="get_sub_tests"),

]
