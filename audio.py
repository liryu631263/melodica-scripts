"""口风琴音色合成与播放（纯标准库，Windows 专用）。

- 用正弦波 + 少量谐波 + ADSR 包络合成 16-bit PCM。
- 用 winsound 播放（SND_MEMORY + SND_ASYNC），无需第三方库。
- 注意：这是简化的口风琴音色，不模拟游戏内「起音约 0.25s 达六成、约 3.6s 渐强」的
  缓慢音量包络，而是采用更常规的短起音/释放，听感更接近真实口风琴。
"""

import math
import struct
import threading
import wave
import winsound
from io import BytesIO

SAMPLE_RATE = 44100


def midi_to_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def note_pcm(midi, duration, volume=0.5, sample_rate=SAMPLE_RATE):
    """合成单个音符的原始 PCM（16-bit mono）。"""
    freq = midi_to_freq(midi)
    n = max(1, int(sample_rate * duration))
    attack = max(1, int(sample_rate * 0.02))
    release = max(1, int(sample_rate * 0.06))
    out = bytearray()
    for i in range(n):
        env = 1.0
        if i < attack:
            env = i / attack
        elif i > n - release:
            env = (n - i) / release
        t = i / sample_rate
        s = (math.sin(2 * math.pi * freq * t)
             + 0.35 * math.sin(2 * math.pi * 2 * freq * t)
             + 0.15 * math.sin(2 * math.pi * 3 * freq * t))
        s *= env * volume / 1.5
        out += struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767))
    return bytes(out)


def _wav_bytes(pcm, sample_rate=SAMPLE_RATE):
    buf = BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def note_wav(midi, duration, volume=0.5, sample_rate=SAMPLE_RATE):
    """合成单个音符，返回带 WAV 头的字节。"""
    return _wav_bytes(note_pcm(midi, duration, volume, sample_rate), sample_rate)


def score_wav(notes, bpm, note_gap=0.03, sample_rate=SAMPLE_RATE):
    """把整个曲谱合成一份 WAV（含 WAV 头）。返回 (wav_bytes, start_times_seconds)。"""
    spb = 60.0 / bpm
    gap = min(note_gap, spb * 0.5)
    chunks = []
    start_times = []
    t = 0.0
    for note in notes:
        start_times.append(t)
        seg_len = int(sample_rate * note.beats * spb)
        seg = bytearray(seg_len * 2)  # 先全部静音
        if not note.is_rest:
            dur = max(0.0, note.beats * spb - gap)
            sound = note_pcm(note.midi(), dur, sample_rate=sample_rate)
            if len(sound) > len(seg):
                sound = sound[:len(seg)]
            seg[:len(sound)] = sound
        chunks.append(bytes(seg))
        t += note.beats * spb
    return _wav_bytes(b''.join(chunks), sample_rate), start_times


_play_thread = None
_play_lock = threading.Lock()


def _play_sync(data):
    try:
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except RuntimeError:
        pass  # 播放被 stop_all() 打断时忽略


def play_wav(data, async_play=True):
    """播放 WAV 字节。async_play=True 时在后台线程播放并立即返回。

    说明：winsound 不支持 SND_MEMORY + SND_ASYNC 组合（会抛
    「Cannot play asynchronously from memory」），因此用后台线程做同步播放来模拟异步。
    """
    global _play_thread
    if not async_play:
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        return
    with _play_lock:
        stop_all()
        if _play_thread is not None:
            _play_thread.join(timeout=0.5)
        _play_thread = threading.Thread(target=_play_sync, args=(data,), daemon=True)
        _play_thread.start()


def stop_all():
    """停止当前所有播放。"""
    winsound.PlaySound(None, winsound.SND_PURGE)
