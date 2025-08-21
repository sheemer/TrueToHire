from django.contrib import admin
from .models import WindowsTestInstance

@admin.register(WindowsTestInstance)
class WindowsTestInstanceAdmin(admin.ModelAdmin):
    list_display = ("instance_id", "get_test_id", "start_time", "end_time", "status")
    search_fields = ("instance_id", "test_request__public_id")
    list_filter = ("status",)

    @admin.display(description="Test ID")
    def get_test_id(self, obj):
        return obj.test_request.public_id if obj.test_request else "-"