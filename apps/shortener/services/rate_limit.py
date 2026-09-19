"""
基于 Redis（Django cache 后端）的固定窗口限流器。

用于限制同一 IP / 用户在时间窗口内调用「生成短链」等写接口的次数，防止恶意刷接口。
Redis 的 INCR 为原子操作，可在多进程 / 多实例部署下正确计数；
本地无 Redis 时自动使用 LocMemCache，功能同样可用（仅在单进程内有效）。
"""
from django.core.cache import cache


def check_rate_limit(identifier: str, max_count: int, window_seconds: int):
    """固定窗口计数限流。

    :param identifier: 限流维度标识，如 ``create:1.2.3.4``
    :param max_count: 窗口内允许的最大次数
    :param window_seconds: 时间窗口（秒）
    :return: (是否放行, 当前窗口已用次数)
    """
    key = f'ratelimit:{identifier}'

    # key 不存在时初始化为 1，并设置过期；add 本身是 set-if-not-exists
    if cache.add(key, 1, timeout=window_seconds):
        return True, 1

    try:
        current = cache.incr(key)
    except ValueError:
        # 极端情况下 key 刚好过期，重新初始化
        cache.add(key, 1, timeout=window_seconds)
        current = 1

    return current <= max_count, current
