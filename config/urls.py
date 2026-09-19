"""主路由：管理后台、认证、短链接应用。"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    # 短链接相关路由（API、页面、以及根路径下的 /<短码> 跳转）
    path('', include('shortener.urls')),
]
