"""本地曲库检索：列出 / 搜索 scores/ 目录下的曲谱，支持别名与模糊匹配。

用法：
    python library.py            # 列出全部曲谱
    python library.py 关键词      # 按曲名/文件名/别名搜索（不区分大小写）

交互式「输入曲名 → 选曲 → 试听/演奏」请用 search.py：
    python search.py

把新曲谱加入曲库：用 translate.py 把 MIDI / 简谱翻译成 .mel，再放进 scores/ 目录。
"""

import argparse
import os
import re
import sys

from melodica.core import score as score_mod

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores')


def _meta_from(path):
    """读取曲谱头部注释，返回 (title, aliases)。

    - 第一个非空的 # 注释行视为曲名
    - `# @别名 a b c` 行提供别名（如拼音/英文名，便于搜索）
    """
    title = None
    aliases = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s.startswith('#'):
                if s:
                    break  # 遇到 T= 或音符就停止读头部
                continue
            body = s.lstrip('#').strip()
            if not body:
                continue
            if body.startswith('@别名') or body.startswith('@alias'):
                rest = re.sub(r'^@别名\s*', '', body)
                aliases += [a for a in re.split(r'[\s,，、]+', rest) if a]
            elif title is None:
                title = body
    return title, aliases


def scan(lib_dir=LIB_DIR):
    """扫描曲库，返回 [{name, title, aliases, path, bpm, n_notes, beats}]。"""
    result = []
    if not os.path.isdir(lib_dir):
        return result
    for fn in sorted(os.listdir(lib_dir)):
        if not fn.lower().endswith('.mel'):
            continue
        path = os.path.join(lib_dir, fn)
        title, aliases = _meta_from(path)
        try:
            notes, bpm = score_mod.load_score(path)
        except Exception:
            notes, bpm = [], None
        result.append({
            'name': os.path.splitext(fn)[0],
            'title': title or os.path.splitext(fn)[0],
            'aliases': aliases,
            'path': path,
            'bpm': bpm,
            'n_notes': len(notes),
            'beats': sum(n.beats for n in notes),
        })
    return result


def _norm(s):
    return re.sub(r'[\s_\-]+', '', s).lower()


def match(query, item):
    """返回 query 与 item 的匹配度分数（0 = 不匹配）。分数越高越靠前。"""
    q = _norm(query)
    if not q:
        return 0
    fields = [(item['name'], 70), (item['title'], 80)]
    fields += [(a, 60) for a in item.get('aliases', [])]
    best = 0
    for text, base in fields:
        t = _norm(text)
        if not t:
            continue
        if t == q:
            best = max(best, base + 40)
        elif t.startswith(q):
            best = max(best, base + 30)
        elif q in t:
            best = max(best, base + 20)
        elif t in q:
            best = max(best, base + 10)
    return best


def search(query, items):
    """按匹配度排序返回匹配项（降序），无匹配返回空列表。"""
    scored = [(match(query, it), it) for it in items]
    scored = [(s, it) for s, it in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored]


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
        print('把新曲谱翻译成 .mel 放入曲库目录，或：python translate.py <mid或简谱文件> --out scores/<曲名>.mel')
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
