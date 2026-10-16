"""曲谱翻译：MIDI / 简谱文本 -> 口风琴 .mel 曲谱。

用法：
    python translate.py input.mid [选项]     # MIDI 文件（.mid/.midi）
    python translate.py input.txt [选项]     # 简谱文本（.txt/.jianpu/.jp）

选项：
    --track N       选择 MIDI 轨道（默认音符最多的轨）
    --transpose N   额外移调 N 个半音（可为负）
    --min-sharps    自动选调，尽量少用「升半音」（降低演奏难度）
    --bpm N         覆盖输出速度
    --grid G        时值量化网格（拍，默认 0.25）
    --out PATH      输出 .mel 路径（默认 <输入名>.mel）
    --list-notes    只打印解析结果，不写文件

输出为 .mel，可直接用 simulator.py 试听、或用 main.py 在游戏内演奏。
"""

import argparse
import os
import sys

import jianpu
import midi_import
from melodica import Note, pitch_to_note
from score import notes_to_text

# 自然音区（不按鼠标）对应的 MIDI 范围：C5(72) ~ C♯6(85)
_SWEET_LO, _SWEET_HI = 72, 85
_RANGE_LO, _RANGE_HI = 60, 97  # 口风琴可演奏的完整范围


def extract_melody(raw_notes, gap_eps=0.1):
    """从一轨原始音符提取单声部主旋律（重叠时取最高音），并在间隙插入休止符。

    返回 [(pitch|None, beats), ...]，pitch 为 None 表示休止符。
    """
    raw = sorted(raw_notes, key=lambda n: (n.start, -n.pitch))
    melody = []
    for n in raw:
        if melody and n.start < melody[-1].start + melody[-1].duration:
            if n.pitch > melody[-1].pitch:
                melody[-1].duration = max(0.0, n.start - melody[-1].start)
                melody.append(n)
        else:
            melody.append(n)

    events = []
    t = 0.0
    for n in melody:
        if n.duration <= 0.01:
            continue
        if n.start > t + gap_eps:
            events.append((None, n.start - t))
        events.append((n.pitch, n.duration))
        t = n.start + n.duration
    return events


def _octave_fit(pitches):
    """按整八度平移，把旋律中心对齐到自然音区，并确保落在可演奏范围内。"""
    lo, hi = min(pitches), max(pitches)
    center = (lo + hi) / 2
    shift = int(round(((_SWEET_LO + _SWEET_HI) / 2 - center) / 12)) * 12
    if lo + shift < _RANGE_LO:
        shift += 12
    elif hi + shift > _RANGE_HI:
        shift -= 12
    return shift


def events_to_notes(events, grid=0.25, transpose=0, min_sharps=False):
    """把 (pitch|None, beats) 事件序列翻译成 Note 序列。"""
    # 1. 时值量化
    ev = []
    for p, d in events:
        q = round(d / grid) * grid if d > 0 else grid
        ev.append((p, max(grid, q)))

    # 2. 移调
    pitches = [p for p, _ in ev if p is not None]
    if pitches:
        k = 0
        if min_sharps:
            # 先按「升降半音数量」选调（只看音级，与八度无关）
            k = min(range(12), key=lambda kk: sum(1 for p in pitches if pitch_to_note(p + kk).sharp))
        # 再按整八度居中，把选中的调摆到自然音区（解决「降二度 vs 升十度」的八度选择）
        shift = _octave_fit([p + k for p in pitches]) + k + transpose
        ev = [(None if p is None else min(_RANGE_HI, max(_RANGE_LO, p + shift)), d) for p, d in ev]

    # 3. 音高映射
    notes = []
    for p, d in ev:
        if p is None:
            notes.append(Note(degree=0, beats=d))
        else:
            n = pitch_to_note(p)
            n.beats = d
            notes.append(n)
    return notes


def describe(n):
    if n.is_rest:
        return f"休止 {n.beats:g} 拍"
    mod = []
    if n.octave == -1:
        mod.append('降八度')
    elif n.octave == 1:
        mod.append('升八度')
    if n.sharp:
        mod.append('升半音')
    s = f"{n.degree}{'(高音1)' if n.degree == 8 else ''} [{n.label}] {n.beats:g} 拍"
    if mod:
        s += f" ({'/'.join(mod)})"
    return s


def main(argv=None):
    p = argparse.ArgumentParser(
        description="三角洲行动口风琴曲谱翻译（MIDI/简谱 -> .mel）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('input', help='输入文件：.mid/.midi（MIDI）或 .txt/.jianpu/.jp（简谱文本）')
    p.add_argument('--track', type=int, default=None, help='选择 MIDI 轨道（默认音符最多的轨）')
    p.add_argument('--transpose', type=int, default=0, help='额外移调 N 个半音')
    p.add_argument('--min-sharps', action='store_true', help='自动选调，尽量少用升半音')
    p.add_argument('--bpm', type=float, default=None, help='覆盖输出速度')
    p.add_argument('--grid', type=float, default=0.25, help='时值量化网格（拍，默认 0.25）')
    p.add_argument('--out', default=None, help='输出 .mel 路径')
    p.add_argument('--list-notes', action='store_true', help='只打印解析结果，不写文件')
    args = p.parse_args(argv)

    ext = os.path.splitext(args.input)[1].lower()

    if ext in ('.mid', '.midi'):
        try:
            tracks, bpm = midi_import.parse_midi(args.input)
        except Exception as e:
            print(f"错误：解析 MIDI 失败：{e}", file=sys.stderr)
            return 1
        if not any(tracks):
            print("错误：MIDI 中没有音符。", file=sys.stderr)
            return 1
        if args.track is not None:
            if not 0 <= args.track < len(tracks):
                print(f"错误：轨道 {args.track} 不存在（共 {len(tracks)} 轨）。", file=sys.stderr)
                return 1
            ti = args.track
        else:
            ti = max(range(len(tracks)), key=lambda i: len(tracks[i]))
        raw = tracks[ti]
        print(f"MIDI 共 {len(tracks)} 轨，选择第 {ti} 轨（{len(raw)} 个音符）。")
        if len(tracks) > 1:
            for i, tr in enumerate(tracks):
                if tr:
                    ps = [n.pitch for n in tr]
                    print(f"    轨 {i}: {len(tr)} 音符，音域 {min(ps)}-{max(ps)}")
        events = extract_melody(raw)

    elif ext in ('.txt', '.jianpu', '.jp', '.text'):
        try:
            with open(args.input, encoding='utf-8') as f:
                text = f.read()
            events, bpm = jianpu.parse_jianpu(text)
        except (OSError, jianpu.JianpuError) as e:
            print(f"错误：{e}", file=sys.stderr)
            return 1

    else:
        print(f"错误：不支持的输入类型 {ext}（支持 .mid/.midi/.txt/.jianpu/.jp）。", file=sys.stderr)
        return 1

    bpm = args.bpm if args.bpm is not None else bpm
    notes = events_to_notes(events, grid=args.grid, transpose=args.transpose, min_sharps=args.min_sharps)

    if args.list_notes:
        print(f"共 {len(notes)} 个音符，BPM={bpm:g}：")
        for i, n in enumerate(notes, 1):
            print(f"  {i:>3}.  {describe(n)}")
        return 0

    out = args.out or (os.path.splitext(args.input)[0] + '.mel')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(notes_to_text(notes, bpm))
    print(f"已翻译 {len(notes)} 个音符 -> {out}（BPM={bpm:g}）。")
    print(f"可试听：python simulator.py {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
