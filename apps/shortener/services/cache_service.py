"""
短链查询的缓存服务（Cache-Aside Pattern）。

跳转是最高频的读操作，通过 Redis 缓存「短码 -> 跳转信息」降低 MySQL 压力：

1. **旁路缓存**：先读缓存，未命中再读数据库并回填；
2. **缓存穿透防护**：数据库中不存在的短码写入「空值标记」并设置较短 TTL，
   避免恶意请求大量不存在的短码把压力打到数据库；
3. **缓存雪崩防护**：正常缓存 TTL 叠加随机抖动，避免大量 key 同时过期；
4. **主动失效**：短链被禁用 / 删除 / 更新时，调用 ``invalidate`` 立即删除缓存。

缓存值只保存跳转必需的轻量字段（dict），不直接缓存 ORM 对象，序列化更轻、解耦更好。
"""
import random
from dataclasses import dataclass

from django.core.cache import cache

# 正常短链缓存 24 小时，叠加 0~30 分钟随机抖动防雪崩
_DETAIL_TTL = 24 * 3600
_DETAIL_JITTER = 1800
# 不存在短码的空值缓存 60 秒，叠加 0~30 秒抖动
_NULL_TTL = 60
_NULL_JITTER = 30

_NULL_PLACEHOLDER = '__NOT_FOUND__'


@dataclass
class ResolvedShortLink:
    """跳转解析结果（缓存载体）。"""
    id: int
    code: str
    original_url: str
    is_active: bool
    expires_at: str  # ISO8601 字符串或空串

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'code': self.code,
            'original_url': self.original_url,
            'is_active': self.is_active,
            'expires_at': self.expires_at or '',
            '_marker': 'resolved',
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ResolvedShortLink':
        return cls(
            id=data['id'],
            code=data['code'],
            original_url=data['original_url'],
            is_active=data['is_active'],
            expires_at=data.get('expires_at', ''),
        )


def _detail_key(code: str) -> str:
    return f'short:detail:{code}'


def _null_key(code: str) -> str:
    return f'short:null:{code}'


def get_cached_short_link(code: str):
    """按系统短码或自定义别名解析短链，带缓存。

    返回 :class:`ResolvedShortLink`；不存在返回 ``None``（结果同样被短 TTL 缓存）。
    """
    from shortener.models import ShortURL

    code = code.strip()
    detail_key = _detail_key(code)
    null_key = _null_key(code)

    # 1) 命中「不存在」空值标记 -> 直接返回，不查库
    if cache.get(null_key):
        return None

    # 2) 命中正常缓存
    cached = cache.get(detail_key)
    if cached:
        if cached == _NULL_PLACEHOLDER:
            return None
        return ResolvedShortLink.from_dict(cached)

    # 3) 未命中 -> 查询数据库（系统短码或自定义别名）
    obj = (
        ShortURL.objects
        .filter(code=code)
        .first()
    )
    if obj is None:
        obj = ShortURL.objects.filter(alias=code).first()

    if obj is None:
        # 空值缓存，防穿透
        cache.set(null_key, 1, _NULL_TTL + random.randint(0, _NULL_JITTER))
        return None

    resolved = ResolvedShortLink(
        id=obj.id,
        code=obj.short_code,
        original_url=obj.original_url,
        is_active=obj.is_active,
        expires_at=obj.expires_at.isoformat() if obj.expires_at else '',
    )
    cache.set(
        detail_key,
        resolved.to_dict(),
        _DETAIL_TTL + random.randint(0, _DETAIL_JITTER),
    )
    return resolved


def invalidate(*codes: str) -> None:
    """短链变更 / 删除后主动失效缓存（可一次传多个短码，如 code 与 alias）。"""
    for code in codes:
        if not code:
            continue
        cache.delete(_detail_key(code))
        cache.delete(_null_key(code))
