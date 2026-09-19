"""WSGI 配置，供 gunicorn / uWSGI 使用。"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
