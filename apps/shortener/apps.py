from django.apps import AppConfig


class ShortenerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shortener'
    verbose_name = '短链接管理'

    def ready(self):
        # 注册信号（创建用户时自动签发 API Key 等）
        from . import signals  # noqa: F401
