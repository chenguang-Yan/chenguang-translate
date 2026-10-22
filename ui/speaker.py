# -*- coding: utf-8 -*-
"""自绘扬声器按钮。

原来弹窗里用的是 🔊/🔉/🔇 emoji：不同系统渲染差异大，有的偏彩色、有的缺字，
跟浅蓝卡片风格也不统一。这里改用 QPainter 画一个简洁的喇叭矢量图标，
并支持 正常 / 加载中 / 播放中 / 失败 四种状态。
"""
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton

# 逻辑坐标系固定为 24×24，绘制时按控件实际尺寸缩放
_SPEAKER = (
    (3.0, 9.6), (7.6, 9.6), (12.2, 5.0), (12.2, 19.0), (7.6, 14.5), (3.0, 14.5),
)
_WAVE_CX, _WAVE_CY = 13.6, 12.0     # 声波圆心


class SpeakerButton(QPushButton):
    """简洁的扬声器图标按钮"""

    STATE_IDLE = 0
    STATE_LOADING = 1
    STATE_PLAYING = 2
    STATE_FAIL = 3

    _COLOR = {
        STATE_IDLE: "#5B7B99",
        STATE_LOADING: "#9FB6C9",
        STATE_PLAYING: "#1B6FC4",
        STATE_FAIL: "#D9534F",
    }
    _COLOR_HOVER = "#2B6396"
    _HOVER_BG = "#D8EAFC"

    def __init__(self, parent=None, size: int = 22, tooltip: str = "点击朗读"):
        super().__init__(parent)
        self.setObjectName("Play")
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.base_tooltip = tooltip
        self._state = self.STATE_IDLE
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._tick)

    # ---------- 状态 ----------

    def state(self) -> int:
        return self._state

    def set_state(self, state: int, tooltip: str = None):
        self._state = state
        if state == self.STATE_PLAYING:
            self._phase = 0
            self._timer.start()
        else:
            self._timer.stop()
        if tooltip is not None:
            self.setToolTip(tooltip)
        self.update()

    def reset(self):
        """恢复到初始外观"""
        self.set_state(self.STATE_IDLE, self.base_tooltip)

    def _tick(self):
        self._phase = (self._phase + 1) % 3
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)

        hovered = self.underMouse() and self.isEnabled()
        if hovered and self._state != self.STATE_PLAYING:
            p.setBrush(QColor(self._HOVER_BG))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)

        s = min(self.width(), self.height()) / 24.0
        base = QColor(self._COLOR.get(self._state, self._COLOR[self.STATE_IDLE]))
        if hovered and self._state in (self.STATE_IDLE, self.STATE_FAIL):
            base = QColor(self._COLOR_HOVER)
        if not self.isEnabled():
            base = QColor("#B7C6D3")

        # 喇叭主体
        path = QPainterPath()
        for i, (x, y) in enumerate(_SPEAKER):
            px, py = x * s, y * s
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        p.setBrush(QBrush(base))
        p.drawPath(path)

        pen = QPen()
        pen.setWidthF(max(1.0, 1.5 * s))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self._state == self.STATE_FAIL:
            # 失败：喇叭右侧一道斜杠
            pen.setColor(base)
            p.setPen(pen)
            p.drawLine(QPointF(15.4 * s, 8.6 * s), QPointF(21.0 * s, 15.4 * s))
            p.end()
            return

        # 声波：两条圆弧，播放时由内向外扩散
        inner_a, outer_a = self._wave_alphas()
        for radius, alpha, a0, span in (
            (3.1, inner_a, -56, 112),
            (6.1, outer_a, -48, 96),
        ):
            if alpha <= 0:
                continue
            c = QColor(base)
            c.setAlpha(alpha)
            pen.setColor(c)
            p.setPen(pen)
            d = 2 * radius * s
            p.drawArc(
                QRectF((_WAVE_CX - radius) * s, (_WAVE_CY - radius) * s, d, d),
                int(a0 * 16), int(span * 16),
        )
        p.end()

    def _wave_alphas(self):
        if self._state == self.STATE_PLAYING:
            return ((255, 90), (190, 200), (90, 255))[self._phase % 3]
        if self._state == self.STATE_LOADING:
            return (150, 55)
        return (215, 120)       # 静态：内浓外淡
