# -*- coding: utf-8 -*-
"""发音音频：下载 MP3 到本地缓存，并提供 Windows MCI 兜底播放。

注意：MCI 有线程亲和性，必须在主（GUI）线程调用；因此本模块只做下载与
MCI 播放，Qt 播放由弹窗在 GUI 线程负责。
"""
import ctypes
import hashlib
import os
import tempfile

import requests

import config

_ALIAS = "cg_tts"
_winmm = getattr(ctypes, "windll", None)
_winmm = _winmm.winmm if _winmm is not None else None


def download(url: str, timeout: int = 8):
    """下载发音到本地缓存，返回文件路径；失败返回 None。"""
    try:
        name = "cg_tts_" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10] + ".mp3"
        path = os.path.join(tempfile.gettempdir(), name)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        if len(r.content) < 500:      # 接口异常时会返回很小的 JSON 错误体
            config.log_debug(f"audio: 内容过小({len(r.content)}B)，视为无音频 {url}")
            return None
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        config.log_debug(f"audio: 下载失败 {e}")
        return None


# 在线合成的语音：英音/美音必须是两个不同的 voice，否则两个按钮听起来没区别
EDGE_VOICES = {
    "uk": ["en-GB-SoniaNeural", "en-GB-RyanNeural", "en-GB-LibbyNeural"],
    "us": ["en-US-AriaNeural", "en-US-AvaNeural", "en-US-AndrewNeural"],
}


def synth_edge(text: str, accent: str = "us", timeout: int = 8) -> str:
    """用 edge-tts（微软神经语音）在线合成英文文本，返回本地 mp3；失败返回 None。

    仅作为 dictvoice 无音频时的兜底：dictvoice 只对已收录的单词/短语有录音，
    整句基本没有（实测返回 500），所以整句朗读几乎都走这里。
    微软接口偶发 "No audio was received" 或长时间无响应，故逐个候选语音重试
    并加超时；失败时清掉残留的半截文件，避免下次被当成有效缓存。
    此函数可在后台线程调用（内部自建 event loop）。
    """
    if not text or not text.strip():
        return None
    try:
        import asyncio

        import edge_tts
    except Exception as e:
        config.log_debug(f"audio: edge-tts 不可用 {e}")
        return None

    voices = EDGE_VOICES.get(accent) or EDGE_VOICES["us"]
    last_err = None
    for voice in voices:
        name = "cg_tts_edge_" + hashlib.md5(
            (voice + "|" + text).encode("utf-8")).hexdigest()[:10] + ".mp3"
        path = os.path.join(tempfile.gettempdir(), name)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path

        async def _run():
            await edge_tts.Communicate(text, voice).save(path)

        try:
            asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
        except Exception as e:          # 超时 / NoAudioReceived / 网络错误
            last_err = e
            _drop_partial(path)
            continue
        if os.path.exists(path) and os.path.getsize(path) > 500:
            config.log_debug(f"audio: edge-tts 合成成功 {len(text)}字符 {voice}")
            return path
        _drop_partial(path)
    config.log_debug(f"audio: edge-tts 合成失败（{accent}）{last_err}")
    return None


def _drop_partial(path: str):
    """清掉合成失败留下的空/半截文件，防止下次被误判为缓存命中"""
    try:
        if os.path.exists(path) and os.path.getsize(path) <= 1000:
            os.remove(path)
    except OSError:
        pass


def download_first(urls, timeout: int = 8):
    """依次尝试候选发音地址，返回 (本地路径, 实际成功的 URL)；全失败返回 (None, None)。"""
    for u in urls or []:
        p = download(u, timeout)
        if p:
            return p, u
    return None, None


def play_mci(path: str) -> bool:
    """用 Windows MCI 播放本地 MP3（需在主线程调用）。"""
    if not _winmm:
        config.log_debug("audio: 无 winmm，无法使用 MCI")
        return False
    try:
        _winmm.mciSendStringW(f"close {_ALIAS}", None, 0, 0)
        err = _winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {_ALIAS}', None, 0, 0)
        if err:
            err = _winmm.mciSendStringW(f'open "{path}" alias {_ALIAS}', None, 0, 0)
        if err:
            config.log_debug(f"audio: MCI 打开失败 err={err}")
            return False
        err = _winmm.mciSendStringW(f"play {_ALIAS}", None, 0, 0)
        if err:
            config.log_debug(f"audio: MCI 播放失败 err={err}")
            return False
        config.log_debug("audio: MCI 播放中")
        return True
    except Exception as e:
        config.log_debug(f"audio: MCI 异常 {e}")
        return False
