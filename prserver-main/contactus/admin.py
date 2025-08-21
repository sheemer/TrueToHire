from django.contrib import admin
from .models import ImprovementRequest

@admin.register(ImprovementRequest)
class ImprovementRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'user', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('title', 'description')
