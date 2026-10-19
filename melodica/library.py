"""本地曲库检索（可复用库）：扫描 scores/ 下的 .mel，支持别名与模糊匹配。

命令行入口见 cli/library.py；web.py 与 cli/search.py 直接复用本模块。
"""

import os
import re

from melodica import ROOT
from melodica.core import score as score_mod

LIB_DIR = os.path.join(ROOT, 'scores')


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
