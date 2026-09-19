"""Django Admin 后台配置。"""
from django.contrib import admin

from .models import APIKey, AccessLog, ShortURL


@admin.register(ShortURL)
class ShortURLAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_code', 'original_url', 'creator', 'is_active',
                    'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('code', 'alias', 'original_url', 'remarks')
    list_display_links = ('short_code',)
    list_per_page = 30


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_url', 'ip', 'device_type', 'browser',
                    'os_name', 'accessed_at')
    list_filter = ('device_type', 'browser', 'accessed_at')
    search_fields = ('ip', 'short_url__code', 'short_url__alias')
    list_per_page = 50
    readonly_fields = ('short_url', 'ip', 'user_agent', 'device_type',
                       'browser', 'os_name', 'referer', 'accessed_at')

    def has_add_permission(self, request):
        return False


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'key')
    readonly_fields = ('key', 'created_at')
