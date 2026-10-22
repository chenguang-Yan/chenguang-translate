# -*- coding: utf-8 -*-
"""程序内矢量小图标：复制 / 全选，以及带悬停反馈的复制按钮。

不依赖外部图片资源，全部用 QPainter 绘制，任意 DPI 下都清晰。
"""
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QPushButton


def _new_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def copy_pixmap(color: str = "#4A5F73", size: int = 16) -> QPixmap:
    """两张纸叠放的「复制」图标：前面完整纸张 + 后面纸张的右上两条边"""
    pm = _new_pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.1, size / 12.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    # 后面的纸（只画上边与右边，露出层叠感）
    p.drawLine(int(s * 0.34), int(s * 0.16), int(s * 0.72), int(s * 0.16))
    p.drawLine(int(s * 0.72), int(s * 0.16), int(s * 0.72), int(s * 0.50))
    # 前面的纸
    p.drawRoundedRect(
        QRectF(s * 0.14, s * 0.30, s * 0.54, s * 0.56), s * 0.10, s * 0.10)
    p.end()
    return pm


def select_all_pixmap(color: str = "#4A5F73", size: int = 16) -> QPixmap:
    """虚线选框 + 四角控点的「全选」图标"""
    pm = _new_pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.0, size / 14.0))
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72), s * 0.10, s * 0.10)
    # 四角控点
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    d = max(1.6, s * 0.115)
    for fx, fy in ((0.14, 0.14), (0.86, 0.14), (0.14, 0.86), (0.86, 0.86)):
        p.drawRect(QRectF(s * fx - d / 2, s * fy - d / 2, d, d))
    p.end()
    return pm


def check_pixmap(color: str = "#28A36A", size: int = 16) -> QPixmap:
    """对勾（复制成功反馈）"""
    pm = _new_pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.6, size / 7.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = float(size)
    p.drawLine(int(s * 0.20), int(s * 0.54), int(s * 0.42), int(s * 0.76))
    p.drawLine(int(s * 0.42), int(s * 0.76), int(s * 0.80), int(s * 0.26))
    p.end()
    return pm


def menu_icon(pix_factory, color: str = "#3F5566", grey: str = "#B4BCC4", size: int = 16) -> QIcon:
    """生成带禁用态灰化的菜单图标"""
    icon = QIcon()
    icon.addPixmap(pix_factory(color, size), QIcon.Mode.Normal)
    icon.addPixmap(pix_factory(grey, size), QIcon.Mode.Disabled)
    return icon


class CopyButton(QPushButton):
    """小号复制按钮：点击把文本写入剪贴板，短暂显示对勾反馈"""

    def __init__(self, text_provider, tooltip: str = "复制", size: int = 20, parent=None):
        super().__init__(parent)
        self._provider = text_provider          # callable -> str
        self._pix_idle = copy_pixmap("#5E86AA", 14)
        self._pix_done = check_pixmap("#28A36A", 14)
        self._pix = self._pix_idle
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet(
            "QPushButton { border: none; background: transparent; border-radius: 4px; }"
            "QPushButton:hover { background: #D3E6FA; }"
            "QPushButton:pressed { background: #BFD9F5; }")
        self.clicked.connect(self._do_copy)

    def _do_copy(self):
        text = ""
        try:
            text = self._provider() or ""
        except Exception:
            text = ""
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._pix = self._pix_done
        self.setToolTip("已复制")
        self.update()
        QTimer.singleShot(1200, self._restore)

    def _restore(self):
        self._pix = self._pix_idle
        self.setToolTip("复制")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        x = (self.width() - self._pix.width()) // 2
        y = (self.height() - self._pix.height()) // 2
        p.drawPixmap(x, y, self._pix)
        p.end()
