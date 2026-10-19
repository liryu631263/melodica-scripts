"""本地曲库检索（命令行）：列出 / 搜索 scores/ 目录下的曲谱，支持别名与模糊匹配。

用法：
    python cli/library.py            # 列出全部曲谱
    python cli/library.py 关键词      # 按曲名/文件名/别名搜索（不区分大小写）

交互式「输入曲名 → 选曲 → 试听/演奏」请用 search.py：
    python cli/search.py

把新曲谱加入曲库：用 translate_cli.py 把 MIDI / 简谱翻译成 .mel，再放进 scores/ 目录。
"""

import argparse
import os
import sys

# 本脚本位于 cli/ 子目录，先把仓库根加进 sys.path，保证能 import melodica
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from melodica.library import LIB_DIR, scan, search  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description='本地口风琴曲库检索')
    p.add_argument('keyword', nargs='?', default=None, help='搜索关键字（曲名/文件名/别名）')
    p.add_argument('--dir', default=LIB_DIR, help='曲库目录（默认 scores/）')
    args = p.parse_args(argv)

    items = scan(args.dir)
    if args.keyword:
        items = search(args.keyword, items)

    if not items:
        print('曲库为空，或没有匹配的曲谱。')
        print('把新曲谱翻译成 .mel 放入曲库目录，或：python cli/translate_cli.py <mid或简谱文件> --out scores/<曲名>.mel')
        return 0

    print(f"共 {len(items)} 首曲谱：")
    for it in items:
        bpm = f"{it['bpm']:g}" if it['bpm'] else '?'
        dur = f"{it['beats'] / it['bpm'] * 60:.0f}s" if it['bpm'] else '?'
        alias = f"（别名：{'、'.join(it['aliases'])}）" if it['aliases'] else ''
        print(f"  {it['name']:<16} {it['title']}{alias}")
        print(f"      {it['n_notes']} 音符 · BPM {bpm} · 约 {dur} · {os.path.relpath(it['path'])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
