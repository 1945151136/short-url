"""模型信号：新建用户时自动为其签发 API Key。"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.crypto import get_random_string

from .models import APIKey


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_api_key(sender, instance, created, **kwargs):
    if created and not APIKey.objects.filter(user=instance).exists():
        APIKey.objects.create(
            user=instance,
            key='sk_' + get_random_string(40),
        )
