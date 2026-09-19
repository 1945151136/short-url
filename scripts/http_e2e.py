"""
真实 HTTP 端到端测试：需要先启动 runserver。
默认访问 http://127.0.0.1:8090，可用环境变量 BASE_URL 覆盖。
运行：.venv\\Scripts\\python.exe scripts\\http_e2e.py
"""
import os
import re
import sys
import time

import requests

BASE = os.getenv('BASE_URL', 'http://127.0.0.1:8090')
TIMEOUT = 10
passed = 0


def check(name, cond, extra=''):
    global passed
    status = '✅' if cond else '❌'
    print(f'{status} {name}' + (f'  | {extra}' if extra else ''))
    if not cond:
        sys.exit(1)
    passed += 1


def no_proxy_session():
    s = requests.Session()
    s.trust_env = False  # 绕过系统代理，直连本机
    return s


def get_csrf(s, path):
    r = s.get(BASE + path, timeout=TIMEOUT)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    return token.group(1) if token else None


def main():
    # ---------- 1. 健康检查 ----------
    s = no_proxy_session()
    r = s.get(BASE + '/api/health', timeout=TIMEOUT)
    check('健康检查 200', r.status_code == 200, r.text)

    # ---------- 2. 匿名创建短链 ----------
    r = s.post(BASE + '/api/shorten', json={'original_url': 'https://www.python.org/'}, timeout=TIMEOUT)
    check('匿名创建短链 201', r.status_code == 201, r.text)
    code = r.json()['data']['code']
    check('短码为 6 位', len(code) == 6, code)

    # ---------- 3. 302 跳转 ----------
    r = s.get(BASE + f'/{code}', allow_redirects=False, timeout=TIMEOUT)
    check('访问短链返回 302', r.status_code == 302, f'status={r.status_code}')
    check('Location 指向原始链接', r.headers.get('Location') == 'https://www.python.org/',
          r.headers.get('Location'))

    # ---------- 4. 非法 / 内网链接拦截 ----------
    bad_cases = [
        ('ftp://example.com/file', '非 http/https 协议'),
        ('http://192.168.1.1/', '内网地址'),
        ('http://127.0.0.1:8090/', '环回地址'),
        ('http://169.254.169.254/latest/meta-data/', '云元数据地址'),
        ('http://', '缺少域名'),
        ('   ', '空白链接'),
    ]
    for bad, why in bad_cases:
        r = s.post(BASE + '/api/shorten', json={'original_url': bad}, timeout=TIMEOUT)
        check(f'非法链接拦截（{why}）', r.status_code == 400, f'{bad.strip() or "<空>"} -> {r.status_code}')

    # ---------- 5. 不存在短码 404 ----------
    r = s.get(BASE + '/zzzzzz', timeout=TIMEOUT)
    check('不存在短码 404', r.status_code == 404)

    # ---------- 6. 注册新用户 ----------
    username = f'e2e_{int(time.time())}'
    password = 'Str0ng!Pass_2026'
    s2 = no_proxy_session()
    token = get_csrf(s2, '/register/')
    r = s2.post(BASE + '/register/', data={
        'csrfmiddlewaretoken': token,
        'username': username, 'password1': password, 'password2': password,
    }, timeout=TIMEOUT, allow_redirects=False)
    check('注册成功并跳转', r.status_code in (302, 200), f'status={r.status_code}')

    # ---------- 7. 登录态创建短链 ----------
    r = s2.post(BASE + '/api/shorten', json={'original_url': 'https://docs.djangoproject.com/'},
                timeout=TIMEOUT)
    check('登录态创建短链 201', r.status_code == 201, r.text)
    my_code = r.json()['data']['code']

    # ---------- 8. 从看板获取 API Key ----------
    r = s2.get(BASE + '/dashboard/', timeout=TIMEOUT)
    m = re.search(r'id="apiKey"[^>]*>(\S+)<', r.text)
    check('看板展示 API Key', bool(m), m.group(1) if m else '未找到')
    api_key = m.group(1) if m else ''

    # ---------- 9. 用 X-API-Key 鉴权创建（全新会话）----------
    s3 = no_proxy_session()
    r = s3.post(BASE + '/api/shorten',
                json={'original_url': 'https://www.nginx.com/'},
                headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    check('API Key 鉴权创建 201', r.status_code == 201, r.text)
    key_code = r.json()['data']['code']

    # 无鉴权应被拒绝（列表接口）
    r = no_proxy_session().get(BASE + '/api/links', timeout=TIMEOUT)
    check('无鉴权访问列表 401', r.status_code == 401)
    # 带 Key 可访问列表
    r = s3.get(BASE + '/api/links', headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    check('API Key 访问列表 200', r.status_code == 200 and len(r.json()['data']) >= 2,
          f"{len(r.json().get('data', []))} 条")

    # ---------- 10. 多次访问验证 PV/UV ----------
    for _ in range(3):
        s.get(BASE + f'/{code}', allow_redirects=False, timeout=TIMEOUT)
    time.sleep(1.0)
    r = s.get(BASE + f'/api/links/{code}', timeout=TIMEOUT)
    stat = r.json()['data']
    check('PV 统计正确(>=4)', stat['pv'] >= 4, f"PV={stat['pv']}")
    check('返回趋势与分布', 'trend' in stat and 'distribution' in stat)

    # ---------- 11. 停用 / 启用 / 删除 ----------
    r = s3.patch(BASE + f'/api/links/{key_code}', json={'is_active': False},
                 headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    check('停用短链 200', r.status_code == 200, r.text)
    r = s.get(BASE + f'/{key_code}', allow_redirects=False, timeout=TIMEOUT)
    check('停用后访问返回 410', r.status_code == 410, f'status={r.status_code}')

    r = s3.delete(BASE + f'/api/links/{key_code}', headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    check('删除短链 200', r.status_code == 200, r.text)
    r = s.get(BASE + f'/{key_code}', allow_redirects=False, timeout=TIMEOUT)
    check('删除后访问 404', r.status_code == 404)

    # ---------- 12. 详情统计页可渲染 ----------
    r = s2.get(BASE + f'/links/{my_code}/', timeout=TIMEOUT)
    check('统计详情页 200', r.status_code == 200 and (b'Chart' in r.content or b'canvas' in r.content))

    print(f'\n🎉 端到端测试全部通过，共 {passed} 项检查。')


if __name__ == '__main__':
    try:
        main()
    except requests.RequestException as e:
        print(f'\n❌ 网络错误（请确认 runserver 已在 {BASE} 启动）：{e}')
        sys.exit(1)
