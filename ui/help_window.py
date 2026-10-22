# -*- coding: utf-8 -*-
"""应用内帮助窗口：基于现有功能的使用说明（纯文本 HTML，可滚动、可复制）"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextBrowser, QGraphicsDropShadowEffect, QFrame, QStyle,
)

import config


# 帮助正文（HTML）。内容完全基于软件现有功能，便于用户对照操作。
HELP_HTML = """
<style>
  body { font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
         color: #23303d; font-size: 13px; line-height: 1.65; margin: 0; }
  h1 { font-size: 19px; color: #1f3a56; margin: 0 0 4px; }
  h2 { font-size: 15px; color: #2f6fae; margin: 18px 0 6px;
       border-left: 4px solid #4a90d9; padding-left: 8px; }
  h3 { font-size: 13px; color: #33506b; margin: 12px 0 4px; }
  p  { margin: 4px 0; }
  ul { margin: 4px 0 4px 0; padding-left: 20px; }
  li { margin: 3px 0; }
  code { background: #eaf0f7; color: #1f3a56; padding: 1px 5px;
         border-radius: 4px; font-family: Consolas, "Courier New", monospace;
         font-size: 12px; }
  .tip { background: #fff6e6; border: 1px solid #ffe0a3; border-radius: 8px;
         padding: 8px 12px; margin: 8px 0; color: #7a5a16; }
  .key { display: inline-block; background: #eef4fb; border: 1px solid #c9d4e0;
         border-radius: 4px; padding: 0 6px; margin: 0 1px;
         font-family: Consolas, monospace; font-size: 12px; color: #2f6fae; }
  .divider { height: 1px; background: #e3eaf2; margin: 14px 0; }
  .foot { color: #9aa7b4; font-size: 11px; margin-top: 16px; }
</style>

<h1>辰光 · 划词翻译 — 使用帮助</h1>
<p>一款 Windows 桌面划词翻译工具：在任意软件中选中文本，即可自动弹出翻译浮窗。</p>

<h2>一、快速上手</h2>
<ul>
  <li><b>划词翻译</b>：在任意 Windows 程序中选中英文，<b>双击单词</b> 或 <b>拖选短句</b> 后，翻译浮窗会自动弹出。</li>
  <li><b>快捷键取词</b>：默认按 <span class="key">F4</span> 取词（可在设置中改为 F9 / Ctrl / Alt / Ctrl+Shift+T）。</li>
  <li><b>手动查询</b>：打开主设置界面，在顶部输入框输入单词或短句，回车或点「查询」。</li>
</ul>
<div class="tip">提示：程序启动后会自动打开设置界面，关闭后仍驻留系统托盘后台运行，单击（左键点击）托盘图标即可再次打开。</div>

<h2>二、翻译浮窗说明</h2>
<h3>单词视图</h3>
<ul>
  <li><b>音标</b>：分别显示英式 [音标] 与美式 [音标]。</li>
  <li><b>发音</b>：音标右侧的喇叭图标，点击即播放对应口音发音。</li>
  <li><b>基本翻译</b>：单词释义；若该译文为英文，其右侧也提供英/美朗读图标。</li>
  <li><b>网络释义</b>：来自词典的网络用例释义。</li>
</ul>
<h3>短句视图</h3>
<ul>
  <li>显示<b>基本翻译</b>；若原文含英文，顶部提供 <b>英 🔊 / 美 🔊</b> 整句朗读。</li>
  <li>若译文为英文（例如中文译成英文），「基本翻译」行右侧同样提供英/美朗读。</li>
</ul>
<h3>链接 / 超长内容</h3>
<ul>
  <li>选中网址或超长内容时<b>不翻译</b>，浮窗只显示原文，并提供：</li>
  <li>· 标题右侧的<b>复制</b>图标；</li>
  <li>· 若是链接，额外给出「<b>在浏览器中打开</b>」按钮。</li>
</ul>
<h3>中文内容</h3>
<ul>
  <li>默认开启「仅翻译英文」：划到中文等非英文内容时不翻译，仅弹窗显示原文并带复制按钮。</li>
  <li>若取消勾选「仅翻译英文」，中文也会被翻译（译为英文）。</li>
  <li>无论哪种情况，<b>只要选中了内容就会弹窗</b>。</li>
</ul>

<h2>三、复制与右键菜单</h2>
<ul>
  <li>浮窗<b>标题右侧</b>有一个复制图标，点击即可复制划译内容。</li>
  <li>在浮窗任意文字上<b>右键</b>可打开菜单：<b>复制</b>（<span class="key">Ctrl</span>+<span class="key">C</span>）、<b>全选</b>（<span class="key">Ctrl</span>+<span class="key">A</span>）。</li>
  <li>也可直接在浮窗里用鼠标选中文字后复制。</li>
</ul>

<h2>四、朗读功能</h2>
<ul>
  <li>单词与短句均提供 <b>英式（英）</b> 与 <b>美式（美）</b> 两种发音，点击对应喇叭图标即可。</li>
  <li><b>自动朗读</b>：在设置中开启后，划词完成会自动朗读；可指定默认口音（美 / 英）。</li>
  <li><b>在线合成兜底</b>：有道在线发音只对已收录的短语有录音，短句无录音时会自动用微软神经语音合成朗读，口音按所点按钮区分（英 / 美）。</li>
</ul>

<h2>五、主设置界面</h2>
<h3>查询与历史</h3>
<ul>
  <li><b>查询框</b>：手动输入单词/短句查询，回车或点「查询」。</li>
  <li><b>查询历史</b>：展示最近查询记录，点击可重新查询；可「清空」。</li>
  <li>「查询历史显示条数」可设置为 0（不存储历史）、5 / 10 / 15 / 30 条。</li>
</ul>
<h3>选项设置</h3>
<ul>
  <li><b>划词翻译（选中后自动弹出）</b>：总开关，关闭后不再自动取词。</li>
  <li><b>快捷键取词</b>：开启并可选择热键（F4 / F9 / Ctrl / Alt / Ctrl+Shift+T）。</li>
  <li><b>仅翻译英文</b>：中文只显示原文便于复制；取消则中文也翻译。</li>
  <li><b>自动朗读</b> + 口音（美 / 英）：划词后自动朗读。</li>
  <li><b>查询历史显示条数</b>：0 = 不存储，其余为显示条数。</li>
  <li><b>划词灵敏度</b>：拖动触发所需的鼠标位移阈值——
        <ul>
          <li>极宽松 / 宽松：几乎不动或轻微拖动即触发；</li>
          <li>标准（默认）/ 严格：明显拖动才触发。</li>
        </ul>
        若出现「位移不足，未触发取词」，请调低灵敏度；若单击空白处也弹窗，请调高。</li>
  <li><b>弹窗自动关闭时间</b>：填写秒数后弹窗自动关闭，0 = 不自动关闭。</li>
  <li><b>短句朗读在线合成兜底</b>：短句无原生录音时自动合成朗读。</li>
  <li><b>开机自动启动</b>：开机登录后自动运行（写入注册表）。</li>
  <li><b>点击弹窗外部区域时关闭弹窗</b>：取消后点击外部不再关闭。</li>
  <li><b>查看运行日志</b>：划词没反应时，点此打开 debug.log 排查（见下方常见问题）。</li>
</ul>
<h3>翻译源</h3>
<ul>
  <li>默认 <b>有道翻译</b>，需自行填写 <b>appKey / appSecret</b> 后方可使用。</li>
  <li>填写位置：设置界面「翻译源」面板，或直接编辑程序目录下的
      <b>config.json</b>（<code>youdao_app_key</code> / <code>youdao_app_secret</code>）。</li>
  <li>也可切换 <b>百度 / 谷歌 / DeepL</b>，需自行申请并填写对应的 API 凭据，
      所有凭据都保存在同一个 <b>config.json</b> 中。</li>
  <li>改动翻译源或凭据后，设置界面会自动重测连通性；失败时显示红色提示，可点「重试」。</li>
</ul>

<h2>六、系统托盘</h2>
<ul>
  <li>程序后台常驻，关闭设置窗口不会退出。</li>
  <li><b>单击（左键点击）</b>托盘图标 → 打开设置界面（也可双击）。</li>
  <li><b>右键</b>托盘图标 → 「打开设置」/「使用帮助」/「退出」。</li>
</ul>

<h2>七、关闭浮窗的几种方式</h2>
<ul>
  <li>点击浮窗<b>外部</b>任意区域（若已开启该选项）；</li>
  <li>按 <span class="key">Esc</span> 键；</li>
  <li>点击浮窗右上角的 <b>✕</b>；</li>
  <li>设置了自动关闭秒数后，到时自动关闭。</li>
</ul>

<h2>八、常见问题（FAQ）</h2>
<h3>1. 划词没反应？</h3>
<ul>
  <li>确认主界面「划词翻译（选中后自动弹出）」已勾选。</li>
  <li>若日志出现「位移不足，未触发取词」，说明灵敏度过高，请改为「极宽松」或「宽松」。</li>
  <li>个别程序（部分 PDF 阅读器、浏览器特殊区域）取不到文本，请改用<b>快捷键取词</b>。</li>
  <li>点主界面「查看运行日志」，根据日志定位原因。</li>
</ul>
<h3>2. 提示「接口连接失败」或翻译失败？</h3>
<ul>
  <li>检查网络是否通畅；点设置界面「重试」重新检测。</li>
  <li>若使用非有道翻译源，请确认 API 凭据填写正确。</li>
</ul>
<h3>3. 英音和美音听上去一样？</h3>
<ul>
  <li>短句原生发音缺失时会走在线合成兜底，口音按所点按钮区分——点「英」即英音、点「美」即美音，二者不会混淆。</li>
</ul>
<h3>4. 中文内容为什么不翻译？</h3>
<ul>
  <li>默认开启「仅翻译英文」。如需翻译中文，取消该勾选即可（中文将译为英文）。</li>
</ul>
<h3>5. 弹窗关不掉 / 一碰就关？</h3>
<ul>
  <li>可关闭方式见第六节；若误触关闭，调整「划词灵敏度」或「点击弹窗外部区域时关闭弹窗」选项。</li>
</ul>

<div class="divider"></div>
<p class="foot">辰光科技 · 划词翻译　|　划词即译，所见即所得</p>
"""


class _HelpHeader(QWidget):
    """帮助窗口的自绘标题栏：品牌 + 关闭按钮，支持拖动"""

    def __init__(self, title: str, window: "HelpWindow"):
        super().__init__(window)
        self.setObjectName("HelpTitleBar")
        self.setFixedHeight(40)
        self._window = window
        self._drag_pos = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(8)

        logo = QLabel()
        pix = QPixmap(config.resource_path(os.path.join("assets", "logo_h.png")))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(20, Qt.TransformationMode.SmoothTransformation))
        else:
            lab = QLabel("辰光")
            lab.setStyleSheet("font-size:16px;font-weight:bold;color:#e0343c;")
            lay.addWidget(lab)
        lay.addWidget(logo)

        text = QLabel(title)
        text.setStyleSheet("font-size:14px;font-weight:bold;color:#1f3a56;")
        lay.addWidget(text)
        lay.addStretch(1)

        btn_close = QPushButton()
        btn_close.setObjectName("HelpClose")
        btn_close.setFixedSize(30, 30)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("关闭帮助")
        # 通用关闭图标（系统原生对话框关闭图标）
        close_icon = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogCloseButton)
        btn_close.setIcon(close_icon)
        btn_close.setIconSize(btn_close.size() * 0.55)
        btn_close.clicked.connect(window.close)
        btn_close.setStyleSheet(
            "QPushButton { background:transparent; border:none;"
            " border-radius:6px; }"
            "QPushButton:hover { background:#eaf0f7; }")
        lay.addWidget(btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self._window.frameGeometry().topLeft())
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)


class HelpWindow(QDialog):
    """帮助窗口：浅色卡片 + 可滚动 HTML 内容"""

    STYLE = """
    QDialog { background: #f4f7fb; border: 1px solid #d3dde8; border-radius: 12px; }
    #HelpTitleBar { background: #ffffff; border-top-left-radius: 12px;
                    border-top-right-radius: 12px; border-bottom: 1px solid #e3eaf2; }
    QTextBrowser { background: #f4f7fb; border: none; }
    QTextBrowser { selection-background-color: #2F7BF6; selection-color: #ffffff; }
    QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
    QScrollBar::handle:vertical { background: #c2d4e6; border-radius: 4px; min-height: 24px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("划词翻译 - 帮助")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(560, 520)
        self.resize(640, 600)
        try:
            from ui.appicon import app_icon
            self.setWindowIcon(app_icon())
        except Exception:
            pass
        self.setStyleSheet(self.STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_HelpHeader("使用帮助", self))

        card = QFrame(self)
        card.setObjectName("HelpCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(40, 80, 130, 50))
        card.setGraphicsEffect(shadow)
        card.setStyleSheet("background:#f4f7fb;border:none;")
        outer.addWidget(card, 1)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)

        self._browser = QTextBrowser(card)
        self._browser.setOpenExternalLinks(False)
        self._browser.setHtml(HELP_HTML)
        cl.addWidget(self._browser)

    def show_help(self):
        """显示并置顶（已显示则只是置前）"""
        self.show()
        self.raise_()
        self.activateWindow()
