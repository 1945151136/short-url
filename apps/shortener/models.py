"""短链接核心数据模型。"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class ShortURL(models.Model):
    """长短链映射表。

    - code：系统通过「自增主键 ID + Base62」发号生成的短码，全局唯一、可逆；
    - alias：用户自定义短码（可选），与 code 二选一作为对外访问短码；
    - 访问明细记录在 :class:`AccessLog`，统计实时聚合。
    """

    code = models.CharField('系统短码', max_length=16, unique=True, db_index=True, blank=True)
    alias = models.CharField('自定义短码', max_length=32, unique=True, null=True, blank=True)
    original_url = models.URLField('原始长链接', max_length=2048)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='创建者',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='short_urls',
    )
    remarks = models.CharField('备注', max_length=255, blank=True, default='')
    is_active = models.BooleanField('是否启用', default=True)
    expires_at = models.DateTimeField('过期时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'short_url'
        verbose_name = '短链接'
        verbose_name_plural = verbose_name
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('creator', 'created_at'), name='idx_creator_created'),
        ]

    def __str__(self):
        return f'{self.short_code} -> {self.original_url}'

    @property
    def short_code(self) -> str:
        """对外短码：自定义别名优先，否则用系统发号短码。"""
        return self.alias or self.code

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.now())

    @property
    def is_accessible(self) -> bool:
        """当前是否可正常跳转（启用且未过期）。"""
        return self.is_active and not self.is_expired


class AccessLog(models.Model):
    """短链访问明细，用于 PV/UV、设备、来源、趋势等统计。"""

    short_url = models.ForeignKey(
        ShortURL, verbose_name='短链接', on_delete=models.CASCADE, related_name='logs'
    )
    ip = models.GenericIPAddressField('访问 IP')
    user_agent = models.CharField('User-Agent', max_length=512, blank=True, default='')
    device_type = models.CharField('设备类型', max_length=16, default='pc')
    browser = models.CharField('浏览器', max_length=32, blank=True, default='')
    os_name = models.CharField('操作系统', max_length=32, blank=True, default='')
    referer = models.URLField('来源页', max_length=1024, blank=True, null=True)
    accessed_at = models.DateTimeField('访问时间', auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'access_log'
        verbose_name = '访问记录'
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=('short_url', 'accessed_at'), name='idx_url_time'),
            models.Index(fields=('accessed_at',), name='idx_accessed_at'),
        ]

    def __str__(self):
        return f'{self.short_url.short_code} @ {self.accessed_at:%Y-%m-%d %H:%M:%S}'


class APIKey(models.Model):
    """开放 API 鉴权密钥，与用户一对一，创建用户时自动签发。"""

    key = models.CharField('API Key', max_length=64, unique=True, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name='所属用户',
        on_delete=models.CASCADE, related_name='api_key',
    )
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'api_key'
        verbose_name = 'API 密钥'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user}: {self.key[:8]}...'
