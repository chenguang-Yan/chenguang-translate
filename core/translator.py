# -*- coding: utf-8 -*-
"""翻译服务封装（支持多翻译源）

- 基本翻译：有道智云 / 百度翻译开放平台 / Google Cloud Translation / DeepL
- 单词详情（音标/词性释义/网络释义）：dict.youdao.com jsonapi（有道词典，无需凭据）
- 发音：dictvoice 在线音频 URL
"""
import hashlib
import time
import urllib.parse
import uuid

import requests

import config

TEXT_API = "https://openapi.youdao.com/api"
DICT_API = "https://dict.youdao.com/jsonapi"
VOICE_URL = "https://dict.youdao.com/dictvoice?audio={word}&type={t}"  # t=1 英音 / 2 美音

BAIDU_API = "https://fanyi-api.baidu.com/api/trans/vip/translate"
GOOGLE_API = "https://translation.googleapis.com/language/translate/v2"
DEEPL_API_FREE = "https://api-free.deepl.com/v2/translate"
DEEPL_API_PRO = "https://api.deepl.com/v2/translate"

TIMEOUT = 8

# 可选翻译源：key -> 显示名
SOURCES = {
    "youdao": "有道翻译",
    "baidu": "百度翻译",
    "google": "谷歌翻译",
    "deepl": "DeepL 翻译",
}


class TranslateError(Exception):
    pass


_NOT_CONFIGURED_MSG = (
    "翻译源未配置：请在设置界面「翻译源 → 有道」填写 appKey / appSecret，"
    "或直接在程序目录的 config.json 中填写 youdao_app_key / youdao_app_secret"
    "（也可设置环境变量 YOUDAO_APP_KEY / YOUDAO_APP_SECRET）"
)


def current_source() -> str:
    """当前配置的翻译源（未知值回落 youdao）"""
    src = (config.load().get("translate_source") or "youdao").lower()
    return src if src in SOURCES else "youdao"


def _truncate(q: str) -> str:
    if len(q) <= 20:
        return q
    return q[:10] + str(len(q)) + q[-10:]


def voice_url(word: str, accent: str = "us") -> str:
    t = 2 if accent == "us" else 1
    return VOICE_URL.format(word=urllib.parse.quote(word), t=t)


def voice_urls(text: str, accent: str = "us") -> list:
    """返回候选发音地址：[首选口音, 备用口音]。

    dictvoice 对同一段文本的英音/美音可用性并不一致——部分英文短句只有英音或
    只有美音（另一种会返回 500 "returned null audio"）。因此这里返回两个候选，
    由调用方按顺序尝试，保证短句朗读尽可能有声音。
    单词和短句都可用（短句即整句 TTS）。
    """
    order = ("us", "uk") if accent == "us" else ("uk", "us")
    return [voice_url(text, a) for a in order]


# ---------------- 基本翻译（文本翻译 API） ----------------

def translate_text(text: str, app_key: str = None, app_secret: str = None,
                   from_lang: str = "auto", to_lang: str = "zh-CHS") -> str:
    """调用有道智云文本翻译 API，返回译文。

    凭据优先级：显式传入 > 环境变量 > config.json。
    """
    cfg_key, cfg_secret = config.youdao_credentials()
    app_key = app_key or cfg_key
    app_secret = app_secret or cfg_secret
    if not app_key or not app_secret:
        raise TranslateError(_NOT_CONFIGURED_MSG)
    salt = str(uuid.uuid4())
    curtime = str(int(time.time()))
    sign = hashlib.sha256(
        (app_key + _truncate(text) + salt + curtime + app_secret).encode("utf-8")
    ).hexdigest()
    data = {
        "q": text,
        "from": from_lang,
        "to": to_lang,
        "appKey": app_key,
        "salt": salt,
        "curtime": curtime,
        "sign": sign,
        "signType": "v3",
    }
    try:
        r = requests.post(TEXT_API, data=data, timeout=TIMEOUT)
        r.raise_for_status()
        res = r.json()
    except requests.RequestException as e:
        raise TranslateError(f"网络请求失败：{e}")
    if int(res.get("errorCode", "-1")) != 0:
        raise TranslateError(f"翻译接口错误码：{res.get('errorCode')}（可在有道智云文档查询含义）")
    translation = res.get("translation") or []
    if not translation:
        raise TranslateError("翻译结果为空")
    return "\n".join(translation)


# ---------------- 单词详情（词典 jsonapi） ----------------

def lookup_word(word: str) -> dict:
    """查询单词详情，返回：
    {
      "uk": {"phone": "...", "speech": url}, "us": {...},
      "basic": ["n. 释义", ...],
      "web": [("词组", "释义A；释义B"), ...],
    }
    部分字段缺失时优雅降级。
    """
    dicts = '{"count":99,"dicts":[["ec"],["web_trans"]]}'
    params = {
        "jsonversion": "2",
        "client": "mobile",
        "q": word,
        "dicts": dicts,
    }
    result = {"uk": None, "us": None, "basic": [], "web": []}
    try:
        r = requests.get(DICT_API, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return result

    # ec.word 可能是 dict 或 list[条目]；统一成条目列表取首个
    ecraw = data.get("ec")
    if isinstance(ecraw, dict):
        raw = ecraw.get("word")
    elif isinstance(ecraw, list):
        raw = ecraw
    else:
        raw = None
    entries = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    entry = entries[0] if entries else {}

    def _speech(item, key):
        """接口返回的 ukspeech/usspeech 可能是 "word&type=2" 这类残缺片段，
        不可直接拼域名；只接受完整 URL 或以 / 开头的合法路径，否则返回 None，
        由上层回退到 voice_url() 生成标准发音地址。"""
        url = (item or {}).get(key) or ""
        if url.startswith("http"):
            return url
        if url.startswith("/") and " " not in url:
            return "https://dict.youdao.com" + url
        return None

    phone_uk = entry.get("ukphone")
    phone_us = entry.get("usphone")
    result["uk"] = {"phone": phone_uk, "speech": _speech(entry, "ukspeech")} if phone_uk else None
    result["us"] = {"phone": phone_us, "speech": _speech(entry, "usspeech")} if phone_us else None

    # trs -> ["v. 释义", ...]（i[0] 已含词性前缀）
    for item in entry.get("trs") or []:
        if not isinstance(item, dict):
            continue
        for tr in (item.get("tr") or []):
            if isinstance(tr, dict):
                i = (tr.get("l") or {}).get("i") or []
                txt = i[0] if i else ""
                if txt:
                    result["basic"].append(txt)

    # 网络释义
    wt = (data.get("web_trans") or {}).get("web-transaction") or {}
    for entry_w in wt.get("web-translation") or []:
        key = entry_w.get("key") or ""
        vals = []
        for tr in (entry_w.get("trans") or [])[:3]:
            v = tr.get("value") if isinstance(tr, dict) else ""
            if v:
                vals.append(v)
        if key and vals:
            result["web"].append((key, "；".join(vals)))
    return result


# ---------------- 其他翻译源 ----------------

def translate_baidu(text: str, appid: str, secret: str,
                    from_lang: str = "auto", to_lang: str = "zh") -> str:
    """百度翻译开放平台（通用翻译 API，v3 之前的标准版签名 md5）。"""
    appid = (appid or "").strip()
    secret = (secret or "").strip()
    if not appid or not secret:
        raise TranslateError("百度翻译未配置：请填写 APP ID 与密钥")
    salt = str(uuid.uuid4().hex)
    sign = hashlib.md5((appid + text + salt + secret).encode("utf-8")).hexdigest()
    data = {
        "q": text, "from": from_lang, "to": to_lang,
        "appid": appid, "salt": salt, "sign": sign,
    }
    try:
        r = requests.post(BAIDU_API, data=data, timeout=TIMEOUT)
        r.raise_for_status()
        res = r.json()
    except requests.RequestException as e:
        raise TranslateError(f"网络请求失败：{e}")
    except ValueError:
        raise TranslateError("返回内容不是合法 JSON")
    if res.get("error_code"):
        raise TranslateError(f"百度翻译错误码：{res.get('error_code')}（{res.get('error_msg') or '详见开放平台文档'}）")
    out = [t.get("dst", "") for t in res.get("trans_result") or []]
    if not out or not any(out):
        raise TranslateError("翻译结果为空")
    return "\n".join(x for x in out if x)


def translate_google(text: str, api_key: str, target: str = "zh-CN") -> str:
    """Google Cloud Translation API v2（REST，使用 API Key）。"""
    key = (api_key or "").strip()
    if not key:
        raise TranslateError("谷歌翻译未配置：请填写 API 密钥")
    try:
        r = requests.post(
            GOOGLE_API,
            params={"key": key},
            data={"q": text, "target": target, "format": "text"},
            timeout=TIMEOUT)
        r.raise_for_status()
        res = r.json()
    except requests.RequestException as e:
        raise TranslateError(f"网络请求失败：{e}")
    except ValueError:
        raise TranslateError("返回内容不是合法 JSON")
    if res.get("error"):
        msg = (res["error"] or {}).get("message") or "未知错误"
        raise TranslateError(f"谷歌翻译接口错误：{msg}")
    trans = ((res.get("data") or {}).get("translations") or [])
    txt = trans[0].get("translatedText") if trans else ""
    if not txt:
        raise TranslateError("翻译结果为空")
    return txt


def translate_deepl(text: str, auth_key: str, free: bool = True,
                    target_lang: str = "ZH") -> str:
    """DeepL API（免费版 / 专业版）。"""
    auth_key = (auth_key or "").strip()
    if not auth_key:
        raise TranslateError("DeepL 未配置：请填写 Authentication Key")
    url = DEEPL_API_FREE if free else DEEPL_API_PRO
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"DeepL-Auth-Key {auth_key}",
                "Content-Type": "application/json",
            },
            json={"text": [text], "target_lang": target_lang},
            timeout=TIMEOUT)
        res = r.json() if r.content else {}
        if r.status_code >= 400:
            raise TranslateError(f"DeepL 接口错误 {r.status_code}（{res.get('message') or '请检查密钥与套餐类型'}）")
    except requests.RequestException as e:
        raise TranslateError(f"网络请求失败：{e}")
    except ValueError:
        raise TranslateError("返回内容不是合法 JSON")
    items = res.get("translations") or []
    txt = items[0].get("text") if items else ""
    if not txt:
        raise TranslateError("翻译结果为空")
    return txt


# ---------------- 统一入口（按配置分发） ----------------

MAX_Q_BYTES = 4800      # 有道要求单次 q 的 UTF-8 字节数 ≤ 5000，留一点余量


def _fit_bytes(text: str, limit: int = MAX_Q_BYTES) -> str:
    """把文本截到字节上限内（按字符边界回退，避免出现半个字）"""
    raw = (text or "").encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore")


def target_lang(text: str) -> str:
    """按原文语言决定译文语言：含中文 → 英文，其它 → 简体中文。

    允许翻译中文时若仍把中文字面译成中文，结果等于没翻，所以中文译成英文。
    """
    from core.detector import has_chinese

    return "en" if has_chinese(text or "") else "zh-CHS"


def translate(text: str, source: str = None, to_lang: str = None) -> str:
    """按当前配置选择翻译源执行翻译。

    to_lang 为空时按原文语言自动决定（见 target_lang）。
    """
    src = (source or current_source()).lower()
    cfg = config.load()
    tgt = to_lang or target_lang(text)
    want_zh = tgt.lower().startswith("zh")
    text = _fit_bytes(text)      # 接口对单次文本有字节上限，超长先截到安全长度
    if src == "baidu":
        return translate_baidu(text, cfg.get("baidu_appid"),
                               cfg.get("baidu_secret"),
                               to_lang="zh" if want_zh else "en")
    if src == "google":
        return translate_google(text, cfg.get("google_apikey"),
                                target="zh-CN" if want_zh else "en")
    if src == "deepl":
        return translate_deepl(text, cfg.get("deepl_authkey"),
                               bool(cfg.get("deepl_free", True)),
                               target_lang="ZH" if want_zh else "EN")
    return translate_text(text, to_lang=tgt)


def test_connection(app_key: str = None, app_secret: str = None) -> str:
    """测试连接（有道）：返回成功提示或抛 TranslateError。"""
    cfg_key, cfg_secret = config.youdao_credentials()
    if not (app_key or cfg_key) or not (app_secret or cfg_secret):
        raise TranslateError(_NOT_CONFIGURED_MSG)
    out = translate_text("hello", app_key, app_secret)
    return out


def test_current() -> str:
    """测试当前所选翻译源是否可用：返回译文或抛 TranslateError。"""
    src = current_source()
    try:
        out = translate("hello", src)
    except TranslateError:
        raise
    except Exception as e:
        raise TranslateError(f"{SOURCES.get(src, src)}请求异常：{e}")
    if not out:
        raise TranslateError(f"{SOURCES.get(src, src)}返回空结果")
    return out
