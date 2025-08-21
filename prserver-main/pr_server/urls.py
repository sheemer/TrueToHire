"""
URL configuration for pr_server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.conf.urls import handler404, handler500

urlpatterns = [
    path('admin/', admin.site.urls),
    path("home/", include("home.urls")),
    path('accounts/', include('accounts.urls')),
    path("accounts/", include("django.contrib.auth.urls")),
    path('dashboard/', include('dashboard.urls')),
    path('windows_test_rooms/', include('windows_test_rooms.urls')),
    path('video_playback/', include('video_playback.urls')),
    path('linux_test_rooms/', include('linux_test_rooms.urls')),
    path('contactus/', include('contactus.urls')),
    path('accounts/', include('allauth.urls')),
    path('accounts/two-factor/', include('allauth_2fa.urls')), 
    path('customimage/', include('customimage.urls')),
]


handler404 = "django.views.defaults.page_not_found"
handler500 = "django.views.defaults.server_error"
