# -*- coding: utf-8 -*-
"""剪贴板取词：模拟 Ctrl+Insert / Ctrl+C 读取选中文本，随后还原剪贴板。

三条关键约定（都是踩过坑之后加的）：

1. **标记 + 回读校验**：先往剪贴板写唯一标记，立刻回读确认写入成功；写入失败就
   直接放弃本次取词——否则会读到上一次的旧剪贴板内容，把它当成划词结果。
2. **标记内容一律判失败**：结果里出现 ``CG_MARK_`` 说明是并发取词时另一个线程
   写入的标记，绝不能当成划出的文字（曾出现把标记当单词弹窗的 bug）。
3. **全进程串行化**：同一时刻只允许一个取词流程。鼠标划词与快捷键取词分别跑在
   不同线程，并发时会互相覆盖标记。

按键策略：先用 Ctrl+Insert（几乎所有编辑器/浏览器都支持，且没有副作用），
失败再用 Ctrl+C；但前台是控制台窗口时不发 Ctrl+C——那会中断正在运行的命令。
"""
import threading
import time
import uuid

import pyperclip
from pynput.keyboard import Controller, Key

_kb = Controller()
_LOCK = threading.Lock()

MARK_PREFIX = "CG_MARK_"      # 纯 ASCII，避免被输入法/剪贴板规范化改掉
POLL_INTERVAL = 0.02
POLL_QUICK = 0.18             # Ctrl+Insert 的快速探测窗口
POLL_TIMEOUT = 0.50           # 补发 Ctrl+C 后 / 控制台窗口的等待上限
RETRY = 2
CLIP_TRIES = 3                # 剪贴板被占用时的重试次数

# 控制台类窗口：Ctrl+C 会中断前台进程，只允许用 Ctrl+Insert
_TERMINAL_CLASSES = {
    "consolewindowclass",              # conhost（cmd / powershell）
    "cascadia_hosting_window_class",   # Windows Terminal
    "mintty", "putty", "windowsterminal",
}


def _clip_get() -> str:
    for _ in range(CLIP_TRIES):
        try:
            return pyperclip.paste() or ""
        except Exception:
            time.sleep(0.02)
    return ""


def _clip_set(text: str) -> bool:
    for _ in range(CLIP_TRIES):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(0.02)
    return False


def _foreground_class() -> str:
    try:
        import ctypes

        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        return (buf.value or "").strip().lower()
    except Exception:
        return ""


def _send_copy(use_insert: bool) -> None:
    """发送复制键：Ctrl+Insert 或 Ctrl+C"""
    key = Key.insert if use_insert else "c"
    try:
        _kb.press(Key.ctrl)
        time.sleep(0.01)
        _kb.press(key)
        time.sleep(0.01)
        _kb.release(key)
        time.sleep(0.01)
        _kb.release(Key.ctrl)
    except Exception:
        pass


def _wait_clipboard_change(mark: str, timeout: float) -> str:
    """轮询剪贴板直到内容不再是标记；超时返回空串"""
    text = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        text = _clip_get()
        if text and text != mark:
            return text
    return ""


def get_selected_text() -> str:
    """模拟复制键抓取当前应用中的选中文本；无选中/失败返回 ''。

    注意：会丢失原剪贴板中的非文本内容（图片等），文本内容会还原。
    """
    if not _LOCK.acquire(timeout=0.05):
        # 另一个线程正在取词，本次直接放弃，避免互相污染标记
        return ""
    try:
        previous = _clip_get()
        is_terminal = _foreground_class() in _TERMINAL_CLASSES

        for attempt in range(RETRY):
            mark = MARK_PREFIX + uuid.uuid4().hex
            if not _clip_set(mark) or _clip_get() != mark:
                # 剪贴板被别的程序占用，不能继续——否则会把旧内容当结果
                return ""

            if is_terminal:
                # 控制台里绝不发 Ctrl+C（会中断正在运行的命令）
                _send_copy(True)
                text = _wait_clipboard_change(mark, POLL_TIMEOUT + 0.05)
            else:
                # 先 Ctrl+Insert：兼容面广且没有副作用，响应快就省掉补发
                _send_copy(True)
                text = _wait_clipboard_change(mark, POLL_QUICK)
                if not text:
                    # 部分应用（Qt / Java / 少数编辑器）不认 Ctrl+Insert
                    _send_copy(False)
                    text = _wait_clipboard_change(mark, POLL_TIMEOUT)

            if text and MARK_PREFIX not in text:
                _clip_set(previous)
                return text.strip()

            if attempt + 1 < RETRY:
                time.sleep(0.10)

        _clip_set(previous)
        return ""
    finally:
        _LOCK.release()
