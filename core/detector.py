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


def has_english(text: str) -> bool:
    """文本中是否包含英文字母"""
    return any(c.isascii() and c.isalpha() for c in (text or ""))


LANGSCOPE_EN = "en"        # 只有英文
LANGSCOPE_ZH = "zh"        # 只有中文
LANGSCOPE_MIXED = "both"   # 中英混排
LANGSCOPE_OTHER = "other"  # 既无中文也无英文（纯数字/符号/其它语言字母等）


def lang_scope(text: str) -> str:
    """判定文本的语言归属，返回 en / zh / both / other 之一。"""
    t = text or ""
    en = has_english(t)
    zh = has_chinese(t)
    if en and zh:
        return LANGSCOPE_MIXED
    if en:
        return LANGSCOPE_EN
    if zh:
        return LANGSCOPE_ZH
    return LANGSCOPE_OTHER


def matches_scope(text: str, scope: str) -> bool:
    """按「翻译范围」设置判断该文本是否需要翻译。

    仅翻译英文：只要内容里含中文（含混排）就不算英文，与旧版 is_english 一致；
    仅翻译中文：内容里含中文即命中（混排也算）；
    中英文均翻译：含英文或含中文都命中，其它语言（如纯俄文）仍落在范围外。
    """
    if isinstance(scope, str):
        scope = scope.strip().lower()
    s = lang_scope(text)
    if scope == "zh":
        return s in (LANGSCOPE_ZH, LANGSCOPE_MIXED)
    if scope == "both":
        return s in (LANGSCOPE_EN, LANGSCOPE_ZH, LANGSCOPE_MIXED)
    # 默认 / 仅翻译英文
    return s == LANGSCOPE_EN


def is_english(text: str) -> bool:
    """是否为英文文本：有英文字母且不含中文（含中文者一律不算英文）。

    保留此函数以兼容旧调用，语义等价于 lang_scope(text) == en。
    """
    return lang_scope(text) == LANGSCOPE_EN


def normalize(text: str) -> str:
    return " ".join((text or "").split())


# URL：协议头或 www 开头，且中间没有空白（划词选中的链接通常是一整串）
_URL_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)


def is_url(text: str) -> bool:
    """是否为网址：http(s):// 或 www. 开头且不含空白。

    链接本身不需要翻译，弹窗只要给出「打开 / 复制」就够了。
    """
    return bool(_URL_RE.match((text or "").strip()))
