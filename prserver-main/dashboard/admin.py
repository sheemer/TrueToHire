from django.contrib import admin
from .models import TestType, SubTest, TestRequest


@admin.register(TestRequest)
class TestRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_accessed', 'test_type', 'accessed_by_name')
    list_filter = ('is_accessed', 'test_type')
    readonly_fields = ('is_accessed',)
    fields = ('title', 'password', 'test_type', 'is_accessed', 'accessed_by_name', 'accessed_by_email')

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:  # Hide fields for non-superusers
            return self.readonly_fields + ('test_type',)
        return self.readonly_fields



@admin.register(TestType)
class TestTypeAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        import logging
        logger = logging.getLogger(__name__)
        try:
            super().save_model(request, obj, form, change)
        except Exception as e:
            logger.error(f"Error saving TestType: {e}")
            raise

@admin.register(SubTest)
class SubTestAdmin(admin.ModelAdmin):
    list_display = ('name', 'test_type', 'os_type', 'ami_id', 'time_limit', 'script', 'pass_fail')
    search_fields = ('name', 'ami_id')
    list_filter = ('os_type', 'test_type')
    fields = ('name', 'test_type', 'ami_id', 'details', 'instructions', 'time_limit', 'os_type', 'script')

