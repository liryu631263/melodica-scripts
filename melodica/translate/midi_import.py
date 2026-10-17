"""MIDI 解析：把 .mid 读成各轨道的音符（音高 / 起始拍 / 时值拍）。

依赖 mido（纯 Python 库，`pip install mido`）。
"""

from dataclasses import dataclass

import mido


@dataclass
class RawNote:
    pitch: int
    start: float      # 起始（拍）
    duration: float   # 时值（拍）


def parse_midi(path):
    """解析 MIDI 文件，返回 (tracks, bpm)。

    tracks — 每个轨道是一个 RawNote 列表（按起始时间排序）
    bpm    — 第一个 set_tempo 对应的速度（没有则默认 120）
    """
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat or 480
    bpm = 120.0
    tracks = []

    for track in mid.tracks:
        notes = []
        abs_tick = 0
        open_notes = {}
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'set_tempo':
                bpm = round(60_000_000 / msg.tempo, 2)
            elif msg.type == 'note_on' and msg.velocity > 0:
                open_notes.setdefault(msg.note, abs_tick)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                start = open_notes.pop(msg.note, None)
                if start is not None:
                    notes.append(RawNote(
                        pitch=msg.note,
                        start=start / tpb,
                        duration=(abs_tick - start) / tpb,
                    ))
        tracks.append(sorted(notes, key=lambda n: n.start))
    return tracks, bpm
