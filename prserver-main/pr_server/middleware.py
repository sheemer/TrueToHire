from django.http import HttpResponseForbidden
from django.conf import settings


class RestrictAdminMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/') and request.META['REMOTE_ADDR'] not in ALLOWED_ADMIN_IPS:
            return HttpResponseForbidden("Admin access restricted")
        return self.get_response(request)