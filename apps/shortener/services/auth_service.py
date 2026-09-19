"""鉴权辅助：开放 API 使用 X-API-Key，网页端使用 Django Session 登录。"""
from ..models import APIKey


def resolve_user(request):
    """解析当前请求归属的用户。

    优先级：请求头 ``X-API-Key`` -> 已登录 Session 用户 -> 匿名（None）。
    """
    api_key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    if api_key:
        obj = (
            APIKey.objects
            .filter(key=api_key.strip(), is_active=True)
            .select_related('user')
            .first()
        )
        if obj:
            return obj.user
        return None  # 显式传了错误的 Key，按鉴权失败处理
    if request.user.is_authenticated:
        return request.user
    return None
