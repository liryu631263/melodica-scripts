"""曲库检索 + 演奏入口：输入曲名 → 搜索 → 选曲 → 试听/演奏。

本地检索（scores/ 曲库）：
    python search.py 小星星
    python search.py 小星星 --sim / --game / --show

网络检索（公开 MIDI 站，灰色版权内容仅供个人练习，需 pip install scoreseek）：
    python search.py "happy birthday" --online
    python search.py "canon" --online --pick 1 --sim
"""

import argparse
import os
import re
import subprocess
import sys

import library

ROOT = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(ROOT, 'downloads')


def _reconfigure_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass


def _run(script, path):
    return subprocess.call([sys.executable, os.path.join(ROOT, script), path], cwd=ROOT)


def _safe_name(s, maxlen=40):
    s = re.sub(r'[\\/:*?"<>|]+', '_', s).strip().strip('.')
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen] or 'untitled'


def _pick(items, index=None):
    if index is not None:
        if 1 <= index <= len(items):
            return items[index - 1]
        print(f'无效序号 {index}（共 {len(items)} 首）。')
        return None
    if len(items) == 1:
        return items[0]
    print('找到多首，请选择：')
    for i, it in enumerate(items, 1):
        note = f" · {it['n_notes']} 音符" if it.get('n_notes') else ''
        print(f"  [{i}] {it['title']}{note}")
    while True:
        n = input('选序号（默认 1）：').strip() or '1'
        try:
            return items[int(n) - 1]
        except (ValueError, IndexError):
            print('无效序号，请重试。')


def _online_search(kw, args):
    try:
        from melodica.translate import net_search
    except net_search.NetSearchError as e:
        print(f'网络检索不可用：{e}')
        return None

    print(f'网络搜索「{kw}」……')
    try:
        hits = net_search.search_online(kw, limit=args.limit)
    except Exception as e:
        print(f'搜索失败：{e}')
        return None

    if not hits:
        print('未找到 MIDI 结果。')
        print(net_search.no_result_hint(kw))
        return None

    print(f'找到 {len(hits)} 条 MIDI（公开站点，灰色版权，仅供个人练习）：')
    for i, h in enumerate(hits, 1):
        c = f" · {h['composer']}" if h['composer'] else ''
        print(f"  [{i}] {h['title']}{c}  （{h['source']}）")

    sel = _pick(hits, args.pick)
    if sel is None:
        return None

    print('下载中……')
    try:
        mid = net_search.download_midi(sel)
    except Exception as e:
        print(f'下载失败：{e}')
        return None

    os.makedirs(DOWNLOADS, exist_ok=True)
    mel = os.path.join(DOWNLOADS, _safe_name(sel['title']) + '.mel')
    argv = [mid, '--out', mel]
    if args.min_sharps:
        argv.append('--min-sharps')
    if args.track is not None:
        argv += ['--track', str(args.track)]
    if args.bpm is not None:
        argv += ['--bpm', str(args.bpm)]

    import translate
    if translate.main(argv) != 0:
        print('翻译失败。')
        return None
    return {'title': sel['title'], 'path': mel, 'n_notes': None}


def _jianpu_search(kw, args):
    """简谱之家：搜中文简谱 → 选曲 → 下载曲谱图片（非文本，不自动翻译）。"""
    from melodica.translate import jianpujia

    print(f'简谱之家搜索「{kw}」……')
    try:
        hits = jianpujia.search(kw, limit=args.limit)
    except Exception as e:
        print(f'搜索失败：{e}')
        return 1

    if not hits:
        print('简谱之家未找到相关简谱。')
        print('可换个关键词（曲名 / 歌手）再试，或改用 --online 搜 MIDI。')
        return 0

    print(f'找到 {len(hits)} 首简谱：')
    for i, h in enumerate(hits, 1):
        print(f"  [{i}] {h['title']}")
    sel = _pick(hits, args.pick)
    if sel is None:
        return 1

    dest = os.path.join(DOWNLOADS, 'jianpu')
    print('下载曲谱图片中……')
    try:
        paths = jianpujia.download(sel, dest)
    except Exception as e:
        print(f'下载失败：{e}')
        return 1
    print(f'已下载 {len(paths)} 张曲谱图片：')
    for p in paths:
        print('  ' + os.path.relpath(p))
    print('提示：曲谱是图片，需先转成简谱文本再用 translate.py 翻译（可把图片发给我帮忙识别）。')
    return 0


def main(argv=None):
    _reconfigure_utf8()
    p = argparse.ArgumentParser(description='曲库检索 + 试听/演奏（本地 / 网络）')
    p.add_argument('keyword', nargs='?', default=None, help='曲名（省略则交互输入）')
    p.add_argument('--online', action='store_true', help='网络检索公开 MIDI 源（需 pip install scoreseek）')
    p.add_argument('--jianpu', action='store_true', help='简谱之家检索中文简谱并下载曲谱图片')
    p.add_argument('--download-lakh', action='store_true', help='下载 Lakh MIDI 数据集（约 234MB，扩充网络检索曲库）')
    p.add_argument('--limit', type=int, default=10, help='网络搜索结果数上限（默认 10）')
    p.add_argument('--pick', type=int, default=None, help='直接选第 N 条结果（跳过选择提示）')
    p.add_argument('--min-sharps', action='store_true', help='翻译时自动选调，尽量少用升半音')
    p.add_argument('--track', type=int, default=None, help='翻译时指定 MIDI 轨道')
    p.add_argument('--bpm', type=float, default=None, help='翻译时覆盖速度')
    p.add_argument('--sim', action='store_true', help='直接模拟器试听')
    p.add_argument('--game', action='store_true', help='直接游戏内演奏')
    p.add_argument('--show', action='store_true', help='只显示曲谱内容')
    p.add_argument('--dir', default=library.LIB_DIR, help='本地曲库目录')
    args = p.parse_args(argv)

    if args.download_lakh:
        from melodica.translate import net_search
        net_search.download_lakh()
        return 0

    kw = args.keyword or input('请输入曲名：').strip()
    if not kw:
        print('未输入曲名。')
        return 0

    if args.jianpu:
        return _jianpu_search(kw, args)

    if args.online:
        sel = _online_search(kw, args)
    else:
        items = library.search(kw, library.scan(args.dir))
        if not items:
            print(f'本地未找到「{kw}」相关曲谱。')
            print('可先用 translate.py 把 MIDI/简谱翻译成 .mel 放入曲库；')
            print('或加 --jianpu 搜中文简谱图片、--online 联网搜 MIDI。')
            return 0
        sel = _pick(items, args.pick)

    if sel is None:
        return 1

    n = f"，{sel['n_notes']} 音符" if sel.get('n_notes') else ''
    print(f'已选：{sel["title"]}（{os.path.relpath(sel["path"])}{n}）')

    if args.sim:
        action = 'sim'
    elif args.game:
        action = 'game'
    elif args.show:
        action = 'show'
    else:
        print('下一步：')
        print('  [1] 模拟器试听（推荐，不封号）')
        print('  [2] 游戏内演奏')
        print('  [3] 查看曲谱')
        action = {'1': 'sim', '2': 'game', '3': 'show'}.get(input('选（默认 1）：').strip() or '1', 'sim')

    path = sel['path']
    if action == 'sim':
        print('启动模拟器试听……')
        return _run('simulator.py', path)
    if action == 'game':
        print('启动游戏演奏（默认 5 秒倒计时，请趁此切到游戏窗口，F12 随时停）……')
        return _run('main.py', path)
    if action == 'show':
        with open(path, encoding='utf-8') as f:
            print(f.read())
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
