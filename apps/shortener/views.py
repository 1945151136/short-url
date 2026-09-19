"""短链接服务视图：开放 RESTful API、网页页面与短链 302 跳转。"""
import json

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import ShortenForm
from .models import ShortURL
from .services import stats as stats_service
from .services.auth_service import resolve_user
from .services.cache_service import get_cached_short_link
from .services.rate_limit import check_rate_limit
from .services.recorder import record_access_async
from .services.short_url_service import (
    AliasError,
    create_short_url,
    delete_short_url,
    update_short_url_status,
)
from .services.url_validator import URLValidationError


# ---------------------------------------------------------------- 通用辅助
def full_short_url(code: str) -> str:
    return f'{settings.SITE_BASE_URL}/{code}'


def json_error(message: str, status: int = 400):
    return JsonResponse({'code': status, 'message': message}, status=status)


def _parse_body(request) -> dict:
    """兼容 JSON 请求体与表单 / query 参数。"""
    if request.content_type and 'application/json' in request.content_type:
        try:
            data = json.loads(request.body or '{}')
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    data = {k: v for k, v in request.POST.items()}
    data.update({k: v for k, v in request.GET.items() if k not in data})
    return data


def _owner_or_none(request, obj):
    """校验当前用户是否为短链所有者，返回 user；匿名 / 非所有者返回 None。"""
    user = resolve_user(request)
    if obj.creator_id is None:
        return None
    if user and obj.creator_id == user.id:
        return user
    return None


# ============================================================ 开放 API
@csrf_exempt
@require_http_methods(['POST'])
def api_shorten(request):
    """创建短链接：POST /api/shorten。"""
    user = resolve_user(request)
    if user is None and not settings.ALLOW_ANONYMOUS_CREATE:
        return json_error('未鉴权：请登录或在请求头 X-API-Key 中提供 API Key', 401)

    ip = stats_service.get_client_ip(request.META)
    allowed, used = check_rate_limit(
        f'create:{ip}', settings.RATE_LIMIT_MAX, settings.RATE_LIMIT_WINDOW
    )
    if not allowed:
        return json_error(f'请求过于频繁，{settings.RATE_LIMIT_WINDOW} 秒内最多创建 '
                          f'{settings.RATE_LIMIT_MAX} 次', 429)

    data = _parse_body(request)
    try:
        obj = create_short_url(
            original_url=data.get('original_url') or data.get('url') or data.get('dest_url'),
            creator=user,
            alias=data.get('alias', ''),
            remarks=data.get('remarks', ''),
            expires_at=data.get('expires_at'),
        )
    except (URLValidationError, AliasError, ValueError) as exc:
        return json_error(str(exc), 400)

    return JsonResponse({
        'code': 201,
        'message': 'created',
        'data': {
            'code': obj.short_code,
            'short_url': full_short_url(obj.short_code),
            'original_url': obj.original_url,
            'expires_at': obj.expires_at.isoformat() if obj.expires_at else None,
        },
    }, status=201)


@csrf_exempt
@require_http_methods(['GET'])
def api_my_links(request):
    """当前用户的短链列表：GET /api/links。"""
    user = resolve_user(request)
    if user is None:
        return json_error('未鉴权', 401)
    links = (
        ShortURL.objects.filter(creator=user)
        .values('id', 'code', 'alias', 'original_url', 'remarks',
                'is_active', 'expires_at', 'created_at')
    )
    data = []
    for row in links:
        code = row['alias'] or row['code']
        data.append({
            **row,
            'short_url': full_short_url(code),
            'created_at': row['created_at'].isoformat(),
            'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None,
        })
    return JsonResponse({'code': 200, 'message': 'success', 'data': data})


@csrf_exempt
def api_link_detail(request, code):
    """单条短链资源：GET 统计 / PATCH 更新 / DELETE 删除。"""
    obj = ShortURL.objects.filter(code=code).first() or \
        ShortURL.objects.filter(alias=code).first()
    if obj is None:
        return json_error('短链接不存在', 404)

    # ---- GET：读取统计（匿名创建的短链允许创建者为空，登录后台员工可读）----
    if request.method == 'GET':
        not_owner = obj.creator_id is not None and _owner_or_none(request, obj) is None
        if not_owner and not request.user.is_staff:
            return json_error('无权查看该短链统计', 403)
        pv, uv = stats_service.get_pv_uv(obj.short_code)
        return JsonResponse({
            'code': 200,
            'message': 'success',
            'data': {
                'short_url': full_short_url(obj.short_code),
                'original_url': obj.original_url,
                'pv': pv,
                'uv': uv,
                'trend': stats_service.get_daily_trend(obj, days=7),
                'distribution': stats_service.get_distributions(obj),
            },
        })

    # ---- 写操作必须为所有者 ----
    if _owner_or_none(request, obj) is None:
        return json_error('无权操作该短链', 403)

    if request.method in ('PATCH', 'POST'):
        data = _parse_body(request)
        kwargs = {}
        if 'is_active' in data:
            kwargs['is_active'] = str(data['is_active']).lower() in ('1', 'true', 'yes', 'on')
        if 'expires_at' in data:
            kwargs['expires_at'] = data['expires_at']
        try:
            update_short_url_status(obj, **kwargs)
        except ValueError as exc:
            return json_error(str(exc), 400)
        return JsonResponse({'code': 200, 'message': 'updated'})

    if request.method == 'DELETE':
        delete_short_url(obj)
        return JsonResponse({'code': 200, 'message': 'deleted'})

    return json_error('不支持的请求方法', 405)


@require_http_methods(['GET'])
def health(request):
    """健康检查。"""
    return JsonResponse({'code': 200, 'message': 'ok', 'service': 'short-url'})


# ============================================================ 网页页面
def index(request):
    """首页：短链生成 + （登录后）最近短链。"""
    result = None
    error = None
    if request.method == 'POST':
        form = ShortenForm(request.POST)
        if form.is_valid():
            user = getattr(request.user, 'is_authenticated', False) and request.user or None
            ip = stats_service.get_client_ip(request.META)
            allowed, _ = check_rate_limit(
                f'create:{ip}', settings.RATE_LIMIT_MAX, settings.RATE_LIMIT_WINDOW
            )
            if not allowed:
                error = '操作过于频繁，请稍后再试。'
            else:
                try:
                    cd = form.cleaned_data
                    obj = create_short_url(
                        original_url=cd['original_url'],
                        creator=user,
                        alias=cd.get('alias', ''),
                        remarks=cd.get('remarks', ''),
                        expires_at=cd.get('expires_at'),
                    )
                    result = {
                        'short_url': full_short_url(obj.short_code),
                        'original_url': obj.original_url,
                    }
                except (URLValidationError, AliasError, ValueError) as exc:
                    error = str(exc)
    else:
        form = ShortenForm()

    recent = []
    if request.user.is_authenticated:
        recent = ShortURL.objects.filter(creator=request.user)[:8]
    return render(request, 'shortener/index.html', {
        'form': form, 'result': result, 'error': error, 'recent': recent,
        'full': full_short_url,
    })


@login_required
def dashboard(request):
    """个人短链管理看板。"""
    links_qs = ShortURL.objects.filter(creator=request.user)
    links = []
    total_pv = 0
    for obj in links_qs:
        pv, uv = stats_service.get_pv_uv(obj.short_code)
        total_pv += pv
        links.append({'obj': obj, 'pv': pv, 'uv': uv,
                      'short_url': full_short_url(obj.short_code)})
    return render(request, 'shortener/dashboard.html', {
        'links': links,
        'total_links': len(links),
        'total_pv': total_pv,
    })


@login_required
def link_detail(request, code):
    """单条短链统计详情（图表）。"""
    obj = ShortURL.objects.filter(creator=request.user, code=code).first()
    if obj is None:
        obj = ShortURL.objects.filter(creator=request.user, alias=code).first()
    if obj is None:
        raise Http404('短链不存在或不属于当前用户')

    pv, uv = stats_service.get_pv_uv(obj.short_code)
    trend = stats_service.get_daily_trend(obj, days=7)
    dist = stats_service.get_distributions(obj)
    return render(request, 'shortener/detail.html', {
        'obj': obj,
        'pv': pv,
        'uv': uv,
        'trend': trend,
        'trend_json': json.dumps(trend, ensure_ascii=False),
        'device_json': json.dumps(dist['device'], ensure_ascii=False),
        'browser_json': json.dumps(dist['browser'], ensure_ascii=False),
        'short_url': full_short_url(obj.short_code),
    })


def register(request):
    """简单注册：注册成功自动登录并跳转到看板。"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'shortener/register.html', {'form': form})


# ============================================================ 短链跳转（核心）
def redirect_view(request, code):
    """访问 /<短码>：命中则 302 重定向到原始链接，并异步记录访问。"""
    resolved = get_cached_short_link(code)

    if resolved is None:
        return render(request, 'shortener/error.html', {
            'title': '短链接不存在',
            'message': '你访问的短链接无效或已被删除，请确认链接是否正确。',
        }, status=404)

    obj = ShortURL.objects.filter(id=resolved.id).only('is_active', 'expires_at').first()
    if obj is None or not obj.is_accessible:
        reason = '该短链接已被管理员停用' if (obj and not obj.is_active) else '该短链接已过期'
        return render(request, 'shortener/error.html', {
            'title': '短链接不可用',
            'message': f'{reason}，无法继续跳转。',
        }, status=410)

    # 异步记录访问，不阻塞重定向
    record_access_async(
        short_url_id=resolved.id,
        code=resolved.code,
        ip=stats_service.get_client_ip(request.META),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        referer=request.META.get('HTTP_REFERER', ''),
    )
    return HttpResponseRedirect(resolved.original_url, status=302)
