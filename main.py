"""三角洲行动 口风琴 演奏工具 —— 命令行入口。

用法：
    python main.py 曲谱文件 [选项]

选项：
    --bpm N          覆盖曲谱内的速度（BPM）
    --countdown S    开始前的倒计时秒数（默认 5）
    --gap S          音符间释放间隙秒数（默认 0.03，设 0 为完全连奏）
    --list-notes     只打印解析出的音符/键位，不实际演奏
    --smoke          冒烟测试：向前台窗口依次敲出 z x c v b n m ,（校验键盘注入）

曲谱格式见 scores/ 目录与 README.md。
演奏过程中按 F12 可随时停止。
"""

import argparse
import sys

from melodica.core.score import load_score, ScoreError
from melodica.core.input_backend import create_backend, VK_F12
from melodica.core.player import Player


def _reconfigure_utf8():
    """强制 stdout/stderr 用 UTF-8 输出，避免中文在 Windows 终端乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def describe_note(n):
    if n.is_rest:
        return f"休止  {n.beats:g} 拍"
    parts = [f"{n.degree}{'(高音1)' if n.degree == 8 else ''}"]
    parts.append(f"[{n.label}]")
    parts.append(f"{n.beats:g} 拍")
    mod = []
    if n.octave == -1:
        mod.append("降八度")
    elif n.octave == 1:
        mod.append("升八度")
    if n.sharp:
        mod.append("升半音")
    if mod:
        parts.append(f"({'/'.join(mod)})")
    if n.midi() is not None:
        parts.append(f"MIDI={n.midi()}")
    return "  ".join(parts)


def smoke_test():
    import time
    b = create_backend('win32')
    print("冒烟测试：请先切到记事本等文本窗口，稍候会依次敲出 z x c v b n m , …")
    for i in range(3, 0, -1):
        print(f"  {i}…")
        time.sleep(1)
    for scan in (0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33):
        b.press_key(scan)
        time.sleep(0.12)
        b.release_key(scan)
        time.sleep(0.12)
    print("完成。若窗口里依次出现 zxcvbnm, 则键盘注入正常。")


def main(argv=None):
    _reconfigure_utf8()
    p = argparse.ArgumentParser(
        description="三角洲行动口风琴演奏工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('score', nargs='?', help='曲谱文件路径（.mel / .txt）')
    p.add_argument('--bpm', type=float, default=None, help='覆盖曲谱内 T= 速度')
    p.add_argument('--countdown', type=float, default=5.0, help='倒计时秒数（默认 5）')
    p.add_argument('--gap', type=float, default=0.03, help='音符间间隙秒数（默认 0.03）')
    p.add_argument('--list-notes', action='store_true', help='只打印解析结果，不演奏')
    p.add_argument('--smoke', action='store_true', help='冒烟测试键盘注入')
    args = p.parse_args(argv)

    if args.smoke:
        smoke_test()
        return 0

    if not args.score:
        p.error('需要提供曲谱文件路径（或用 --smoke 测试）')

    try:
        notes, bpm = load_score(args.score)
    except (OSError, ScoreError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    if args.bpm:
        bpm = args.bpm

    print(f"曲谱：{args.score}  |  {len(notes)} 个音符  |  BPM={bpm:g}")
    if args.list_notes:
        for i, n in enumerate(notes, 1):
            print(f"  {i:>3}.  {describe_note(n)}")
        return 0

    backend = create_backend('win32')
    player = Player(backend, note_gap=args.gap, stop_vk=VK_F12)
    player.play(notes, bpm, countdown=args.countdown)
    return 0


if __name__ == '__main__':
    sys.exit(main())
