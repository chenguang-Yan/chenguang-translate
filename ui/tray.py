# -*- coding: utf-8 -*-
"""系统托盘图标：打开设置主界面 / 退出"""
import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def make_icon() -> QIcon:
    """程序化生成一个简洁图标（蓝底“译”字），无需外部资源文件。
    同时用于托盘、窗口与弹窗。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#4a90d9"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor("#ffffff"))
    f = QFont("Microsoft YaHei")
    f.setBold(True)
    f.setPixelSize(34)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, open_settings, quit_app, help_app=None):
        from ui.appicon import app_icon
        super().__init__(app_icon())
        self.setToolTip(f"{config.APP_NAME}")
        menu = QMenu()
        act_open = QAction("打开设置", menu)
        act_open.triggered.connect(open_settings)
        menu.addAction(act_open)
        if callable(help_app):
            act_help = QAction("使用帮助", menu)
            act_help.triggered.connect(help_app)
            menu.addAction(act_help)
        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(quit_app)
        menu.addAction(act_quit)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._open_settings = open_settings

    def _on_activated(self, reason):
        # 左键单击（Trigger）或双击（DoubleClick）均打开设置界面
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                     QSystemTrayIcon.ActivationReason.DoubleClick):
            self._open_settings()
