# -*- coding: utf-8 -*-
"""程序入口：串联 监听 → 取词 → 翻译 → 弹窗 / 设置界面 / 托盘"""
import os
import sys
import threading
import time
import traceback

from PyQt6.QtCore import (QCoreApplication, QLockFile, QObject, Qt,
                          QStandardPaths, pyqtSignal)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

import config
from core import detector
from core.detector import is_word, normalize
from core.screen import physical_to_logical
from core import translator
from core.watcher import SignalBridge, Watcher
from ui.popup import TranslationPopup
from ui.settings_window import SettingsWindow
from ui.tray import TrayIcon, make_icon


class AppController(QObject):
    """中央控制器：持有一个应用级单例的弹窗，管理取词→翻译流程"""

    # 后台线程 → GUI 线程：连通状态回传（ok=None 表示检测中）
    connStatusChanged = pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.popup = TranslationPopup()
        self.settings = SettingsWindow(query_callback=self.manual_query)
        self.settings.on_config_changed = self.on_config_changed
        self.settings.on_retry = self.check_connection_again
        self.tray = TrayIcon(self.open_settings, self.quit, help_app=self.open_help)
        self.connStatusChanged.connect(self._apply_conn_status)

        self.bridge = SignalBridge()
        self.bridge.textCaptured.connect(self.on_text_captured)
        self.bridge.outsideClicked.connect(self.on_outside_click)
        self.bridge.escapePressed.connect(self.on_escape)
        self.watcher = Watcher(self.bridge, own_window_hit=self._is_own_window)
        self.watcher.start()

        # 设置窗口关闭=隐藏，程序保持后台运行
        self.tray.show()
        self._start_ipc()

        # 启动即弹出设置窗口（让用户明确看到程序已运行），关闭后仍驻留托盘
        self.open_settings()
        self.tray.showMessage(
            config.APP_NAME, "已启动，正在后台运行。双击托盘图标可打开设置。",
            msecs=3000)

        # 启动后检测翻译源连通性，失败则在「划词翻译」右侧显示红色提示
        self._startup_connection_check()

    # ---------- 单实例 IPC：再次启动时唤起已有窗口 ----------

    def _start_ipc(self):
        """监听本地套接字，接收「另一个进程刚启动，请把窗口显示出来」的请求。"""
        self._ipc = QLocalServer(self)
        QLocalServer.removeServer(IPC_NAME)
        if not self._ipc.listen(IPC_NAME):
            config.log_debug(f"ipc: 监听失败 {self._ipc.errorString()}")
            return
        self._ipc.newConnection.connect(self._on_ipc_connection)

    def _on_ipc_connection(self):
        while self._ipc.hasPendingConnections():
            sock = self._ipc.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_ipc_data(s))
            sock.disconnected.connect(sock.deleteLater)

    def _on_ipc_data(self, sock):
        try:
            data = bytes(sock.readAll())
        except RuntimeError:
            return
        if b"show" in data:
            config.log_debug("ipc: 收到唤起请求 → 显示设置窗口")
            self.open_settings()

    # ---------- 翻译源连通检测 ----------

    def _startup_connection_check(self):
        """后台线程检测翻译源；结果通过信号回到 GUI 线程，显示在设置界面。"""
        self.connStatusChanged.emit(None, "正在检测接口…")

        def worker():
            src = translator.current_source()
            try:
                translator.test_current()
            except Exception as e:
                msg = str(e) or e.__class__.__name__
                config.log_debug(f"conn: 接口连通检测失败 [{src}] {msg}")
                # 未填写凭据属于「待配置」，按检测中（灰色）提示，不算连接失败
                if "未配置" in msg:
                    self.connStatusChanged.emit(None, "待填写翻译源配置")
                else:
                    self.connStatusChanged.emit(False, f"接口连接失败：{msg}")
            else:
                config.log_debug(f"conn: 接口连通检测通过 [{src}]")
                self.connStatusChanged.emit(True, "")

        threading.Timer(1.5, worker).start()

    def _apply_conn_status(self, ok, msg: str):
        """GUI 线程：把检测结果刷到设置界面的红色提示标签上。"""
        try:
            self.settings.set_connection_status(ok, msg)
        except RuntimeError:
            pass

    def check_connection_again(self):
        """供设置界面手动重试"""
        self._startup_connection_check()

    def _logical(self, x: float, y: float):
        """pynput 给的是物理像素，Qt 用逻辑像素 → 按显示器缩放换算"""
        return physical_to_logical(x, y)

    def _is_own_window(self, x: int, y: int) -> bool:
        """是否点在「本程序」的窗口上。

        用于 watcher 的防自触发：在自己窗口里拖选文本不应再触发一次取词
        （否则会把查询框里的选区当成划词结果）。
        """
        p = self._logical(x, y)
        for w in (self.popup, self.settings):
            if not w.isVisible():
                continue
            g = w.frameGeometry()
            # 外扩 2px，避免点在窗口边缘几个像素时被误判成外部
            if g.adjusted(-2, -2, 2, 2).contains(p):
                return True
        return False

    def _popup_hit(self, x: int, y: int) -> bool:
        """是否点在弹窗卡片上（只有弹窗内部才算「内部」）。

        注意这里不包含设置窗口：点在设置窗口上同样属于「非弹窗区域」，弹窗应关闭。
        """
        w = self.popup
        if not w.isVisible():
            return False
        p = self._logical(x, y)
        # 右键菜单常常超出弹窗范围（比如长菜单往下延伸），点在菜单上不算外部点击
        if w.swallows_click(p):
            return True
        return w.frameGeometry().adjusted(-2, -2, 2, 2).contains(p)

    # ---------- 取词结果 → 翻译 → 弹窗 ----------

    def on_text_captured(self, text: str, x: int, y: int):
        # GUI 线程里出现异常会被 Qt 静默吞掉（无控制台时用户只看到「没反应」），
        # 因此这里统一捕获并写入 debug.log，便于定位。
        try:
            text = normalize(text)
            if not text:
                config.log_debug("已取词但内容为空，跳过")
                return
            cfg = config.load()
            scope = config.normalize_scope(cfg.get("translate_scope"))
            # 规则：只要选中了内容就弹窗。
            # ① 链接：翻译它没有意义，弹原文 + 复制 + 打开按钮；
            # ② 不在「翻译范围」内的内容：不翻译，弹原文 + 复制（始终弹窗，方便复制）；
            # ③ 其余（命中范围）：正常翻译，按单词 / 短句分别渲染。
            if detector.is_url(text):
                config.log_debug(f"网址，只显示原文 | {text[:60]!r}")
                self.popup.show_plain(
                    text, x, y,
                    note="网址无需翻译，可复制或在浏览器中打开",
                    url=text)
                return
            if not detector.matches_scope(text, scope):
                config.log_debug(
                    f"非目标语言，弹原文供复制 | 范围={scope} | {text[:40]!r}")
                self.popup.show_plain(text, x, y, note=config.skip_note(scope))
                return
            config.add_history(text, cfg.get("history_limit", 5))
            if self.settings.isVisible():
                self.settings.refresh_history()
            if is_word(text):
                config.log_debug(f"弹窗触发(单词) | {text[:40]!r}")
                self.popup.show_word(text, x, y)
            else:
                config.log_debug(f"弹窗触发(短句) | {text[:40]!r}")
                self.popup.show_sentence(text, x, y)
        except Exception:
            config.log_debug("on_text_captured 异常：\n" + traceback.format_exc())

    def manual_query(self, text: str):
        """主界面手动查词：单词/短句统一走弹窗，显示在屏幕中央偏上"""
        screen = QApplication.primaryScreen().geometry()
        x = screen.center().x()
        y = screen.top() + int(screen.height() * 0.2)
        self.on_text_captured(text, x, y)

    # ---------- 弹窗外点击 → 关闭 ----------

    def on_outside_click(self, x: int, y: int, click_time: float = 0.0):
        try:
            cfg = config.load()
            if not cfg.get("close_on_outside_click"):
                return
            # 弹窗显示之前发生的点击（取词/翻译期间排队的旧事件）不该关掉新弹窗
            shown_at = getattr(self.popup, "shown_at", 0.0)
            if click_time and click_time < shown_at:
                config.log_debug(
                    f"ui: 忽略弹窗显示前的旧点击({click_time:.3f} < {shown_at:.3f})")
                return
            if self.popup.isVisible() and not self._popup_hit(x, y):
                config.log_debug(f"ui: 点击弹窗外部({x},{y}) → 关闭")
                self.popup.hide()
        except Exception:
            config.log_debug("on_outside_click 异常：\n" + traceback.format_exc())

    def on_escape(self):
        """Esc 兜底：万一鼠标事件没被捕捉到，按 Esc 也能关掉弹窗"""
        try:
            cfg = config.load()
            if cfg.get("close_on_esc", True) and self.popup.isVisible():
                config.log_debug("ui: Esc → 关闭弹窗")
                self.popup.hide()
        except Exception:
            config.log_debug("on_escape 异常：\n" + traceback.format_exc())

    # ---------- 设置变更 → 即时生效 ----------

    def on_config_changed(self, cfg: dict):
        self.cfg = cfg
        # 热键可能变更 → 重挂
        self.watcher.restart_hotkey()

    # ---------- 打开设置 / 退出 ----------

    def open_settings(self):
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def open_help(self):
        self.settings.open_help()

    def quit(self):
        self.watcher.stop()
        self.tray.hide()
        qapp = QApplication.instance()
        if qapp:
            qapp.quit()


_MUTEX_NAME = "Local\\ChenguangTranslate-SingleInstance-{6F1C9A2E-2B44-4B7E-9E9C-1F5B6E0A7D31}"
_ERROR_ALREADY_EXISTS = 183
IPC_NAME = "chenguang-translate-ipc"
_NOTIFY_SOCK = None      # 保活：避免唤起请求还没发完套接字就被回收


def _notify_running_instance() -> bool:
    """把「唤起窗口」请求发给正在运行的实例；没人在监听则返回 False。"""
    global _NOTIFY_SOCK
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(b"show")
    sock.flush()
    sock.waitForBytesWritten(400)
    # 套接字对象一旦被销毁，Qt 还没推完的写缓冲会被丢；这里保活并转几圈事件循环
    _NOTIFY_SOCK = sock
    deadline = time.time() + 0.5
    while sock.bytesToWrite() > 0 and time.time() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    time.sleep(0.08)
    return True


class SingleInstance:
    """单实例守卫。

    Windows 下用「命名互斥体」：进程结束（含被强杀）时内核自动回收，
    不会像锁文件那样留下残留锁被误判成「已过期」而让第二个实例抢进。
    其它平台退回 QLockFile。
    """

    def __init__(self):
        self._mutex = None
        self._lockfile = None

    # ---- 获取 ----

    def acquire(self) -> bool:
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                k32 = ctypes.WinDLL("kernel32", use_last_error=True)
                create = k32.CreateMutexW
                create.restype = wintypes.HANDLE
                create.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                   wintypes.LPCWSTR)
                handle = create(None, True, _MUTEX_NAME)
                err = ctypes.get_last_error()
                if not handle:
                    config.log_debug(f"单实例：创建互斥体失败 err={err}")
                    return True          # 拿不到互斥体时不要挡住用户
                if err == _ERROR_ALREADY_EXISTS:
                    k32.CloseHandle(handle)
                    return False
                self._mutex = handle
                return True
            except Exception:
                config.log_debug("单实例：互斥体异常，退回锁文件\n"
                                 + traceback.format_exc())

        tmp = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.TempLocation) or (
            os.environ.get("TEMP") or os.environ.get("TMP") or ".")
        self._lockfile = QLockFile(os.path.join(tmp, "chenguang_translate.lock"))
        return self._lockfile.tryLock(100)

    # ---- 释放（正常退出时可调，进程结束时系统也会自动回收）----

    def release(self):
        if self._mutex is not None:
            try:
                import ctypes
                ctypes.WinDLL("kernel32").CloseHandle(self._mutex)
            except Exception:
                pass
            self._mutex = None
        if self._lockfile is not None:
            self._lockfile.unlock()
            self._lockfile = None


def main():
    # 高分屏适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭设置窗口不退出（后台常驻）
    from ui.appicon import app_icon
    app.setWindowIcon(app_icon())
    app.setApplicationName(config.APP_NAME)

    # 单实例：已有进程在跑时提示并退出，避免托盘出现多个图标、热键冲突
    guard = SingleInstance()
    if not guard.acquire():
        # 已经有实例在跑：优先把它唤到前台，连不上再弹提示
        if _notify_running_instance():
            config.log_debug("启动被拒绝：已唤起运行中的实例")
            return 0
        config.log_debug("启动被拒绝：已有实例在运行")
        box = QMessageBox()
        box.setWindowTitle(config.APP_NAME)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("程序已经在运行中")
        box.setInformativeText(
            "请查看系统托盘中的「划词翻译」图标。\n"
            "如果找不到图标，请在任务管理器中结束「划词翻译」进程后再启动。")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
        return 0

    controller = AppController()
    # 抑制未使用告警
    _ = controller
    code = app.exec()
    guard.release()
    return code


if __name__ == "__main__":
    sys.exit(main())
