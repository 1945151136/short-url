"""访问统计：UA 解析、明细落库、PV/UV 计数、趋势与分布聚合。"""
from collections import OrderedDict
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

# 设备类型中文展示
DEVICE_LABELS = {
    'pc': '电脑',
    'mobile': '手机',
    'tablet': '平板',
    'bot': '爬虫/其他',
    'other': '其他',
}


def get_client_ip(meta) -> str:
    """获取真实客户端 IP（兼容 Nginx 反向代理后的 X-Forwarded-For）。"""
    xff = meta.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return meta.get('REMOTE_ADDR', '0.0.0.0')


def parse_user_agent(ua_string: str) -> dict:
    """解析 User-Agent，返回设备类型 / 浏览器 / 操作系统。"""
    try:
        from user_agents import parse
        ua = parse(ua_string or '')
        if ua.is_bot:
            device = 'bot'
        elif ua.is_mobile:
            device = 'mobile'
        elif ua.is_tablet:
            device = 'tablet'
        elif ua.is_pc:
            device = 'pc'
        else:
            device = 'other'
        browser = ua.browser.family or 'Unknown'
        os_name = ua.os.family or 'Unknown'
        # 归一化过长 / 过杂的名字
        browser = browser.split()[0] if browser else 'Unknown'
        return {'device_type': device, 'browser': browser[:32], 'os_name': os_name[:32]}
    except Exception:
        return {'device_type': 'other', 'browser': '', 'os_name': ''}


def _redis_conn():
    """获取原生 Redis 连接，不可用时返回 None（功能降级为纯数据库统计）。"""
    try:
        from django_redis import get_redis_connection
        return get_redis_connection('default')
    except Exception:
        return None


def record_access(*, short_url_id: int, code: str, ip: str,
                  user_agent: str, referer: str) -> None:
    """记录一次访问：写明细 + 更新 Redis 的 PV 计数与 UV(HyperLogLog)。"""
    from shortener.models import AccessLog

    parsed = parse_user_agent(user_agent)
    AccessLog.objects.create(
        short_url_id=short_url_id,
        ip=ip or '0.0.0.0',
        user_agent=(user_agent or '')[:512],
        referer=referer or None,
        **parsed,
    )

    conn = _redis_conn()
    if conn is not None:
        try:
            today = timezone.now().strftime('%Y%m%d')
            pipe = conn.pipeline()
            pipe.incr(f'stats:pv:{code}')
            pipe.incr(f'stats:pv:{code}:{today}')
            pipe.pfadd(f'stats:uv:{code}', ip)
            pipe.pfadd(f'stats:uv:{code}:{today}', ip)
            pipe.execute()
        except Exception:
            # 统计计数失败不影响主流程，明细已落库
            pass


def get_pv_uv(code: str):
    """返回 (PV, UV)，优先读 Redis，缺失时回退数据库聚合。"""
    conn = _redis_conn()
    pv = uv = None
    if conn is not None:
        try:
            pv = int(conn.get(f'stats:pv:{code}') or 0)
            uv = int(conn.pfcount(f'stats:uv:{code}') or 0)
        except Exception:
            pv = uv = None

    if pv is None:
        from shortener.models import AccessLog
        qs = AccessLog.objects.filter(short_url__code=code)
        pv = qs.count()
        uv = qs.values('ip').distinct().count()
    return pv, uv


def get_daily_trend(short_url, days: int = 7) -> list:
    """近 N 天每天的 PV（含补零），返回 [{date, pv}]。"""
    from shortener.models import AccessLog

    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    rows = (
        AccessLog.objects
        .filter(short_url=short_url, accessed_at__date__gte=start)
        .annotate(day=TruncDate('accessed_at'))
        .values('day')
        .annotate(pv=Count('id'))
    )
    mapping = {row['day']: row['pv'] for row in rows}

    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        result.append({'date': day.strftime('%m-%d'), 'pv': mapping.get(day, 0)})
    return result


def _distribution(short_url, field: str) -> dict:
    from shortener.models import AccessLog
    rows = (
        AccessLog.objects.filter(short_url=short_url)
        .values(field).annotate(c=Count('id')).order_by('-c')
    )
    return {row[field] or '未知': row['c'] for row in rows}


def get_distributions(short_url) -> dict:
    """设备 / 浏览器 / 操作系统分布。"""
    device_raw = _distribution(short_url, 'device_type')
    device = OrderedDict()
    for key, val in device_raw.items():
        device[DEVICE_LABELS.get(key, key)] = val
    return {
        'device': device,
        'browser': _distribution(short_url, 'browser'),
        'os': _distribution(short_url, 'os_name'),
    }
