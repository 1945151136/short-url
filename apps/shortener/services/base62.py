"""
Base62 编解码与短码发号器。

为什么用「自增 ID + Base62」而不是随机字符串？
------------------------------------------------
- **全局唯一、天然不冲突**：自增主键一一映射到 Base62 串，无需「生成后查重、冲突重试」；
- **可逆**：短码可解码回主键，必要时能直接定位记录；
- **码长随数据量自然增长且非常紧凑**：62^6 ≈ 568 亿，6 位短码即可容纳海量链接；
- **性能好**：发号依赖数据库自增序列，无随机 IO 与唯一键冲突开销。

为避免短码连续可猜（被人遍历爬取），这里对标准 Base62 字母表用**固定种子洗牌**：
编码结果仍是与 ID 一一对应的双射（保证唯一、可逆），但从外部看不出连续规律。
"""
import random

# 标准字母表：0-9 a-z A-Z，共 62 个字符
_STANDARD_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
_BASE = len(_STANDARD_ALPHABET)  # 62


def _build_shuffled_alphabet(seed: int = 20240601) -> str:
    """用固定种子洗牌，保证每次运行得到同一张（合法的）62 字符排列表。"""
    chars = list(_STANDARD_ALPHABET)
    random.Random(seed).shuffle(chars)
    shuffled = ''.join(chars)
    # 断言：洗牌后仍是 62 个互不重复的字符
    assert len(shuffled) == 62 and len(set(shuffled)) == 62
    return shuffled


ALPHABET = _build_shuffled_alphabet()
_CHAR_TO_INDEX = {ch: idx for idx, ch in enumerate(ALPHABET)}

# 发号偏移量 = 62^5。
# 作用：① 让短码从 6 位起步，更美观、更接近主流短链产品；
# ② 外部无法通过短码长短 / 顺序推测平台真实数据量，也提高了遍历成本。
# BigInt 主键上限约 9.2×10^18，加 9 亿偏移无溢出风险。
CODE_ID_OFFSET = _BASE ** 5


def encode_id(pk: int) -> str:
    """数据库自增主键 -> 对外短码（含偏移）。"""
    return encode(pk + CODE_ID_OFFSET)


def decode_id(code: str) -> int:
    """对外短码 -> 数据库主键（减偏移）。"""
    value = decode(code)
    return value - CODE_ID_OFFSET if value >= CODE_ID_OFFSET else value


def encode(num: int) -> str:
    """非负整数 -> Base62 短码。"""
    if num == 0:
        return ALPHABET[0]
    if num < 0:
        raise ValueError('短码发号 ID 必须为非负整数')

    digits = []
    while num > 0:
        num, rem = divmod(num, _BASE)
        digits.append(ALPHABET[rem])
    return ''.join(reversed(digits))


def decode(code: str) -> int:
    """Base62 短码 -> 整数 ID；含非法字符时抛 ValueError。"""
    if not code:
        raise ValueError('空短码')
    num = 0
    for ch in code:
        try:
            num = num * _BASE + _CHAR_TO_INDEX[ch]
        except KeyError as exc:
            raise ValueError(f'非法短码字符: {ch}') from exc
    return num


# 路由层保留词，禁止作为自定义短码，避免与页面 / 接口路径冲突
RESERVED_WORDS = {
    'admin', 'api', 'dashboard', 'accounts', 'login', 'logout', 'register',
    'static', 'media', 'favicon.ico', 'robots.txt', 'health', 'shorten',
    'stats', 'links', 'docs', 'index', 'home',
}
