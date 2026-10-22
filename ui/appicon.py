# -*- coding: utf-8 -*-
"""应用图标：优先使用 assets/app_icon.ico（AI 生成的划词翻译图标），
缺失时回退到程序化生成的「译」字图标（make_icon）。"""
from PyQt6.QtGui import QIcon

import config
from ui.tray import make_icon

_cached = None


def app_icon() -> QIcon:
    """全局统一的应用图标（托盘 / 设置窗口 / 弹窗共用）"""
    global _cached
    if _cached is not None:
        return _cached
    path = config.resource_path("assets/app_icon.ico")
    icon = QIcon(path)
    if icon.isNull():
        icon = make_icon()
    _cached = icon
    return icon
