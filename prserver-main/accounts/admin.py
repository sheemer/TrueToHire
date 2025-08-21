from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Company

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'company', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'company')
    search_fields = ('username', 'email')
    ordering = ('username',)

    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('company',)}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Fields', {'fields': ('company',)}),
    )

admin.site.register(Company)