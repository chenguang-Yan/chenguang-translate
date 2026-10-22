# -*- coding: utf-8 -*-
"""配置读写模块：config.json + history.json"""
import json
import os
import sys
import threading
import time

APP_NAME = "划词翻译"

# ============ 取词 / 翻译的长度上限 ============
# 取词上限：超出则不再处理。有道接口 q 上限 5000 字节，2000 字符留足余量，
# 足以覆盖淘宝联盟这类超长链接（实测 700~900 字符）。
# 此前这里写死 500，导致划超长链接「没反应」——内容被静默丢掉了。
MAX_CAPTURE_LEN = 2000

# ============ 翻译源凭据读取 ============
# 重要：真实凭据**不要写死进源码并提交到版本库**。有道凭据与其它翻译源一样，
# 统一存放在程序目录下的 config.json（与被忽略的百度/谷歌/DeepL 凭据同文件），
# 也可通过环境变量提供（优先级更高）。两者都为空时报「翻译源未配置」。
#
# config.json 中相关字段：
#   "youdao_app_key": "你的appKey",
#   "youdao_app_secret": "你的appSecret",
#   "baidu_appid": "...", "baidu_secret": "...", ...
#
# 注：config.json 位于程序所在目录（打包后即 exe 所在目录，如 dist\划词翻译\），
# 首次启动自动生成。

# ============ 翻译范围（划词时要翻译哪种语言的内容） ============
# 命中范围的文本会被送往翻译接口；未命中范围的文本**仍然弹窗**，
# 但只显示原文并保留复制按钮（见 ui/popup.py 的 show_plain）。
SCOPE_EN = "en"        # 仅翻译英文：只有纯英文内容才翻译
SCOPE_ZH = "zh"        # 仅翻译中文：只有含中文的内容才翻译
SCOPE_BOTH = "both"    # 中英文均翻译：含英文或中文都翻译

TRANSLATE_SCOPES = {
    SCOPE_EN: "仅翻译英文",
    SCOPE_ZH: "仅翻译中文",
    SCOPE_BOTH: "中英文均翻译",
}
DEFAULT_TRANSLATE_SCOPE = SCOPE_EN

# 未命中翻译范围时，浮窗里提示用户为什么没翻译
SCOPE_SKIP_NOTE = {
    SCOPE_EN: "已跳过翻译（当前仅翻译英文，内容非英文），可点标题右侧图标复制",
    SCOPE_ZH: "已跳过翻译（当前仅翻译中文，内容非中文），可点标题右侧图标复制",
    SCOPE_BOTH: "已跳过翻译（内容既非中文也非英文），可点标题右侧图标复制",
}


def skip_note(scope: str) -> str:
    """按当前翻译范围给出「为什么没翻译」的浮窗提示文案。"""
    return SCOPE_SKIP_NOTE.get(scope, SCOPE_SKIP_NOTE[DEFAULT_TRANSLATE_SCOPE])


def normalize_scope(value) -> str:
    """把任意取值规整为合法的三档之一，非法值回落到默认「仅翻译英文」。"""
    try:
        v = str(value or "").strip().lower()
    except Exception:
        v = ""
    return v if v in TRANSLATE_SCOPES else DEFAULT_TRANSLATE_SCOPE


YOUDAO_APP_KEY_ENV = "YOUDAO_APP_KEY"
YOUDAO_APP_SECRET_ENV = "YOUDAO_APP_SECRET"


def youdao_credentials() -> tuple:
    """按优先级取得有道凭据，返回 (app_key, app_secret)；未配置时返回 ("", "")。"""
    import os as _os

    # 1) 环境变量（优先级最高，便于 CI / 临时覆盖）
    key = (_os.environ.get(YOUDAO_APP_KEY_ENV) or "").strip()
    secret = (_os.environ.get(YOUDAO_APP_SECRET_ENV) or "").strip()
    if key and secret:
        return key, secret

    # 2) config.json（程序目录下的主配置文件）
    try:
        cfg = load()
        return ((cfg.get("youdao_app_key") or "").strip(),
                (cfg.get("youdao_app_secret") or "").strip())
    except Exception:
        return "", ""


def _app_dir() -> str:
    """定位程序数据目录：
    - 打包后（PyInstaller）：取 exe 所在目录，保证配置持久化在 exe 旁边
    - 开发态：取本文件所在目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")


def resource_path(rel: str) -> str:
    """定位打包内资源文件（assets 等）：
    - 打包后（PyInstaller onefile/onedir）：解包目录 sys._MEIPASS
    - 开发态：项目根目录
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

DEFAULT_CONFIG = {
    # 划词触发
    "auto_translate": True,        # ☑ 划词翻译（松手/双击自动）
    "hotkey_enabled": True,        # ☑ 快捷键取词
    "hotkey": "f4",                # 热键：f4 / ctrl / alt / f9 ...
    "translate_scope": DEFAULT_TRANSLATE_SCOPE,   # 翻译范围：仅翻译英文 / 仅翻译中文 / 中英文均翻译
    "drag_threshold": 4,           # 划词触发所需鼠标位移(px)：0-宽松/4-标准/10-严格
    "auto_pronounce": False,       # ☑ 自动朗读
    "pronounce_accent": "us",      # us / uk
    "tts_fallback": True,          # 在线发音无录音时用语音合成兜底（短句朗读）
    # 弹窗行为
    "close_on_outside_click": True,
    "close_on_esc": True,
    "close_on_focus_loss": True,
    "auto_close_seconds": 0,       # 弹窗自动关闭秒数，0=不自动关闭
    # 系统
    "autostart": False,            # 开机自启动
    "history_limit": 5,            # 查询历史显示条数
    # 翻译源：youdao（默认引擎）/ baidu / google / deepl
    "translate_source": "youdao",
    # 有道凭据（与其它翻译源凭据一同存放在本文件）
    # 也可通过环境变量 YOUDAO_APP_KEY/YOUDAO_APP_SECRET 提供，优先级更高；
    # 留空即「未配置」，可在设置界面「翻译源」中填写
    "youdao_app_key": "",
    "youdao_app_secret": "",
    "baidu_appid": "",             # 百度翻译开放平台 APP ID
    "baidu_secret": "",            # 百度翻译开放平台 密钥
    "google_apikey": "",           # Google Cloud Translation API Key
    "deepl_authkey": "",           # DeepL Authentication Key
    "deepl_free": True,            # DeepL 免费版(True) / 专业版(False)
}

_lock = threading.Lock()


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _migrate(raw: dict) -> dict:
    """旧版配置迁移：english_only（布尔）→ translate_scope（三档）。

    旧布尔语义："true" 只翻英文 → SCOPE_EN；取消勾选时所有内容都翻 → SCOPE_BOTH。
    """
    if not isinstance(raw, dict):
        return {}
    raw = dict(raw)
    if "translate_scope" not in raw and "english_only" in raw:
        raw["translate_scope"] = (SCOPE_EN if raw.get("english_only")
                                  else SCOPE_BOTH)
    raw.pop("english_only", None)
    if "translate_scope" in raw:
        raw["translate_scope"] = normalize_scope(raw.get("translate_scope"))
    return raw


def load() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        raw = {}
    return _deep_merge(dict(DEFAULT_CONFIG), _migrate(raw))


def save(cfg: dict) -> None:
    with _lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def update(**kwargs) -> dict:
    cfg = load()
    cfg.update(kwargs)
    save(cfg)
    return cfg


# ---------- 查询历史 ----------

def load_history() -> list:
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_history(text: str, limit: int = 5) -> list:
    """记录一条查询历史；limit<=0 表示不存储查询历史（并清空已有历史）"""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5
    if limit <= 0:
        clear_history()
        return []
    hist = [h for h in load_history() if h.get("text") != text]
    hist.insert(0, {"text": text})
    hist = hist[:limit]
    with _lock:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist


def clear_history() -> None:
    with _lock:
        try:
            os.remove(HISTORY_PATH)
        except FileNotFoundError:
            pass


# ---------- 调试日志（用于排查取词失败） ----------

DEBUG_LOG = os.path.join(APP_DIR, "debug.log")


def log_debug(msg: str) -> None:
    try:
        if os.path.exists(DEBUG_LOG) and os.path.getsize(DEBUG_LOG) > 200 * 1024:
            with open(DEBUG_LOG, "w", encoding="utf-8") as f:
                f.write("")
        ts = time.strftime("%H:%M:%S")
        with _lock:
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
