"""
Django 项目配置。

设计原则（12-Factor）：
- 所有环境相关配置（密钥、数据库、Redis、域名等）一律从环境变量 / .env 读取；
- 不写死任何密码或主机；
- 本地零依赖可用 SQLite + 本地内存缓存直接 runserver；
- Docker / 生产环境通过环境变量切换到 MySQL + Redis。
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录：config/settings.py 的上两级
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env（若存在）
load_dotenv(BASE_DIR / '.env')


def env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(key: str, default=None):
    value = os.getenv(key)
    if not value:
        return default if default is not None else []
    return [item.strip() for item in value.split(',') if item.strip()]


# 把 apps/ 目录加入模块搜索路径，使应用可直接以 'shortener' 引用
APPS_DIR = BASE_DIR / 'apps'
sys.path.insert(0, str(APPS_DIR))

# ============================ 安全相关 ============================
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'dev-insecure-secret-key-please-change-me',
)
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', ['*'])

# 反向代理（Nginx）场景：识别转发协议，便于未来启用 HTTPS 时正确判断安全请求
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# 允许发起 POST / 表单提交的可信来源（格式 scheme://host[:port]，逗号分隔）。
# 经 Nginx 反代到非标准端口（如本机 8088）时，浏览器 Origin 带端口，必须显式信任，
# 否则 Django 的 CSRF Origin 校验会返回 403。
CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    [
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://localhost:8088',
        'http://127.0.0.1:8088',
        'http://localhost:8090',
        'http://127.0.0.1:8090',
    ],
)

# ============================ 应用注册 ============================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 本项目应用
    'shortener',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise：在没有 Nginx 的托管环境（如 Render）由 Django 直接返回静态文件
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ============================ 数据库 ============================
# 配置了 DB_ENGINE=mysql 且 DB_HOST 存在时使用 MySQL（PyMySQL 驱动），
# 否则回退到 SQLite，便于本地零依赖快速启动。
if os.getenv('DB_ENGINE', '').lower() == 'mysql':
    import pymysql
    pymysql.install_as_MySQLdb()

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'shorturl'),
            'USER': os.getenv('DB_USER', 'shorturl'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            # 连接失败时由 docker entrypoint 等待数据库就绪；设置连接超时
            'OPTIONS': {
                'charset': 'utf8mb4',
                'connect_timeout': 10,
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ============================ 缓存（Redis）============================
REDIS_URL = os.getenv('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                # 连接失败不抛异常导致整站不可用（降级直查数据库）
                'IGNORE_EXCEPTIONS': True,
                'SOCKET_CONNECT_TIMEOUT': 3,
                'SOCKET_TIMEOUT': 3,
            },
            'KEY_PREFIX': 'shorturl',
        }
    }
else:
    # 本地无 Redis 时使用进程内内存缓存
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'shorturl-local',
        }
    }

# ============================ 认证 ============================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# ============================ 国际化 ============================
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# ============================ 静态文件 ============================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# WhiteNoise：在没有 Nginx 的托管环境（Render 等 PaaS）由应用服务器直接托管并压缩静态文件
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================ 项目自定义配置 ============================
SITE_BASE_URL = os.getenv('SITE_BASE_URL', 'http://localhost:8000').rstrip('/')
SHORT_CODE_MIN_LENGTH = int(os.getenv('SHORT_CODE_MIN_LENGTH', '6'))
ALLOW_ANONYMOUS_CREATE = env_bool('ALLOW_ANONYMOUS_CREATE', True)
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
RATE_LIMIT_MAX = int(os.getenv('RATE_LIMIT_MAX', '30'))
