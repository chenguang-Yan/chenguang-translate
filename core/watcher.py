# -*- coding: utf-8 -*-
"""全局监听：鼠标划选/双击 + 快捷键取词。
通过 Qt 信号把捕获结果安全地投递到 GUI 线程。"""
import threading
import time

from pynput import mouse
from PyQt6.QtCore import QObject, pyqtSignal

import config
from core import grabber

DRAG_THRESHOLD = 4          # 默认拖动像素阈值（可在设置里按灵敏度调整）
CAPTURE_DELAY = 0.30        # 松手后等待目标应用完成选区（Electron 应用如 Typora 稍慢）
CAPTURE_RETRY_DELAY = 0.22  # 首次取词为空时，稍等再试一次（部分应用复制响应较慢）


def _double_click_window() -> float:
    """双击判定窗口：系统双击间隔 ×1.6 + 0.15s。

    只按系统值（默认 500ms）判定会漏掉"稍慢的双击"——很多人双击间隔在 0.6~0.9s
    之间，这种情况必须仍然算双击，否则表现就是"划词没反应"。
    """
    base = 0.5
    try:
        import ctypes

        ms = ctypes.windll.user32.GetDoubleClickTime()
        if 200 <= ms <= 1000:
            base = ms / 1000.0
    except Exception:
        pass
    return min(max(base, 0.4) * 1.6 + 0.15, 1.2)


DOUBLE_CLICK_WINDOW = _double_click_window()
DOUBLE_CLICK_SLOP = 12      # 两次点击允许的位置偏差（像素）


def _shift_down() -> bool:
    """Shift 是否按下（Shift+点击扩展选区时鼠标几乎不动，需要单独触发）"""
    try:
        import keyboard

        return bool(keyboard.is_pressed("shift"))
    except Exception:
        return False

HOTKEY_CHOICES = ["f4", "f9", "ctrl", "alt", "ctrl+shift+t"]


def _foreground_title() -> str:
    """获取当前前台窗口标题（用于调试日志）"""
    try:
        import ctypes

        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


class SignalBridge(QObject):
    """跨线程信号桥：监听线程 → GUI 线程"""
    textCaptured = pyqtSignal(str, int, int)   # 文本, 光标x, 光标y
    outsideClicked = pyqtSignal(int, int, float)  # 弹窗外点击(x, y, 点击时间戳)
    hotkeyTriggered = pyqtSignal(int, int)     # 热键触发取词
    escapePressed = pyqtSignal()               # Esc（兜底关闭弹窗）


class Watcher:
    def __init__(self, bridge: SignalBridge, own_window_hit=None):
        """
        own_window_hit: callable(x, y) -> bool，判断坐标是否落在本程序自己的窗口内
                        （弹窗/设置窗口内的事件要忽略，防自触发）
        """
        self.bridge = bridge
        self.own_window_hit = own_window_hit or (lambda x, y: False)
        self._mouse_listener = None
        self._hotkey_thread = None
        self._stop_hotkey = threading.Event()
        self._down_pos = None
        self._down_time = 0.0
        self._last_click_time = 0.0
        self._last_click_pos = (0, 0)
        # 取词流程可能耗时 1 秒以上（等应用响应复制）。这期间用户再划词会再起一个
        # 线程，两个线程抢剪贴板会互相覆盖标记（曾把标记当成单词弹窗），故串行化。
        self._capture_lock = threading.Lock()
        self._capture_pending = None

    # ---------- 生命周期 ----------

    def start(self):
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()
        self._restart_hotkey()

    def stop(self):
        if self._mouse_listener:
            self._mouse_listener.stop()
        self._stop_hotkey.set()

    # ---------- 配置热键（设置变更时重挂） ----------

    def restart_hotkey(self):
        self._restart_hotkey()

    def _restart_hotkey(self):
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._stop_hotkey.set()
        self._stop_hotkey = threading.Event()
        self._hotkey_thread = threading.Thread(
            target=self._hotkey_loop, args=(self._stop_hotkey,), daemon=True
        )
        self._hotkey_thread.start()

    # ---------- 鼠标监听 ----------

    def _on_click(self, x, y, button, pressed):
        if pressed:
            # 弹窗外的「任何」按下都要通知 GUI：左中右键都算，避免只用右键时关不掉
            self.bridge.outsideClicked.emit(int(x), int(y), time.time())
        if button != mouse.Button.left:
            return
        if self.own_window_hit(x, y):
            return  # 自己窗口内的点击不处理（弹窗内点击不关闭、不触发翻译）

        if pressed:
            self._down_pos = (x, y)
            self._down_time = time.time()
            now = time.time()
            # 双击 → 取词（双击本身即选词）；间隔按系统双击时间判定
            if now - self._last_click_time < DOUBLE_CLICK_WINDOW and \
               abs(x - self._last_click_pos[0]) < DOUBLE_CLICK_SLOP and \
               abs(y - self._last_click_pos[1]) < DOUBLE_CLICK_SLOP:
                self._schedule_capture(x, y)
            self._last_click_time = now
            self._last_click_pos = (x, y)
        else:
            down = self._down_pos
            self._down_pos = None
            if not down:
                return
            moved = abs(x - down[0]) + abs(y - down[1])
            threshold = self._threshold()
            # 只要拖动超过阈值就视为划选（不再要求按住时长，兼容快速拖选）
            if moved >= threshold:
                self._schedule_capture(x, y)
            elif _shift_down():
                # Shift+点击扩展选区：鼠标不位移，但选区已变化
                config.log_debug(f"Shift 点击（{moved}px），触发取词")
                self._schedule_capture(x, y)
            elif moved > 0:
                # 单击微抖：不取词，仅记录，便于排查「划词没反应」
                config.log_debug(f"位移不足({moved}px < 阈值{threshold}px)，未触发取词")

    def _threshold(self) -> int:
        """划词触发所需的鼠标位移阈值（设置里可调灵敏度）"""
        try:
            v = int(config.load().get("drag_threshold", DRAG_THRESHOLD))
        except (TypeError, ValueError):
            return DRAG_THRESHOLD
        return max(0, min(60, v))

    def _on_move(self, x, y):
        pass

    def _schedule_capture(self, x, y):
        cfg = config.load()
        if not cfg.get("auto_translate"):
            return  # 自动模式关闭时忽略
        t = threading.Timer(CAPTURE_DELAY, self._capture, args=(x, y))
        t.daemon = True
        t.start()

    def _capture(self, x, y):
        """取词入口：串行执行，避免两个线程抢剪贴板。"""
        if not self._capture_lock.acquire(blocking=False):
            # 正在取词：记下最后一次触发，等当前流程结束再补一次
            self._capture_pending = (x, y)
            config.log_debug("取词进行中，本次触发已排队")
            return
        try:
            self._do_capture(x, y)
        except Exception as e:  # 取词链路的任何异常都要留痕，不能静默
            config.log_debug(f"取词异常 {e.__class__.__name__}: {e}")
        finally:
            self._capture_lock.release()
            pending, self._capture_pending = self._capture_pending, None
            if pending:
                t = threading.Timer(0.12, self._capture, args=pending)
                t.daemon = True
                t.start()

    def _do_capture(self, x, y):
        cfg = config.load()
        title = _foreground_title()
        text = grabber.get_selected_text()
        if not text:
            # 部分应用（Electron/浏览器/WPS）复制响应较慢，稍后再试一次
            time.sleep(CAPTURE_RETRY_DELAY)
            text = grabber.get_selected_text()
        if not text:
            config.log_debug(
                f"取词为空 | 窗口={title!r} | 未选中可复制内容，或该窗口拦截了 Ctrl+Insert/Ctrl+C")
            return
        if len(text) > config.MAX_CAPTURE_LEN:
            config.log_debug(
                f"取词过长({len(text)} > {config.MAX_CAPTURE_LEN}) | 窗口={title!r}")
            return
        # 是否翻译统一由 main 判定（非英文也可能需要弹窗供复制）
        config.log_debug(f"取词成功 | 窗口={title!r} | {text[:40]!r}")
        self.bridge.textCaptured.emit(text, int(x), int(y))

    @staticmethod
    def _is_english(text: str) -> bool:
        from core.detector import is_english
        return is_english(text)

    # ---------- 快捷键监听 ----------

    def _hotkey_loop(self, stop_event: threading.Event):
        try:
            import keyboard
        except ImportError:
            return

        def on_hotkey():
            cfg = config.load()
            if not cfg.get("hotkey_enabled"):
                return
            # 用当前鼠标位置作为弹窗锚点
            try:
                pos = mouse.Controller().position
                x, y = int(pos[0]), int(pos[1])
            except Exception:
                x, y = 200, 200
            text = grabber.get_selected_text()
            if not text or len(text) > config.MAX_CAPTURE_LEN:
                return
            self.bridge.textCaptured.emit(text, x, y)

        mapping = {
            "f4": "f4",
            "f9": "f9",
            "ctrl": "ctrl+c",      # 借用 Ctrl+C：取词逻辑本身也模拟复制，直接捕获剪贴板
            "alt": "alt",
            "ctrl+shift+t": "ctrl+shift+t",
        }
        cfg = config.load()
        hk = mapping.get(cfg.get("hotkey", "f4"), "f4")

        handles = []
        if hk == "ctrl+c":
            # Ctrl+C 模式：监听用户主动复制动作，直接读取剪贴板
            def on_copy():
                if not config.load().get("hotkey_enabled"):
                    return
                time.sleep(0.15)
                try:
                    import pyperclip
                    text = pyperclip.paste() or ""
                except Exception:
                    return
                if not text.strip() or len(text) > config.MAX_CAPTURE_LEN:
                    return
                try:
                    pos = mouse.Controller().position
                    x, y = int(pos[0]), int(pos[1])
                except Exception:
                    x, y = 200, 200
                self.bridge.textCaptured.emit(text.strip(), x, y)

                handles.append(keyboard.add_hotkey("ctrl+c", on_copy, suppress=False))
        else:
            handles.append(keyboard.add_hotkey(hk, on_hotkey, suppress=False))
        # Esc 兜底：任何程序里按 Esc 都能关掉弹窗（suppress=False，不影响原按键）
        handles.append(keyboard.add_hotkey("esc", self._on_escape, suppress=False))

        # 等待停止事件
        while not stop_event.wait(0.2):
            pass
        for h in handles:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass

    def _on_escape(self):
        self.bridge.escapePressed.emit()
