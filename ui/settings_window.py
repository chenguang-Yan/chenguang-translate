# -*- coding: utf-8 -*-
"""主设置界面：参考有道词典设置面板（查询框 + 历史 + 勾选式选项）"""
import os

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QColor, QCursor, QFont, QIntValidator, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QListWidget, QListWidgetItem,
    QGroupBox, QGridLayout, QMessageBox, QFormLayout, QSizePolicy,
)

import config
from core import autostart, detector, translator
from ui.tray import make_icon
from ui.help_window import HelpWindow

STYLE = """
QMainWindow { background: #f4f7fb; border: 1px solid #d3dde8; }
#TitleBar { background: #ffffff; border-bottom: 1px solid #e3eaf2; }
#TitleText { font-size: 13px; font-weight: bold; color: #23303d; }
#Brand { font-size: 20px; font-weight: bold; color: #e0343c; }
#BrandSub { font-size: 20px; font-weight: bold; color: #333; }
#Copyright { font-size: 11px; color: #9aa7b4; }
#ConnWarn { color: #e0343c; font-size: 12px; }
#Hint { font-size: 11px; color: #8a97a5; }
QPushButton#WinBtn {
    background: transparent; border: none; color: #6b7c8d;
    font-size: 14px; padding: 0; border-radius: 4px;
}
QPushButton#WinBtn:hover { background: #eaf0f7; color: #23303d; }
QPushButton#WinBtn#WinClose:hover { background: #e0343c; color: #fff; }
QGroupBox {
    font-weight: bold; color: #4a90d9; border: 1px solid #dde5ee;
    border-radius: 8px; margin-top: 12px; background: #fff;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit {
    background: #fff; border: 1px solid #c9d4e0; border-radius: 6px; padding: 4px 8px;
}
QLineEdit:focus { border-color: #4a90d9; }
/* 下拉框：高度贴近字体行高，右侧留出自绘箭头空间 */
QComboBox {
    background: #fff; border: 1px solid #c9d4e0; border-radius: 6px;
    padding: 1px 20px 1px 8px; min-height: 0;
}
QComboBox:hover { border-color: #8fb8e0; }
QComboBox:focus { border-color: #4a90d9; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView {
    background: #fff; border: 1px solid #c9d4e0; border-radius: 6px;
    selection-background-color: #e3f0ff; selection-color: #1f3a56;
    outline: none; padding: 2px;
}
QComboBox QAbstractItemView::item { min-height: 20px; padding: 2px 6px; }
QCheckBox { spacing: 6px; }
QPushButton { background: #4a90d9; color: #fff; border: none; border-radius: 6px; padding: 5px 14px; }
QPushButton:hover { background: #3d7fc4; }
QPushButton#QueryBtn { font-size: 14px; padding: 5px 20px; }
QPushButton#Retry {
    background: transparent; border: none; color: #4a90d9;
    font-size: 12px; padding: 0 2px; text-decoration: underline;
}
QPushButton#Retry:hover { color: #2f6fae; }
QPushButton#Ghost {
    background: #fff; color: #3f5a75; border: 1px solid #c9d4e0;
    padding: 4px 12px; font-size: 12px;
}
QPushButton#Ghost:hover { background: #eef4fb; border-color: #8fb8e0; }
QListWidget { background: #fff; border: 1px solid #dde5ee; border-radius: 6px; }
"""

HOTKEY_LABELS = {"f4": "F4", "f9": "F9", "ctrl": "Ctrl", "alt": "Alt", "ctrl+shift+t": "Ctrl+Shift+T"}
# 查询历史显示条数可选项；0 = 不存储查询历史
HISTORY_LIMITS = (0, 5, 10, 15, 30)
# 划词灵敏度：鼠标松开与按下之间的位移阈值（像素）。越小越容易触发
SENSITIVITY = (
    (1, "极宽松（几乎不动也触发）"),
    (2, "宽松（轻微拖动即触发）"),
    (4, "标准"),
    (10, "严格（明显拖动才触发）"),
)


class StyledComboBox(QComboBox):
    """自绘下拉箭头的下拉框：高度贴近字体行高，统一圆角风格"""

    def __init__(self, parent=None, width: int = 0):
        super().__init__(parent)
        # 高度 ≈ 字体行高 + 4px，避免比正文高出一截
        self.setFixedHeight(max(21, self.fontMetrics().height() + 4))
        if width:
            self.setFixedWidth(width)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#5A6B7C"))
        pen.setWidthF(1.6)
        p.setPen(pen)
        x = self.width() - 11
        y = self.height() // 2 - 2
        p.drawLine(x - 4, y, x, y + 4)
        p.drawLine(x, y + 4, x + 4, y)
        p.end()


class TitleBar(QWidget):
    """自定义标头：辰光 logo + 「划词翻译」，可拖动窗口，右侧帮助 / 最小化 / 关闭"""

    def __init__(self, title: str, window: QWidget, help_callback=None):
        super().__init__(window)
        self.setObjectName("TitleBar")
        self.setFixedHeight(38)
        self._window = window
        self._drag_pos = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(6)

        logo = QLabel()
        pix = QPixmap(config.resource_path(os.path.join("assets", "logo.png")))
        if not pix.isNull():
            # 高度 24px 等比缩放，透明底
            logo.setPixmap(pix.scaledToHeight(24, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("辰光")
            logo.setObjectName("Brand")
        lay.addWidget(logo)

        text = QLabel(title)
        text.setObjectName("TitleText")
        lay.addWidget(text)
        lay.addStretch(1)

        # 帮助入口（右上角）：点击打开使用帮助
        btn_help = QPushButton("?")
        btn_help.setObjectName("WinBtn")
        btn_help.setFixedSize(28, 28)
        btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_help.setToolTip("使用帮助")
        if callable(help_callback):
            btn_help.clicked.connect(help_callback)
        else:
            btn_help.hide()
        lay.addWidget(btn_help)

        btn_min = QPushButton("—")
        btn_min.setObjectName("WinBtn")
        btn_min.setFixedSize(28, 28)
        btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_min.setToolTip("最小化")
        btn_min.clicked.connect(self._window.showMinimized)
        lay.addWidget(btn_min)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("WinBtn")   # 同时用 WinClose 定位（见下方样式）
        btn_close.setProperty("class", "close")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("关闭（程序继续在后台运行）")
        btn_close.clicked.connect(self._window.close)
        lay.addWidget(btn_close)
        # 单独设置 objectName 会覆盖 WinBtn，故用样式类区分悬停红色
        btn_close.setStyleSheet(
            "QPushButton:hover{background:#e0343c;color:#fff;border-radius:4px;}")

    # 拖动窗口（无边框窗口需要自己实现）
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)


class SettingsWindow(QMainWindow):
    def __init__(self, query_callback=None):
        """
        query_callback: callable(text) — 主界面手动查词时回调（由 main 接管渲染弹窗）
        """
        super().__init__()
        self.query_callback = query_callback
        self._log_viewer = None
        self._help_window = None
        # 翻译源配置变动后延迟重测连通性（避免每敲一个字符就请求一次）
        self._recheck_timer = QTimer(self)
        self._recheck_timer.setSingleShot(True)
        self._recheck_timer.timeout.connect(self._on_recheck)
        # 无边框：标头由自定义 TitleBar 呈现（logo + 「划词翻译」）
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumWidth(460)
        self.setStyleSheet(STYLE)
        from ui.appicon import app_icon
        self.setWindowIcon(app_icon())
        self._build_ui()
        self._load_to_ui()

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(TitleBar(config.APP_NAME, self, help_callback=self.open_help))

        content = QWidget()
        outer.addWidget(content, 1)
        root = QVBoxLayout(content)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        query_row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("输入单词或短句，回车或点查询")
        self.query_edit.returnPressed.connect(self._on_query)
        self.query_btn = QPushButton("查询")
        self.query_btn.setObjectName("QueryBtn")
        self.query_btn.clicked.connect(self._on_query)
        query_row.addWidget(self.query_edit, 1)
        query_row.addWidget(self.query_btn)
        root.addLayout(query_row)

        # 查询历史
        root.addWidget(QLabel("查询历史"))
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(90)
        self.history_list.itemClicked.connect(self._on_history_click)
        root.addWidget(self.history_list)

        # 选项设置
        opt = QGroupBox("选项设置")
        grid = QGridLayout(opt)
        grid.setVerticalSpacing(8)
        r = 0

        # 划词翻译 + 右侧连接状态（红色，右对齐）
        row = QHBoxLayout()
        row.setSpacing(6)
        self.chk_auto = QCheckBox("划词翻译（选中后自动弹出）")
        row.addWidget(self.chk_auto)
        row.addStretch(1)
        self.btn_retry = QPushButton("重试")
        self.btn_retry.setObjectName("Retry")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.setToolTip("重新检测翻译接口")
        self.btn_retry.hide()
        self.btn_retry.clicked.connect(self._on_retry)
        row.addWidget(self.btn_retry)
        self.lbl_conn = QLabel("")
        self.lbl_conn.setObjectName("ConnWarn")
        self.lbl_conn.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_conn.setMaximumWidth(190)
        self.lbl_conn.hide()
        row.addWidget(self.lbl_conn)
        grid.addLayout(row, r, 0, 1, 2); r += 1

        row = QHBoxLayout()
        row.setSpacing(9)
        self.chk_hotkey = QCheckBox("快捷键取词（按下")
        row.addWidget(self.chk_hotkey)
        row.addSpacing(2)
        self.cmb_hotkey = StyledComboBox(width=96)
        for k, label in HOTKEY_LABELS.items():
            self.cmb_hotkey.addItem(label, k)
        row.addWidget(self.cmb_hotkey)
        row.addSpacing(2)
        row.addWidget(QLabel("键取词）"))
        row.addStretch(1)
        grid.addLayout(row, r, 0, 1, 2); r += 1

        self.chk_english = QCheckBox("仅翻译英文（中文内容只显示原文供复制）")
        self.chk_english.setToolTip(
            "勾选：划到中文等非英文内容时不翻译，但仍会弹窗显示原文并带复制按钮；\n"
            "取消勾选：中文也会翻译（译为英文）。\n"
            "无论哪种情况，只要选中了内容就会弹窗。")
        grid.addWidget(self.chk_english, r, 0, 1, 2); r += 1

        row = QHBoxLayout()
        row.setSpacing(9)
        self.chk_pron = QCheckBox("自动朗读")
        row.addWidget(self.chk_pron)
        row.addSpacing(2)
        self.cmb_accent = StyledComboBox(width=64)
        self.cmb_accent.addItem("美", "us")
        self.cmb_accent.addItem("英", "uk")
        row.addWidget(self.cmb_accent)
        row.addStretch(1)
        grid.addLayout(row, r, 0, 1, 2); r += 1

        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(QLabel("查询历史显示条数："))
        self.cmb_hist = StyledComboBox(width=68)
        for n in HISTORY_LIMITS:
            self.cmb_hist.addItem("不存储查询历史" if n == 0 else str(n), n)
        self.cmb_hist.setToolTip("0 表示不存储查询历史")
        row.addWidget(self.cmb_hist)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_history)
        row.addWidget(btn_clear)
        row.addStretch(1)
        grid.addLayout(row, r, 0, 1, 2); r += 1

        # 划词灵敏度（放在选项设置区域底部）
        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(QLabel("划词灵敏度："))
        self.cmb_sens = StyledComboBox(width=176)
        for value, label in SENSITIVITY:
            self.cmb_sens.addItem(label, value)
        self.cmb_sens.setToolTip(
            "鼠标划选时，松开位置与按下位置之间的位移阈值。\n"
            "若日志里出现「位移不足，未触发取词」，请改为「极宽松」或「宽松」；\n"
            "若单击空白处也会弹窗，请改为「严格」。")
        row.addWidget(self.cmb_sens)
        row.addStretch(1)
        grid.addLayout(row, r, 0, 1, 2); r += 1
        root.addWidget(opt)

        # 系统
        sys_g = QGroupBox("系统")
        sy = QVBoxLayout(sys_g)

        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(QLabel("弹窗自动关闭时间："))
        self.edit_auto_close = QLineEdit()
        self.edit_auto_close.setValidator(QIntValidator(0, 999, self.edit_auto_close))
        self.edit_auto_close.setFixedWidth(56)
        self.edit_auto_close.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_auto_close.setToolTip("0 表示不自动关闭")
        row.addWidget(self.edit_auto_close)
        row.addWidget(QLabel("秒"))
        row.addWidget(QLabel("（0 表示不自动关闭）"))
        row.addStretch(1)
        sy.addLayout(row)

        self.chk_tts_fallback = QCheckBox("短句朗读在线合成兜底（无音频时自动合成）")
        self.chk_tts_fallback.setToolTip(
            "有道在线发音只对已收录的短语有录音；开启后，短句无录音时改用微软神经语音合成朗读。")
        self.chk_tts_fallback.stateChanged.connect(lambda *_: self._save())
        sy.addWidget(self.chk_tts_fallback)
        self.chk_autostart = QCheckBox("开机自动启动")
        self.chk_autostart.stateChanged.connect(self._on_autostart)
        sy.addWidget(self.chk_autostart)
        self.chk_close_outside = QCheckBox("点击弹窗外部区域时关闭弹窗")
        self.chk_close_outside.stateChanged.connect(lambda *_: self._save())
        sy.addWidget(self.chk_close_outside)

        # 排查入口：内置日志窗口（避免用记事本打开 debug.log 时的重载干扰）
        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(QLabel("划词没反应时，可查看运行日志排查："))
        btn_log = QPushButton("查看运行日志")
        btn_log.setObjectName("Ghost")
        btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_log.clicked.connect(self.open_log)
        row.addWidget(btn_log)
        row.addStretch(1)
        sy.addLayout(row)
        root.addWidget(sys_g)

        # 翻译源（放在系统设置之后，最底部）
        root.addWidget(self._build_source_group())

        root.addStretch(1)

        # 底部版权标注
        copyright = QLabel("版权所有 © 辰光科技")
        copyright.setObjectName("Copyright")
        copyright.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(copyright)

    # ---------- 翻译源 ----------

    def _build_source_group(self) -> QGroupBox:
        box = QGroupBox("翻译源")
        lay = QVBoxLayout(box)
        lay.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(QLabel("翻译引擎："))
        self.cmb_source = StyledComboBox(width=140)
        for key, name in translator.SOURCES.items():
            self.cmb_source.addItem(name, key)
        self.cmb_source.setToolTip(
            "有道翻译已内置默认配置，直接使用；\n其他引擎需自行申请并填写对应的 API 信息。")
        row.addWidget(self.cmb_source)
        row.addStretch(1)
        lay.addLayout(row)

        self.src_panels = {}

        # 有道：内置配置
        p = QWidget()
        pl = QVBoxLayout(p)
        pl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("已内置默认配置，无需填写")
        lbl.setObjectName("Hint")
        pl.addWidget(lbl)
        self.src_panels["youdao"] = p
        lay.addWidget(p)

        # 百度翻译
        p = QWidget()
        fl = QFormLayout(p)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self.ed_baidu_appid = QLineEdit()
        self.ed_baidu_appid.setPlaceholderText("APP ID")
        self.ed_baidu_secret = QLineEdit()
        self.ed_baidu_secret.setPlaceholderText("密钥")
        fl.addRow("APP ID：", self.ed_baidu_appid)
        fl.addRow("密钥：", self.ed_baidu_secret)
        fl.addRow("", self._hint("在百度翻译开放平台 api.fanyi.baidu.com 申请开发者账号获取"))
        self.src_panels["baidu"] = p
        lay.addWidget(p)

        # 谷歌翻译
        p = QWidget()
        fl = QFormLayout(p)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self.ed_google_key = QLineEdit()
        self.ed_google_key.setPlaceholderText("API 密钥")
        fl.addRow("API 密钥：", self.ed_google_key)
        fl.addRow("", self._hint("在 Google Cloud 控制台启用 Cloud Translation API 后创建密钥"))
        self.src_panels["google"] = p
        lay.addWidget(p)

        # DeepL
        p = QWidget()
        fl = QFormLayout(p)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self.ed_deepl_key = QLineEdit()
        self.ed_deepl_key.setPlaceholderText("Authentication Key")
        self.cmb_deepl_plan = StyledComboBox(width=110)
        self.cmb_deepl_plan.addItem("免费版", True)
        self.cmb_deepl_plan.addItem("专业版", False)
        fl.addRow("Auth Key：", self.ed_deepl_key)
        plan_row = QHBoxLayout()
        plan_row.setSpacing(9)
        plan_row.addWidget(QLabel("套餐："))
        plan_row.addWidget(self.cmb_deepl_plan)
        plan_row.addStretch(1)
        fl.addRow("", self._wrap(plan_row))
        fl.addRow("", self._hint("在 DeepL API 控制台获取，免费版密钥通常以 :fx 结尾"))
        self.src_panels["deepl"] = p
        lay.addWidget(p)

        return box

    @staticmethod
    def _hint(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("Hint")
        lb.setWordWrap(True)
        return lb

    @staticmethod
    def _wrap(layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _sync_source_panel(self, *_):
        """只显示当前所选翻译源的配置项"""
        key = self.cmb_source.currentData()
        for k, panel in self.src_panels.items():
            panel.setVisible(k == key)

    def _source_signature(self) -> tuple:
        return (
            self.cmb_source.currentData(),
            self.ed_baidu_appid.text(),
            self.ed_baidu_secret.text(),
            self.ed_google_key.text(),
            self.ed_deepl_key.text(),
            self.cmb_deepl_plan.currentData(),
        )

    # ---------- 数据加载 / 保存（即时生效） ----------

    def _load_to_ui(self):
        cfg = config.load()
        self.chk_auto.setChecked(cfg["auto_translate"])
        self.chk_hotkey.setChecked(cfg["hotkey_enabled"])
        idx = self.cmb_hotkey.findData(cfg["hotkey"])
        self.cmb_hotkey.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_english.setChecked(cfg["english_only"])
        self.chk_pron.setChecked(cfg["auto_pronounce"])
        idx = self.cmb_accent.findData(cfg["pronounce_accent"])
        self.cmb_accent.setCurrentIndex(idx if idx >= 0 else 0)
        # 划词灵敏度：配置值不在候选内时回落到标准
        sidx = self.cmb_sens.findData(int(cfg.get("drag_threshold", 4) or 4))
        self.cmb_sens.setCurrentIndex(sidx if sidx >= 0 else self.cmb_sens.findData(4))
        # 历史条数：配置值不在候选内时回落到 5
        hidx = self.cmb_hist.findData(int(cfg.get("history_limit", 5)))
        self.cmb_hist.setCurrentIndex(hidx if hidx >= 0 else self.cmb_hist.findData(5))
        # 翻译源
        sidx = self.cmb_source.findData(cfg.get("translate_source", "youdao"))
        self.cmb_source.setCurrentIndex(sidx if sidx >= 0 else 0)
        self.ed_baidu_appid.setText(cfg.get("baidu_appid", "") or "")
        self.ed_baidu_secret.setText(cfg.get("baidu_secret", "") or "")
        self.ed_google_key.setText(cfg.get("google_apikey", "") or "")
        self.ed_deepl_key.setText(cfg.get("deepl_authkey", "") or "")
        didx = self.cmb_deepl_plan.findData(bool(cfg.get("deepl_free", True)))
        self.cmb_deepl_plan.setCurrentIndex(didx if didx >= 0 else 0)
        self._sync_source_panel()
        self._src_sig = self._source_signature()

        self.edit_auto_close.setText(str(int(cfg.get("auto_close_seconds", 0) or 0)))
        self.chk_tts_fallback.setChecked(cfg.get("tts_fallback", True))
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_close_outside.setChecked(cfg["close_on_outside_click"])
        self._refresh_history()
        self._sync_history_enabled()

        # 信号接在加载之后，避免初始化触发保存
        self.chk_auto.stateChanged.connect(lambda *_: self._save())
        self.chk_hotkey.stateChanged.connect(lambda *_: self._save())
        self.cmb_hotkey.currentIndexChanged.connect(lambda *_: self._save())
        self.chk_english.stateChanged.connect(lambda *_: self._save())
        self.chk_pron.stateChanged.connect(lambda *_: self._save())
        self.cmb_accent.currentIndexChanged.connect(lambda *_: self._save())
        self.cmb_sens.currentIndexChanged.connect(lambda *_: self._save())
        self.cmb_hist.currentIndexChanged.connect(self._on_hist_limit_changed)
        self.edit_auto_close.textChanged.connect(lambda *_: self._save())
        self.edit_auto_close.editingFinished.connect(self._normalize_auto_close)
        # 翻译源
        self.cmb_source.currentIndexChanged.connect(
            lambda *_: (self._sync_source_panel(), self._save()))
        self.ed_baidu_appid.textChanged.connect(lambda *_: self._save())
        self.ed_baidu_secret.textChanged.connect(lambda *_: self._save())
        self.ed_google_key.textChanged.connect(lambda *_: self._save())
        self.ed_deepl_key.textChanged.connect(lambda *_: self._save())
        self.cmb_deepl_plan.currentIndexChanged.connect(lambda *_: self._save())

    # ---------- 数值控件读取 ----------

    def _auto_close_value(self) -> int:
        """读取自动关闭秒数；空/非法按 0（不自动关闭）处理"""
        try:
            v = int((self.edit_auto_close.text() or "").strip())
        except ValueError:
            return 0
        return max(0, min(999, v))

    def _normalize_auto_close(self):
        """失焦时把输入框内容规整为规范数字"""
        v = self._auto_close_value()
        if self.edit_auto_close.text().strip() != str(v):
            self.edit_auto_close.setText(str(v))

    def _hist_limit_value(self) -> int:
        v = self.cmb_hist.currentData()
        return int(v) if v is not None else 5

    def _on_hist_limit_changed(self, *_):
        self._sync_history_enabled()
        self._save()
        self._refresh_history()

    def _sync_history_enabled(self):
        """0 = 不存储查询历史：历史列表与清空按钮置灰"""
        disabled = self._hist_limit_value() <= 0
        self.history_list.setEnabled(not disabled)
        self.history_list.setStyleSheet(
            "color:#9aa7b4;background:#f7f9fb;" if disabled else "")

    def _save(self):
        cfg = config.update(
            auto_translate=self.chk_auto.isChecked(),
            hotkey_enabled=self.chk_hotkey.isChecked(),
            hotkey=self.cmb_hotkey.currentData(),
            english_only=self.chk_english.isChecked(),
            drag_threshold=self.cmb_sens.currentData() or 4,
            auto_pronounce=self.chk_pron.isChecked(),
            pronounce_accent=self.cmb_accent.currentData(),
            tts_fallback=self.chk_tts_fallback.isChecked(),
            history_limit=self._hist_limit_value(),
            auto_close_seconds=self._auto_close_value(),
            close_on_outside_click=self.chk_close_outside.isChecked(),
            autostart=self.chk_autostart.isChecked(),
            translate_source=self.cmb_source.currentData() or "youdao",
            baidu_appid=self.ed_baidu_appid.text(),
            baidu_secret=self.ed_baidu_secret.text(),
            google_apikey=self.ed_google_key.text(),
            deepl_authkey=self.ed_deepl_key.text(),
            deepl_free=bool(self.cmb_deepl_plan.currentData()),
        )
        if hasattr(self, "on_config_changed") and callable(self.on_config_changed):
            self.on_config_changed(cfg)
        # 翻译源/凭据发生变化 → 延迟重新检测连通性
        sig = self._source_signature()
        if sig != getattr(self, "_src_sig", None):
            self._src_sig = sig
            self._recheck_timer.start(1200)

    def _on_autostart(self, *_):
        ok = autostart.set_enabled(self.chk_autostart.isChecked())
        if not ok:
            QMessageBox.warning(self, "提示", "开机自启动设置失败（注册表写入被拒绝）。")
        self._save()

    # ---------- 接口连通状态（红色，右对齐） ----------

    def set_connection_status(self, ok, msg: str = ""):
        """ok=True 连通（隐藏提示）；False 失败（红色）；None 检测中（灰色）"""
        if ok is None:
            self.lbl_conn.setStyleSheet("color:#8a97a5;font-size:12px;")
            self.lbl_conn.setText(msg or "正在检测接口…")
            self.lbl_conn.setToolTip("")
            self.lbl_conn.show()
            self.btn_retry.hide()
            return
        if ok:
            self.lbl_conn.clear()
            self.lbl_conn.setStyleSheet("")
            self.lbl_conn.setToolTip("")
            self.lbl_conn.hide()
            self.btn_retry.hide()
            return
        detail = msg or "接口连接失败"
        self.lbl_conn.setStyleSheet("")
        self.lbl_conn.setText("⚠ " + (detail if len(detail) <= 16 else detail[:15] + "…"))
        self.lbl_conn.setToolTip(detail)
        self.lbl_conn.show()
        self.btn_retry.show()

    def _on_retry(self):
        cb = getattr(self, "on_retry", None)
        if callable(cb):
            cb()

    def _on_recheck(self):
        """翻译源配置变动后自动重测连通性"""
        cb = getattr(self, "on_retry", None)
        if callable(cb):
            cb()

    # ---------- 运行日志窗口 ----------

    def open_log(self):
        if self._log_viewer is None:
            from ui.log_viewer import LogViewer

            self._log_viewer = LogViewer(self)
        self._log_viewer.show()
        self._log_viewer.raise_()
        self._log_viewer.activateWindow()

    def open_help(self):
        """打开使用帮助窗口（复用同一个实例）"""
        if self._help_window is None:
            self._help_window = HelpWindow(self)
        self._help_window.show_help()

    # ---------- 查询与历史 ----------

    def _on_query(self):
        text = detector.normalize(self.query_edit.text())
        if text and self.query_callback:
            self.query_callback(text)

    def _on_history_click(self, item: QListWidgetItem):
        text = item.text()
        self.query_edit.setText(text)
        if self.query_callback:
            self.query_callback(text)

    def refresh_history(self):
        self._refresh_history()

    def _refresh_history(self):
        self.history_list.clear()
        if self._hist_limit_value() <= 0:
            hint = QListWidgetItem("（已关闭：不存储查询历史）")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.addItem(hint)
            return
        for h in config.load_history():
            self.history_list.addItem(QListWidgetItem(h["text"]))

    def _clear_history(self):
        config.clear_history()
        self._refresh_history()

    # ---------- 关闭=隐藏，后台常驻 ----------

    def closeEvent(self, event):
        event.ignore()
        self.hide()
