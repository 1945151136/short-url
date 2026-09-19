"""短链接应用路由。

注意：根路径下的 ``<str:code>`` 跳转是兜底匹配，必须放在所有具名路由之后，
且 str 转换器不含斜杠，因此不会拦截 api/、dashboard/、static/ 等多级路径。
"""
from django.urls import path

from . import views

urlpatterns = [
    # ---------- 网页页面 ----------
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('links/<str:code>/', views.link_detail, name='link_detail'),

    # ---------- 开放 RESTful API ----------
    path('api/health', views.health, name='api_health'),
    path('api/shorten', views.api_shorten, name='api_shorten'),
    path('api/links', views.api_my_links, name='api_my_links'),
    path('api/links/<str:code>', views.api_link_detail, name='api_link_detail'),

    # ---------- 短链 302 跳转（兜底，务必放最后）----------
    path('<str:code>/', views.redirect_view, name='redirect'),
    path('<str:code>', views.redirect_view, name='redirect_no_slash'),
]
