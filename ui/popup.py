# -*- coding: utf-8 -*-
"""翻译浮窗：浅蓝圆角卡片，单词视图（音标/发音/基本翻译/网络释义）、短句视图（基本翻译）"""
import threading
import time
import traceback

from PyQt6.QtCore import Qt, QPoint, QUrl, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import (QColor, QFontMetrics, QKeySequence, QPixmap,
                         QTextDocument, QDesktopServices)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QApplication, QScrollArea, QGraphicsDropShadowEffect, QMenu,
)

import config
from core import translator, detector, audio
from core.screen import physical_to_logical
from core.translator import TranslateError
from ui.speaker import SpeakerButton
from ui.icons import CopyButton, copy_pixmap, select_all_pixmap, menu_icon
from ui.tray import make_icon

CARD_W = 372
MARGIN = 14
CARD_MAX_H = 440        # 内容超出该高度时弹窗内部滚动
MENU_CLICK_GRACE = 0.6  # 菜单关闭后仍把「点在其区域内」视为内部点击的宽限秒数
TITLE_MAX_WIDTH = 310   # 标题列最大像素宽（超过则折为两行，再超出截断）
AUTO_PRONOUNCE_MAX_LEN = 120   # 自动朗读的句子长度上限（超出则接口基本无法合成）


def _title_display(text, font, max_w):
    """返回 (显示文本, 是否单行)：让标题在 max_w 像素宽度内最多占两行。

    - 一行放得下 → (原文, True)：调用方按文字像素宽定宽、关掉换行；
    - 需要两行   → (原文或截断文本, False)：调用方开换行、宽度固定为 max_w。

    两行高度的判断直接用 QLabel 同款的 QTextDocument 排版引擎量，比字体
    度量估算准（换行点、字距等因素只有真实排版才知道）。
    """
    fm = QFontMetrics(font)
    if fm.horizontalAdvance(text) <= max_w:
        return text, True           # 一行就能放下

    from PyQt6.QtGui import QTextOption
    doc = QTextDocument()
    doc.setDefaultFont(font)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opt)
    doc.setTextWidth(max_w)

    def height(s: str) -> float:
        doc.setPlainText(s)
        return doc.size().height()

    # 行高不能用 QFontMetrics.height()（不含行距），要用文档实测行高，
    # 否则两行的内容会被误判超限、全部截成一行
    height("测")
    line_h = height("测测")

    if height(text) <= 2 * line_h + 1:
        return text, False          # 正好两行放得下，不截断
    lo, hi, best = 1, len(text), "…"
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + "…"
        if height(cand) <= 2 * line_h + 1:
            best, lo = cand, mid + 1
        else:
            hi = mid - 1
    return best, False


def _selection_contains(label: "QLabel", pos) -> bool:
    """判断 pos（标签内坐标）是否落在标签当前选中的文字上。

    QLabel 没有直接提供「某点是否选中」的接口，这里用同样字体/宽度重建
    文本布局做命中测试，再与选区范围比较。
    """
    sel = label.selectedText()
    start = label.selectionStart()
    if not sel or start < 0:
        return False
    try:
        doc = QTextDocument(label.text())
        doc.setDefaultFont(label.font())
        # 不换行的标签不能给文档设宽度，否则会误判换行位置
        if label.wordWrap():
            doc.setTextWidth(max(1, label.width() - 2 * label.margin()))
        else:
            doc.setTextWidth(-1)
        lay = doc.documentLayout()
        hit = lay.hitTest(pos, Qt.HitTestAccuracy.ExactHit)
        if hit < 0:
            # 精确命中会落在字间缝隙（比如行首上方几个像素），此时退回模糊命中，
            # 但要先确认这个点确实在文本区域内，否则点击空白也算命中了
            w = doc.textWidth() if doc.textWidth() > 0 else doc.idealWidth()
            if not (0 <= pos.x() <= w and 0 <= pos.y() <= doc.size().height()):
                return False
            hit = lay.hitTest(pos, Qt.HitTestAccuracy.FuzzyHit)
    except Exception:      # 命中测试失败时按「不在选区内」处理
        return False
    if hit < 0:
        return False
    return start <= hit < start + len(sel)


STYLE = """
#Card {
    background: #EAF4FF;
    border: 1px solid #C4DCF5;
    border-radius: 14px;
}
QLabel { background: transparent; }
#Title { font-size: 15px; font-weight: bold; color: #1F3A56; }
#Brand { font-size: 13px; font-weight: bold; color: #1F3A56; }
#Section { font-size: 12px; font-weight: bold; color: #3A78B8; }
#Accent { font-size: 12px; color: #5A6B7C; }
#Phone { font-size: 13px; color: #33506B; }
#Meaning { font-size: 13px; color: #23303D; }
#WebKey { font-size: 12px; color: #3A78B8; }
#WebValue { font-size: 12px; color: #3E4C5A; }
#Error { font-size: 13px; color: #C0392B; }
/* 选中文字的高亮：弹窗平时不激活，调色板的 Inactive 高亮几乎看不出来，
   这里统一指定明显的选中底色/字色 */
QLabel {
    selection-background-color: #2F7BF6;
    selection-color: #FFFFFF;
}
QFrame#HLine { background: #D3E4F5; border: none; }
/* 发音按钮完全自绘（矢量喇叭），不显示文字 */
QPushButton#Play { border: none; background: transparent; padding: 0; }
QPushButton#Close {
    border: none;
    background: transparent;
    color: #7092B4;
    font-size: 16px;
    font-weight: bold;
    padding: 0;
}
QPushButton#Close:hover { color: #D9534F; }
QScrollArea { background: transparent; border: none; }
"""

# 右键菜单：参考 Windows 11 桌面右击菜单（浅色、圆角、宽松内边距）
MENU_STYLE = """
QMenu {
    background: #FDFDFD;
    border: 1px solid #E2E2E2;
    border-radius: 8px;
    padding: 5px;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 12px;
    color: #1B1B1B;
}
QMenu::item {
    padding: 6px 26px;
    border-radius: 5px;
    margin: 0 2px;
}
QMenu::item:selected { background: #EFEFEF; color: #1B1B1B; }
QMenu::item:disabled { color: #A0A0A0; background: transparent; }
QMenu::separator { height: 1px; background: #E8E8E8; margin: 4px 10px; }
"""


class _ContextMenu(QMenu):
    """右键菜单：自己处理 Ctrl+C / Ctrl+A。

    Qt 在弹出菜单里不会把快捷键派发给 QAction（QAction.shortcut 只负责显示），
    所以这里直接拦截按键，保证提示的快捷键真的能用。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.copy_action = None
        self.select_all_action = None
        # 手动触发时记下被激活的动作：QMenu.exec() 只会返回「菜单内部激活」的
        # 动作，我们自己 trigger() 的不会被它捕获，所以要用这个字段补回来。
        self.activated_by_key = None

    def _fire(self, action):
        self.activated_by_key = action
        action.trigger()
        self.close()

    def keyPressEvent(self, event):
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl and key == Qt.Key.Key_C and self.copy_action:
            if self.copy_action.isEnabled():
                self._fire(self.copy_action)
            self.close()
            return
        if ctrl and key == Qt.Key.Key_A and self.select_all_action:
            if self.select_all_action.isEnabled():
                self._fire(self.select_all_action)
            self.close()
            return
        super().keyPressEvent(event)


class TranslationPopup(QWidget):
    """单例浮窗，由 AppController 控制显示"""

    # 后台线程准备完音频后回传 GUI 线程：(本地路径, 按钮, 提示语)
    _audioReady = pyqtSignal(object)
    # 后台线程完成翻译后回传 GUI 线程：(请求号, 类型, 数据, x, y)
    _queryReady = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # 不抢焦点：弹窗出现后用户仍可继续输入/复制，Ctrl+C 不受影响
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setStyleSheet(STYLE)
        self.setFixedWidth(CARD_W + MARGIN * 2)
        from ui.appicon import app_icon
        self.setWindowIcon(app_icon())

        # 圆角卡片 + 投影
        self._card = QFrame(self)
        self._card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(40, 80, 130, 60))
        self._card.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        outer.addWidget(self._card)

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 0)

        # 顶部品牌行（独立一行，不随内容滚动）：横版 logo + 「划词翻译」 + 关闭按钮
        header = QWidget(self._card)
        header.setStyleSheet("background: transparent;")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(14, 10, 10, 2)
        hlay.setSpacing(8)
        # 先建字样，「划词翻译」再按它的行高缩放 logo，两者行高保持一致
        brand = QLabel("划词翻译")
        brand.setObjectName("Brand")
        brand.setToolTip("辰光 · 划词翻译")
        brand.setParent(header)      # 先挂到卡片内，才能拿到 #Brand 的字体
        brand.ensurePolished()
        line_h = max(12, brand.fontMetrics().height())
        self._logo_pix = QPixmap(config.resource_path("assets/logo_h.png"))
        if not self._logo_pix.isNull():
            self._logo_pix = self._logo_pix.scaledToHeight(
                line_h, Qt.TransformationMode.SmoothTransformation)
            logo = QLabel()
            logo.setPixmap(self._logo_pix)
            logo.setFixedSize(self._logo_pix.size())
            hlay.addWidget(logo)
        hlay.addWidget(brand)
        hlay.addStretch(1)

        self._btn_close = QPushButton("✕")
        self._btn_close.setObjectName("Close")
        self._btn_close.setFixedSize(22, 22)
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.setToolTip("关闭")
        self._btn_close.clicked.connect(self.hide)
        hlay.addWidget(self._btn_close)
        self._header = header
        card_lay.addWidget(header)

        self._scroll = QScrollArea(self._card)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:transparent;margin:2px;}"
            "QScrollBar::handle:vertical{background:#B9D4EF;border-radius:3px;min-height:24px;}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical{background:transparent;}")
        card_lay.addWidget(self._scroll)

        # 发音播放器（在 GUI 线程创建）
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(1.0)
        self._player.setAudioOutput(self._audio_out)
        self._player.errorOccurred.connect(self._on_media_error)
        self._last_audio_path = None
        self._last_audio_btn = None
        self._play_btn = None
        self._play_note = ""

        self._audioReady.connect(self._on_audio_ready)
        self._queryReady.connect(self._on_query_ready)
        self._req_id = 0
        self.shown_at = 0.0

        # 自动关闭定时器
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.hide)
        self._last_menu_close = (0.0, None)   # 右键菜单关闭的时刻与当时的几何
        self._filter_installed = False        # 应用级事件过滤器是否已挂上

        # 预取 #Title 的字体：标题宽度要用字体度量自己算（见 _title）
        probe = QLabel("测")
        probe.setObjectName("Title")
        probe.setParent(self)        # 必须先挂到弹窗下，ensurePolished 才能吃到样式
        probe.ensurePolished()
        self._title_font = probe.font()
        # 从弹窗上摘下来，避免残留在界面上、也避免混进 findChildren(QLabel) 的扫描
        probe.setParent(None)
        probe.hide()
        probe.deleteLater()

    # ---------- 公共接口 ----------

    def show_word(self, word: str, x: int, y: int):
        """立即显示「正在查询…」，翻译在后台线程完成，避免阻塞 GUI 线程。

        阻塞式查询会让这段时间内的鼠标点击排在事件队列里，等弹窗一显示就被
        那条旧的「弹窗外点击」立刻关掉——表现为「划词后没弹窗」。
        """
        self._req_id += 1
        req = self._req_id
        self._show_loading(word, x, y, "正在查询…")
        threading.Thread(target=self._fetch_word, args=(req, word, x, y), daemon=True).start()

    def _fetch_word(self, req: int, word: str, x: int, y: int):
        """后台线程：词典详情 + 基本翻译"""
        try:
            info = translator.lookup_word(word)
        except Exception as e:
            config.log_debug(f"popup: 词典查询异常 {e}")
            info = {"uk": None, "us": None, "basic": [], "web": []}
        try:
            basic_txt = translator.translate(word)
        except TranslateError as e:
            self._queryReady.emit((req, "error", str(e), x, y))
            return
        except Exception as e:
            self._queryReady.emit((req, "error", f"翻译失败：{e}", x, y))
            return
        self._queryReady.emit((req, "word", (word, info, basic_txt), x, y))

    def show_sentence(self, text: str, x: int, y: int):
        self._req_id += 1
        req = self._req_id
        norm = detector.normalize(text)
        self._show_loading(norm, x, y, "正在翻译…")
        threading.Thread(
            target=self._fetch_sentence, args=(req, text, norm, x, y), daemon=True).start()

    def _fetch_sentence(self, req: int, text: str, norm: str, x: int, y: int):
        try:
            result = translator.translate(text)
        except TranslateError as e:
            self._queryReady.emit((req, "error", str(e), x, y))
            return
        except Exception as e:
            self._queryReady.emit((req, "error", f"翻译失败：{e}", x, y))
            return
        self._queryReady.emit((req, "sentence", (text, norm, result), x, y))

    def _on_query_ready(self, payload):
        """GUI 线程：后台查询完成，渲染结果。"""
        req, kind, data, x, y = payload
        if req != self._req_id:
            config.log_debug("popup: 丢弃过期查询结果")
            return
        if not self.isVisible():
            # 用户已把加载中的弹窗关掉/点走，不再强弹
            config.log_debug("popup: 弹窗已关闭，丢弃查询结果")
            return
        if kind == "error":
            self._render_error(data, x, y)
            return
        if kind == "word":
            word, info, basic_txt = data
            self._render_word(word, info, basic_txt, x, y)
            self._maybe_auto_pronounce(word, info)
        else:
            text, norm, result = data
            self._render_sentence(text, result, x, y)
            # 自动朗读只针对英文：优先读英文原文；原文不是英文（例如中文译成
            # 英文）时改读英文译文，避免开着自动朗读却没声音。
            has_english = any(c.isascii() and c.isalpha() for c in norm)
            target = ""
            if has_english and len(norm) <= AUTO_PRONOUNCE_MAX_LEN:
                target = norm
            else:
                speak = self._speakable(result)
                if speak and len(speak) <= AUTO_PRONOUNCE_MAX_LEN:
                    target = speak
            if target:
                accent = config.load().get("pronounce_accent", "us")
                self._maybe_auto_pronounce(target,
                                           urls=self._candidates(target, accent))

    def show_error(self, msg: str, x: int, y: int):
        self._render_error(msg, x, y)

    # ---------- 渲染 ----------

    def _show_loading(self, title: str, x: int, y: int, hint: str = ""):
        norm = detector.normalize(title)
        def build(lay):
            self._title(lay, norm or "…", copy_text=norm)
            if hint:
                lay.addWidget(self._label(hint, "Accent"))
        self._build(build, x, y)

    def _pron_row(self, text: str, tip: str, leading: str = "朗读") -> QHBoxLayout:
        """一行朗读控件：「朗读 英 🔊 美 🔊」，两种口音各一个按钮。

        dictvoice 对部分文本只有单一口音，_candidates 已带备用地址兜底。
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._label(leading, "Accent"))
        for accent, name in (("uk", "英"), ("us", "美")):
            row.addWidget(self._label(name, "Accent"))
            row.addWidget(self._make_play_btn(
                f"{tip}（{name}音）", self._candidates(text, accent), text, accent))
            row.addSpacing(10)
        row.addStretch(1)
        return row

    def _section_row(self, title: str, speak: str = None,
                     tip: str = "朗读译文") -> QHBoxLayout:
        """「基本翻译」标题行；speak 非空时在其右侧挂英/美朗读按钮。"""
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._label(title, "Section"))
        if speak:
            row.addSpacing(12)
            row.addWidget(self._label("朗读", "Accent"))
            for accent, name in (("uk", "英"), ("us", "美")):
                row.addWidget(self._label(name, "Accent"))
                row.addWidget(self._make_play_btn(
                    f"{tip}（{name}音）", self._candidates(speak, accent),
                    speak, accent))
                row.addSpacing(8)
        row.addStretch(1)
        return row

    @staticmethod
    def _speakable(text: str) -> str:
        """译文是否值得朗读：纯英文（不含中文）才返回待朗读的文本，否则返回空串"""
        flat = detector.normalize(text)
        if flat and detector.is_english(flat):
            return flat
        return ""

    def _render_word(self, word: str, info: dict, basic_txt: str, x: int, y: int):
        # 词典无释义时接口译文兜底；这段译文若是英文，同样给朗读
        speak_result = self._speakable(basic_txt or "")

        def build(lay):
            self._title(lay, word, copy_text=word)

            # 发音行：英 [音标] 🔊    美 [音标] 🔊  （音标在喇叭图标之前）
            pron_row = QHBoxLayout()
            pron_row.setSpacing(6)
            for accent, name in (("uk", "英"), ("us", "美")):
                item = info.get(accent) or {}
                phone = item.get("phone") or ""
                pron_row.addWidget(self._label(name, "Accent"))
                if phone:
                    pron_row.addWidget(self._label(f"[{phone}]", "Phone"))
                urls = self._candidates(word, accent, (item or {}).get("speech"))
                pron_row.addWidget(
                    self._make_play_btn(f"播放{name}音", urls, word, accent))
                pron_row.addSpacing(10)
            pron_row.addStretch(1)
            lay.addLayout(pron_row)
            self._hline(lay)

            # 基本翻译（词典释义优先，接口译文兜底）
            lay.addLayout(self._section_row("基本翻译", speak_result))
            basics = info.get("basic") or []
            if basics:
                for line in basics:
                    lay.addWidget(self._label(line, "Meaning", True))
            else:
                for line in basic_txt.splitlines():
                    lay.addWidget(self._label(line, "Meaning", True))

            # 网络释义
            web = info.get("web") or []
            if web:
                self._hline(lay)
                lay.addWidget(self._label("网络释义", "Section"))
                for key, val in web:
                    lay.addWidget(self._label(key, "WebKey"))
                    lay.addWidget(self._label(val, "WebValue", True))

        self._build(build, x, y)

    def _render_sentence(self, src: str, result: str, x: int, y: int):
        text = detector.normalize(src)
        # 纯中文内容没有「朗读」的意义（发音接口只支持英文），隐藏朗读行
        has_english = any(c.isascii() and c.isalpha() for c in text)

        # 译文是英文时也要能朗读（例如中文译成英文的场景）
        speak_result = self._speakable(result)

        def build(lay):
            self._title(lay, text, copy_text=text)
            if has_english:
                # 整句朗读：英 🔊  美 🔊（无音标），任一口音缺失时自动用另一口音
                lay.addLayout(self._pron_row(text, "朗读整句"))
                self._hline(lay)
            lay.addLayout(self._section_row("基本翻译", speak_result))
            for line in result.splitlines():
                lay.addWidget(self._label(line, "Meaning", True))

        self._build(build, x, y)

    def _render_error(self, msg: str, x: int, y: int):
        def build(lay):
            lay.addWidget(self._label("提示", "Section"))
            lay.addWidget(self._label(msg, "Error", True))
        self._build(build, x, y)

    def show_plain(self, text: str, x: int, y: int, note: str = None,
                   url: str = None):
        """只显示原文、不翻译，保留复制按钮方便取用。

        - 不在「翻译范围」内的内容（如设为仅翻译英文却划到中文）：
          默认提示「已跳过翻译（当前仅翻译英文，内容非英文）」，
          也可由调用方传入更贴合当前设置的 note（见 config.skip_note）；
        - 超长内容/链接：调用方可传 note 覆盖提示文案，传 url 则额外给「打开链接」。
        """
        norm = detector.normalize(text)
        self._req_id += 1          # 作废仍在路上的查询结果，避免稍后覆盖本视图

        def build(lay):
            self._title(lay, norm or "…", copy_text=norm)
            self._hline(lay)
            tip = note or config.skip_note("en")
            lay.addWidget(self._label(tip, "Accent", True))
            if url:
                row = QHBoxLayout()
                row.setSpacing(6)
                row.setContentsMargins(0, 2, 0, 0)
                btn = QPushButton("在浏览器中打开")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    "QPushButton { background:#2F7BF6; color:#FFFFFF; border:none;"
                    " border-radius:6px; padding:5px 10px; font-size:12px; }"
                    "QPushButton:hover { background:#1F66DC; }")
                btn.clicked.connect(lambda: self._open_url(url))
                row.addWidget(btn)
                row.addStretch(1)
                lay.addLayout(row)

        self._plain_mode = True
        self._build(build, x, y, plain=True)

    @staticmethod
    def _open_url(url: str):
        """用系统默认浏览器打开链接"""
        try:
            QDesktopServices.openUrl(QUrl(url))
            config.log_debug(f"打开链接 | {url[:60]}")
        except Exception:
            config.log_debug("打开链接失败：\n" + traceback.format_exc())

    # ---------- 构建辅助 ----------

    def _build(self, builder, x: int, y: int, plain: bool = False):
        # plain=True 表示当前是「只显示原文」的免翻译视图
        self._plain_mode = plain
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 8, 16, 14)
        lay.setSpacing(7)
        builder(lay)
        lay.addStretch(1)
        self._scroll.setWidget(content)
        # 高度自适应：wordWrap 标签的 sizeHint 偏大，不能直接用，
        # 按「内容实际宽度」重算真实高度（超过上限才出滚动条）
        vw = CARD_W - 8          # 预留竖向滚动条宽度，避免触发后再变高
        if content.hasHeightForWidth():
            h = content.heightForWidth(vw)
        else:
            h = content.sizeHint().height()
        scroll_h = min(h + 2, CARD_MAX_H)
        self._scroll.setFixedHeight(scroll_h)
        # 顶层窗口的 adjustSize() 在这里不生效（布局惰性 + 窗口已显示），
        # 直接按「品牌行 + 内容区 + 阴影留白」算出目标高度并固定
        self.setFixedHeight(self._header.sizeHint().height() + scroll_h + MARGIN * 2)
        self._move_near(x, y)
        # 先记录显示时间：万一后续步骤抛异常，时间戳也不会停在旧值上，
        # 否则之后的每次点击都会被「忽略旧点击」的保护逻辑挡掉。
        self.shown_at = time.time()
        self.show()
        self.raise_()
        # 注意：不调用 activateWindow()，避免抢焦点影响原窗口的复制/输入
        self._restart_auto_close()

    # ---------- 右上角关闭 / 自动关闭 ----------

    def eventFilter(self, obj, event):
        # 右键菜单打开期间在应用层兜底拦截 Ctrl+C / Ctrl+A：
        # 弹窗平时不抢焦点，按键有时根本到不了菜单（菜单自身的 keyPressEvent
        # 只在菜单拿到键盘时才有效），这里保证无论落在哪个控件上都能全选/复制
        ctx = getattr(self, "_menu_ctx", None)
        if ctx is not None and event.type() == QEvent.Type.KeyPress:
            menu, act_copy, act_all = ctx
            key = event.key()
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if ctrl and key == Qt.Key.Key_C and act_copy.isEnabled():
                menu._fire(act_copy)
                return True
            if ctrl and key == Qt.Key.Key_A and act_all.isEnabled():
                menu._fire(act_all)
                return True
        if (event.type() == QEvent.Type.MouseButtonPress
                and self._is_inside(obj)):
            self._handle_press_clear(obj, event)
        return super().eventFilter(obj, event)

    def _handle_press_clear(self, obj, event):
        """决定是否清空选区。

        注意：同一个鼠标按下会被 Qt 依次派发给「最深层控件 → 各级父控件」。
        如果每层都判断一次，第一层是标签（判定保留）、后面几层是卡片/弹窗
        （判定清空），选区就被后面几层清掉了。所以只让**最深层**那个控件处理：
        若当前控件下面还压着子控件，就交给更深层去处理。
        """
        if isinstance(obj, QWidget) and obj.childAt(event.position().toPoint()):
            return
        # 例外：右键落在「选中的文字上」要保留选中，否则右键菜单里「复制」是灰的
        if (event.button() == Qt.MouseButton.RightButton
                and isinstance(obj, QLabel)
                and _selection_contains(obj, event.position())):
            return
        self.clear_selection()

    def _is_inside(self, obj) -> bool:
        """控件是否是弹窗自身或它的子控件。

        右键菜单要排除：它虽以弹窗为父控件，但点菜单项是去执行复制/全选，
        不能当成「弹窗内的点击」把选区清掉（否则菜单里的复制等于失效）。
        """
        if not isinstance(obj, QWidget) or isinstance(obj, QMenu):
            return False
        if obj is self:
            return True
        return self.isAncestorOf(obj) and not obj.isWindow()

    def clear_selection(self):
        """取消弹窗内所有标签的文字选中"""
        for lb in self.findChildren(QLabel):
            if lb.hasSelectedText():
                lb.setSelection(0, 0)

    def _restart_auto_close(self):
        """按配置的秒数启动/停止自动关闭（0 = 不自动关闭）"""
        self._auto_timer.stop()
        try:
            secs = int(config.load().get("auto_close_seconds", 0) or 0)
        except (TypeError, ValueError):
            secs = 0
        if secs > 0:
            self._auto_timer.start(secs * 1000)

    def showEvent(self, event):
        super().showEvent(event)
        # 弹窗可见期间常驻应用级事件过滤器：右键菜单的快捷键拦截 +
        # 「点非选中区域取消选中」都靠它
        if not self._filter_installed:
            QApplication.instance().installEventFilter(self)
            self._filter_installed = True

    def hideEvent(self, event):
        self._auto_timer.stop()
        if self._filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._filter_installed = False
        super().hideEvent(event)

    def _title(self, lay, text: str, copy_text: str = None):
        """标题行：划译内容（+ 复制按钮，紧跟在内容后面）。

        品牌 logo / 「划词翻译」字样 / 关闭按钮已上移到独立的顶部品牌行。
        宽度完全自己算（QFontMetrics 量像素 + setFixedWidth），绝不依赖
        QLabel wordWrap 的 sizeHint——那个值不可靠，是「标题被挤成细长条、
        复制按钮悬空」这类排版问题的根源。
        """
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)

        copy_src = copy_text if copy_text is not None else text
        max_w = TITLE_MAX_WIDTH                     # 标题列可用的最大像素宽

        disp, single_line = _title_display(text, self._title_font, max_w)
        title = self._label(text, "Title", True)
        if disp != text:
            title.setToolTip(text)
            title.setText(disp)
        if single_line:
            # 一行放得下：关掉换行、宽度按文字实际像素固定，保证永远一行
            title.setWordWrap(False)
            title.setFixedWidth(QFontMetrics(self._title_font)
                                .horizontalAdvance(disp) + 8)
            title_stretch = 0
        else:
            # 需要两行：开换行、宽度固定为上限，按钮固定右上
            title.setWordWrap(True)
            title.setFixedWidth(max_w)
            title_stretch = 1

        row.addWidget(title, title_stretch, Qt.AlignmentFlag.AlignTop)
        if copy_src:
            btn = CopyButton(lambda t=copy_src: t, "复制划译内容", 20)
            row.addSpacing(5)
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        if title_stretch == 0:
            row.addStretch(1)
        lay.addLayout(row)

    def _label(self, text: str, obj: str = "Meaning", wrap: bool = False) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName(obj)
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lb.customContextMenuRequested.connect(
            lambda pos, w=lb: self._show_text_menu(w, pos))
        if wrap:
            lb.setWordWrap(True)
        return lb

    def _build_text_menu(self, label: QLabel):
        """构造右键菜单（便于测试）：复制（未选中时禁用）/ 全选，带图标与快捷键提示"""
        menu = _ContextMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        selection = label.selectedText() or ""
        full = label.text() or ""

        act_copy = menu.addAction(menu_icon(copy_pixmap), "复制")
        act_copy.setShortcut(QKeySequence.StandardKey.Copy)      # 菜单右侧显示 Ctrl+C
        act_copy.setEnabled(bool(selection))                     # 没有选中就不能复制

        act_all = menu.addAction(menu_icon(select_all_pixmap), "全选")
        act_all.setShortcut(QKeySequence.StandardKey.SelectAll)  # 菜单右侧显示 Ctrl+A
        act_all.setEnabled(bool(full) and selection != full)

        menu.copy_action = act_copy
        menu.select_all_action = act_all
        return menu, act_copy, act_all

    def _show_text_menu(self, label: QLabel, pos):
        menu, act_copy, act_all = self._build_text_menu(label)
        # 弹窗平时不调用 activateWindow（避免抢焦点），导致右键菜单经常
        # 拿不到键盘输入 → 打开菜单前先激活一次窗口
        if not self.isActiveWindow():
            self.activateWindow()
        self._menu_ctx = (menu, act_copy, act_all)
        try:
            chosen = menu.exec(label.mapToGlobal(pos))
        finally:
            # 记下菜单关闭时的位置：菜单可能超出弹窗范围，关闭后立刻到达的
            # 「外部点击」其实是点在菜单上的那一下，不能据此关掉弹窗
            self._last_menu_close = (time.time(), menu.frameGeometry())
            self._menu_ctx = None
        # 用快捷键激活时 exec() 返回 None，从菜单记录里取回真正被触发的动作
        if chosen is None:
            chosen = menu.activated_by_key
        if chosen is None:
            return
        if chosen is act_copy and label.selectedText():
            QApplication.clipboard().setText(label.selectedText())
        elif chosen is act_all:
            label.setSelection(0, len(label.text()))

    def swallows_click(self, point) -> bool:
        """该点击是否落在右键菜单上（菜单可能超出弹窗范围）。

        点在菜单上（尤其是菜单超出弹窗边界的部分）不应被当成「弹窗外点击」
        而关掉弹窗，否则点「全选」会把弹窗一起关掉。
        """
        # 菜单还开着 → 一律不关，等它自己处理完
        if getattr(self, "_menu_ctx", None) is not None:
            return True
        ts, geo = getattr(self, "_last_menu_close", (0.0, None))
        if geo is None or time.time() - ts > MENU_CLICK_GRACE:
            return False
        return geo.adjusted(-8, -8, 8, 8).contains(point)

    def _hline(self, lay):
        line = QFrame()
        line.setObjectName("HLine")
        line.setFixedHeight(1)
        lay.addWidget(line)

    # ---------- 发音按钮 / 候选地址 ----------

    @staticmethod
    def _candidates(text: str, accent: str, speech: str = None) -> list:
        """候选发音地址：词典自带地址优先，其后是「首选口音 → 备用口音」。

        dictvoice 对部分短句只有单一口音，备用地址用于兜底，保证能读出声。
        """
        urls = [speech] if speech else []
        urls.extend(translator.voice_urls(text, accent))
        out, seen = [], set()
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _make_play_btn(self, tooltip: str, urls: list, text: str = None,
                       accent: str = None) -> SpeakerButton:
        btn = SpeakerButton(size=22, tooltip=tooltip)
        btn.speak_text = text or ""          # 待朗读内容（TTS 兜底与排查用）
        btn.speak_accent = accent or ""      # 本按钮的口音（uk/us）
        btn.clicked.connect(
            lambda _=False, u=list(urls), b=btn, t=text: self._play_word(u, b, t))
        return btn

    def _move_near(self, x: int, y: int):
        # 鼠标钩子给的是物理像素，Qt 的屏幕几何用逻辑像素 → 先统一换算
        p = physical_to_logical(x, y)
        screen = QApplication.screenAt(p) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        w, h = self.width(), self.sizeHint().height()
        nx, ny = p.x() + 16, p.y() + 18
        if nx + w > geo.right():
            nx = x - w - 16
        if ny + h > geo.bottom():
            ny = y - h - 18
        self.move(max(geo.left() + 4, nx), max(geo.top() + 4, ny))

    # ---------- 发音播放 ----------

    def _play_word(self, urls, btn=None, text: str = None):
        """播放发音（单词/短句通用）。

        流程：后台线程依次尝试候选地址 → 全部无音频时用 edge-tts 在线合成兜底
        → 就绪后回 GUI 线程播放（Qt 优先，失败回退 MCI）。
        """
        if isinstance(urls, str):
            urls = [urls]
        config.log_debug(f"audio: 点击发音 {urls[0] if urls else '-'}")
        if btn is not None:
            btn.set_state(SpeakerButton.STATE_LOADING, "正在加载发音…")
            QApplication.processEvents()
        threading.Thread(
            target=self._prepare_audio, args=(list(urls), text, btn), daemon=True
        ).start()

    def _prepare_audio(self, urls: list, text: str, btn):
        """后台线程：下载/合成音频，完成后回传 GUI 线程。"""
        # 整句（含空格）在 dictvoice 里基本没有录音（实测英/美都返回 500），
        # 只试首选口音并缩短超时，尽快回退到在线合成，省掉无谓的等待
        if " " in (text or ""):
            urls, timeout = urls[:1], 3
        else:
            timeout = 8
        path, used = audio.download_first(urls, timeout=timeout)
        note = ""
        if path and len(urls) > 1 and used != urls[0]:
            note = "首选口音不可用，已播放另一口音"
        if not path and text:
            cfg = config.load()
            if cfg.get("tts_fallback", True):
                # 口音必须取自按钮本身（uk/us）：在线合成是最后的兜底，
                # 若这里退回全局设置，英音按钮也会合成美音，两个按钮听起来就一样了
                accent = getattr(btn, "speak_accent", "") or \
                    cfg.get("pronounce_accent", "us")
                path = audio.synth_edge(text, accent)
                if path:
                    note = "已使用在线语音合成"
        if not path:
            config.log_debug("audio: 发音均不可用（含在线合成兜底）")
        self._audioReady.emit((path or "", btn, note))

    def _on_audio_ready(self, payload):
        """GUI 线程：拿到本地音频后播放。"""
        path, btn, note = payload
        if not path:
            self._flash_fail(btn)
            return
        self._last_audio_path = path
        self._last_audio_btn = btn
        played = self._qt_play(path)
        if not played:
            played = audio.play_mci(path)
        if played:
            self._start_playing_anim(btn, note)
        else:
            self._flash_fail(btn)

    def _qt_play(self, path: str) -> bool:
        try:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
            return True
        except Exception as e:
            config.log_debug(f"audio: Qt 播放异常 {e}")
            return False

    def _on_media_error(self, *_):
        """Qt 播放报错时回退 MCI（同一文件）。"""
        if self._last_audio_path:
            config.log_debug(f"audio: Qt 报错 {self._player.errorString()!r}，尝试 MCI")
            if audio.play_mci(self._last_audio_path):
                self._start_playing_anim(self._last_audio_btn)
            else:
                self._flash_fail(self._last_audio_btn)

    # ---------- 播放按钮状态动画 ----------

    def _start_playing_anim(self, btn, note: str = ""):
        """切换到播放中状态：图标自身会做声波扩散动画"""
        if btn is None:
            return
        self._play_btn = btn
        self._play_note = note
        btn.set_state(SpeakerButton.STATE_PLAYING, "正在播放…")
        QTimer.singleShot(1500, self._stop_playing_anim)

    def _stop_playing_anim(self):
        if self._play_btn is not None:
            try:
                # 播放结束恢复原提示；若走了兜底/备用口音，保留说明
                self._play_btn.set_state(
                    SpeakerButton.STATE_IDLE,
                    self._play_note or self._play_btn.base_tooltip)
            except RuntimeError:
                pass
        self._play_btn = None
        self._play_note = ""

    def _flash_fail(self, btn):
        if btn is None:
            return
        btn.set_state(SpeakerButton.STATE_FAIL, "发音播放失败")
        QTimer.singleShot(1400, lambda: self._restore_btn(btn))

    @staticmethod
    def _restore_btn(btn):
        try:
            btn.reset()
        except RuntimeError:
            pass

    def _maybe_auto_pronounce(self, text: str, info: dict = None, urls: list = None):
        """划词后自动朗读（单词/短句通用）"""
        cfg = config.load()
        if not cfg.get("auto_pronounce"):
            return
        accent = cfg.get("pronounce_accent", "us")
        if urls is None:
            item = (info or {}).get(accent) or {}
            urls = self._candidates(text, accent, item.get("speech"))
        self._play_word(urls, None, text)
