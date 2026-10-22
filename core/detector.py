# -*- coding: utf-8 -*-
"""单词 / 短句判定"""
import re

_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def is_word(text: str) -> bool:
    """纯字母（可含连字符/撇号）且无空白 → 视为单词；否则视为短句。"""
    t = (text or "").strip()
    if not t or len(t) > 40:
        return False
    return bool(_WORD_RE.match(t))


# 汉字（含扩展 A 区与兼容区）。划词里出现任何一个都视为"含中文"
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 中文常用标点：这些出现也基本可以判定为中文语境
_CJK_PUNCT = set("，。！？；：、“”‘’（）《》【】…—·")


def has_chinese(text: str) -> bool:
    """文本中是否包含中文（汉字或中文标点）"""
    t = text or ""
    if _CJK_RE.search(t):
        return True
    return any(c in _CJK_PUNCT for c in t)


def is_english(text: str) -> bool:
    """是否为英文文本。

    开启「仅对英文划译」时要求更严格：**只要划选内容里出现中文（汉字或中文
    标点）就不算英文**，此时不弹窗翻译。否则需要有英文字母。
    """
    t = (text or "").strip()
    if not t:
        return False
    letters = sum(1 for c in t if c.isascii() and c.isalpha())
    if letters == 0:
        return False
    return not has_chinese(t)


def normalize(text: str) -> str:
    return " ".join((text or "").split())


# URL：协议头或 www 开头，且中间没有空白（划词选中的链接通常是一整串）
_URL_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)


def is_url(text: str) -> bool:
    """是否为网址：http(s):// 或 www. 开头且不含空白。

    链接本身不需要翻译，弹窗只要给出「打开 / 复制」就够了。
    """
    return bool(_URL_RE.match((text or "").strip()))
