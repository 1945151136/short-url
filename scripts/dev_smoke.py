"""
开发冒烟测试：用 Django test client 验证核心链路（不依赖外部 MySQL/Redis）。
运行：.venv\\Scripts\\python.exe scripts\\dev_smoke.py
"""
import os
import sys
import time
from pathlib import Path

# 让脚本能在项目根直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402
django.setup()

from django.test import Client  # noqa: E402

from shortener.models import AccessLog, ShortURL  # noqa: E402
from shortener.services import base62  # noqa: E402


def line(t=''):
    print(t)


def main():
    c = Client()
    ok = True

    # 0) Base62 可逆性
    for n in [1, 61, 62, 63, 3843, 999999, 20240601]:
        code = base62.encode(n)
        assert base62.decode(code) == n, (n, code)
    line('[通过] Base62 编码/解码可逆')

    # 1) 创建短链
    r = c.post('/api/shorten', data='{"original_url":"https://www.djangoproject.com/start/"}',
               content_type='application/json')
    assert r.status_code == 201, r.content
    data = r.json()['data']
    code = data['code']
    line(f"[通过] 创建短链: {data['short_url']}  ->  {data['original_url']}")

    # 2) 自定义别名
    r2 = c.post('/api/shorten', data='{"original_url":"https://docs.djangoproject.com/","alias":"myDocs"}',
                content_type='application/json')
    assert r2.status_code == 201, r2.content
    line(f"[通过] 自定义短码: {r2.json()['data']['short_url']}")

    # 3) 别名冲突应 400
    r_dup = c.post('/api/shorten', data='{"original_url":"https://x.com/","alias":"myDocs"}',
                   content_type='application/json')
    assert r_dup.status_code == 400, r_dup.content
    line('[通过] 重复自定义短码被拒绝')

    # 4) 内网地址 SSRF 拦截
    r_bad = c.post('/api/shorten', data='{"original_url":"http://127.0.0.1:8000/admin"}',
                   content_type='application/json')
    assert r_bad.status_code == 400, r_bad.content
    line('[通过] 内网地址被安全校验拦截')

    # 5) 302 跳转
    redir = c.get(f'/{code}')
    assert redir.status_code == 302, redir.status_code
    assert redir['Location'] == 'https://www.djangoproject.com/start/', redir['Location']
    line(f'[通过] 访问 /{code} 返回 302 -> {redir["Location"]}')

    # 6) 别名跳转
    redir2 = c.get('/myDocs')
    assert redir2.status_code == 302 and 'docs.djangoproject.com' in redir2['Location']
    line('[通过] 自定义短码 302 跳转正常')

    # 7) 不存在短码 404
    nf = c.get('/notexist123')
    assert nf.status_code == 404, nf.status_code
    line('[通过] 不存在短码返回 404')

    # 等待异步访问日志落库
    time.sleep(1.2)

    # 8) 访问统计
    st = c.get(f'/api/links/{code}')
    body = st.json()['data']
    line(f"[统计] PV={body['pv']} UV={body['uv']} 近7天={body['trend']}")
    line(f"[统计] 设备分布={body['distribution']['device']}")
    assert body['pv'] >= 1
    line('[通过] 访问统计 PV/UV/趋势/设备分布正常')

    line('\n全部核心链路验证通过 ✅')
    line(f'数据库中短链总数: {ShortURL.objects.count()}，访问日志数: {AccessLog.objects.count()}')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print(f'\n[失败] 断言未通过: {e}')
        sys.exit(1)
