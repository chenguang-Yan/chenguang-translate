# -*- coding: utf-8 -*-
"""屏幕坐标换算与命中判定。

pynput（全局鼠标钩子）报告的是**物理像素**，而 Qt 的窗口几何（geometry /
frameGeometry）用的是**逻辑像素**。在 100% 缩放下两者相同，但 125% / 150% 缩放的
屏幕上会差一个系数。不做换算就会：
  - 弹窗定位偏出边界；
  - 「点击是否在弹窗内」判定失准 → 点击弹窗外有时关不掉。

这里提供 physical_to_logical()，遍历屏幕找到坐标所在的显示器再按比例换算。
"""
from PyQt6.QtCore import QPoint


def _screen_at_physical(x: float, y: float):
    """按物理像素定位所在屏幕；找不到时返回主屏"""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for s in app.screens():
        g = s.geometry()                      # 逻辑坐标
        ratio = s.devicePixelRatio() or 1.0
        x0, y0 = g.left() * ratio, g.top() * ratio
        x1, y1 = x0 + g.width() * ratio, y0 + g.height() * ratio
        if x0 <= x <= x1 and y0 <= y <= y1:
            return s
    return app.primaryScreen()


def physical_to_logical(x: float, y: float) -> QPoint:
    """物理像素 → Qt 逻辑像素"""
    try:
        s = _screen_at_physical(x, y)
        if s is None:
            return QPoint(int(x), int(y))
        ratio = s.devicePixelRatio() or 1.0
        return QPoint(int(round(x / ratio)), int(round(y / ratio)))
    except Exception:
        return QPoint(int(x), int(y))
