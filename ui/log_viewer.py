# -*- coding: utf-8 -*-
"""内置运行日志查看器（只读窗口，自动跟随刷新）。

为什么不让用户用记事本打开 debug.log：
记事本会监视文件修改，程序每写一行日志它就提示/重新加载，重载后当前选区消失
——在记事本里划词时 Ctrl+C 自然取不到内容，于是"划词没反应"看起来像程序缺陷。
用这个内置窗口读取，互不干扰，选区也不会被打断。
"""
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

import config
from ui.tray import make_icon

MAX_CHARS = 200_000

STYLE = """
QDialog { background: #f4f7fb; }
QPlainTextEdit {
    background: #fff; border: 1px solid #dde5ee; border-radius: 6px;
    color: #24333f; padding: 6px;
}
QPushButton {
    background: #4a90d9; color: #fff; border: none;
    border-radius: 5px; padding: 4px 12px;
}
QPushButton:hover { background: #3d7fc4; }
QPushButton#Ghost {
    background: #fff; color: #3f5a75; border: 1px solid #c9d4e0;
}
QPushButton#Ghost:hover { background: #eef4fb; border-color: #8fb8e0; }
QCheckBox { color: #3f5a75; }
"""


class LogViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} - 运行日志")
        from ui.appicon import app_icon
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.resize(780, 540)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_path = QLabel(os.path.basename(config.DEBUG_LOG))
        self.lbl_path.setStyleSheet("color:#5d7285;font-size:12px;")
        self.lbl_path.setToolTip(config.DEBUG_LOG)
        top.addWidget(self.lbl_path)
        top.addStretch(1)

        self.chk_auto = QCheckBox("自动刷新")
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(self._on_auto_toggled)
        top.addWidget(self.chk_auto)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setObjectName("Ghost")
        btn_refresh.clicked.connect(self.reload)
        top.addWidget(btn_refresh)

        btn_open = QPushButton("打开所在文件夹")
        btn_open.setObjectName("Ghost")
        btn_open.clicked.connect(self._open_folder)
        top.addWidget(btn_open)

        btn_clear = QPushButton("清空日志")
        btn_clear.setObjectName("Ghost")
        btn_clear.clicked.connect(self._clear)
        top.addWidget(btn_clear)
        lay.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text.setFont(font)
        lay.addWidget(self.text, 1)

        self.hint = QLabel("提示：查看日志请用本窗口，不要用记事本直接打开 debug.log —— "
                           "记事本会因日志更新而重载，从而中断你正在划选的文本。")
        self.hint.setStyleSheet("color:#8a97a5;font-size:11px;")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.reload)
        self._timer.start()

        self.reload()

    # ---------- 行为 ----------

    def reload(self):
        try:
            with open(config.DEBUG_LOG, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()[-MAX_CHARS:]
        except FileNotFoundError:
            data = "（暂无日志：还没有取词记录）"
        except Exception as e:
            data = f"（读取日志失败：{e}）"

        if self.text.toPlainText() == data:
            return
        bar = self.text.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.text.setPlainText(data)
        if at_bottom:
            bar.setValue(bar.maximum())
        self.lbl_path.setText(
            f"{os.path.basename(config.DEBUG_LOG)}　{len(data.splitlines())} 行")

    def _on_auto_toggled(self, *_):
        if self.chk_auto.isChecked():
            self._timer.start()
            self.reload()
        else:
            self._timer.stop()

    def _open_folder(self):
        try:
            os.startfile(os.path.dirname(config.DEBUG_LOG))  # noqa: S606
        except Exception:
            pass

    def _clear(self):
        try:
            with open(config.DEBUG_LOG, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
        self.text.clear()
        self.reload()
