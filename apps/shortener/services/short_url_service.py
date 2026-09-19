"""短链接创建 / 查询的业务编排。"""
import re
import uuid
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import base62
from .cache_service import invalidate
from .url_validator import URLValidationError, normalize_and_validate_url

ALIAS_PATTERN = re.compile(r'^[A-Za-z0-9_-]{4,32}$')


class AliasError(ValueError):
    """自定义短码不合法或已被占用。"""


def validate_alias(alias: str) -> str:
    alias = (alias or '').strip()
    if not alias:
        return ''
    if not ALIAS_PATTERN.match(alias):
        raise AliasError('自定义短码需为 4-32 位字母、数字、中划线或下划线')
    if alias.lower() in base62.RESERVED_WORDS:
        raise AliasError('该短码为系统保留词，请更换')
    return alias


def _parse_expires_at(value):
    """把前端传入的过期时间（ISO 字符串 / datetime）转为 aware datetime。"""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        value = str(value).strip().replace('T', ' ')
        # 兼容 "YYYY-MM-DD HH:MM:SS" 与 "YYYY-MM-DD"
        fmt = '%Y-%m-%d %H:%M:%S' if len(value) > 10 else '%Y-%m-%d'
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError as exc:
            raise ValueError('过期时间格式不正确，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS') from exc
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    if dt < timezone.now():
        raise ValueError('过期时间不能早于当前时间')
    return dt


def create_short_url(*, original_url: str, creator=None, alias: str = '',
                     remarks: str = '', expires_at=None, allow_private: bool = False):
    """创建一条短链接，返回 ShortURL 实例。

    流程：URL 安全校验 -> 自定义短码校验 / 查重 -> 落库（自增 ID）-> Base62 发号回填。
    """
    from shortener.models import ShortURL

    url = normalize_and_validate_url(original_url, allow_private=allow_private)
    alias = validate_alias(alias)
    expires_at = _parse_expires_at(expires_at)

    if alias:
        exists = ShortURL.objects.filter(code=alias).exists() or \
            ShortURL.objects.filter(alias=alias).exists()
        if exists:
            raise AliasError('该自定义短码已被占用，请更换')

    # 事务内：先插入拿到自增主键，再用「主键 ID -> Base62」回填系统短码。
    # code 唯一，插入时使用下划线开头的临时占位（Base62 字母表不含下划线，绝不冲突）。
    with transaction.atomic():
        obj = ShortURL(
            original_url=url,
            code=f'_{uuid.uuid4().hex[:12]}',
            alias=alias or None,
            creator=creator,
            remarks=remarks.strip(),
            expires_at=expires_at,
        )
        obj.save()
        obj.code = base62.encode_id(obj.id)
        obj.save(update_fields=['code'])

    return obj


def update_short_url_status(obj, *, is_active: bool = None, expires_at=None):
    """更新启用状态 / 过期时间，并主动失效缓存。"""
    update_fields = []
    if is_active is not None:
        obj.is_active = bool(is_active)
        update_fields.append('is_active')
    if expires_at is not None:
        obj.expires_at = _parse_expires_at(expires_at) if expires_at else None
        update_fields.append('expires_at')
    if update_fields:
        obj.save(update_fields=update_fields)
        invalidate(obj.code, obj.alias or '')
    return obj


def delete_short_url(obj) -> None:
    """删除短链并失效缓存。"""
    code, alias = obj.code, obj.alias or ''
    obj.delete()
    invalidate(code, alias)
