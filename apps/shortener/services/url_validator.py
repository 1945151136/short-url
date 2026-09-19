"""
URL 合法性与安全性校验。

除了基本的格式校验，还做了轻量的 SSRF 防护：短链服务端会根据目标 URL 做跳转，
若允许指向内网地址 / 云厂商元数据地址，可能被利用进行内网探测，因此对这类目标做拦截。
"""
import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {'http', 'https'}


class URLValidationError(ValueError):
    """URL 校验失败。"""


def _is_private_host(host: str) -> bool:
    """判断主机名是否指向环回 / 内网 / 链路本地等地址。"""
    host = host.strip().lower().rstrip('.')
    if host in ('localhost', 'localhost.localdomain'):
        return True

    # 字面量 IP
    try:
        ip = ipaddress.ip_address(host.strip('[]'))
        return (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        )
    except ValueError:
        pass

    # 域名：解析其 A 记录，若解析到内网地址也拦截（解析失败不阻断，交给跳转处理）
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
    except (socket.gaierror, ValueError, OSError):
        return False
    return False


def normalize_and_validate_url(raw_url: str, allow_private: bool = False) -> str:
    """补全协议头并校验，返回规范化后的 URL；不合法抛 :class:`URLValidationError`。"""
    if not raw_url or not raw_url.strip():
        raise URLValidationError('链接不能为空')

    url = raw_url.strip()
    if '://' not in url:
        url = 'http://' + url

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise URLValidationError('仅支持 http / https 协议的链接')
    if not parsed.netloc:
        raise URLValidationError('链接格式不正确，缺少域名')

    host = parsed.hostname or ''
    if not host:
        raise URLValidationError('链接格式不正确，缺少域名')

    if not allow_private and _is_private_host(host):
        raise URLValidationError('不允许指向内网或本机地址的链接')

    return url
