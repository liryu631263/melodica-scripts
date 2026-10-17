"""口风琴「翻译 agent」：简谱之家搜曲 → 下载图片 → Qwen 视觉识图 → 翻译成 .mel。

用法：
    python agent.py 夜曲                  # 搜索、选曲、下载、识图、翻译
    python agent.py 夜曲 --pick 1         # 直接取第 1 条搜索结果
    python agent.py 夜曲 --no-translate   # 只下载图片 + 识图出简谱文本，不翻译
    python agent.py 夜曲 --min-sharps     # 翻译时自动选调，少用升半音

依赖：需设置 DASHSCOPE_API_KEY（环境变量，或项目根目录 .env 文件里写
      DASHSCOPE_API_KEY=xxx）。视觉模型默认 qwen3-vl-plus，可用 QWEN_MODEL 覆盖。
"""

import argparse
import os
import sys

from melodica.translate import jianpujia, qwen_vl

ROOT = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(ROOT, 'downloads')
SCORES = os.path.join(ROOT, 'scores')


def _reconfigure_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass


def _pick(items, index):
    if index is not None:
        if 1 <= index <= len(items):
            return items[index - 1]
        print(f'无效序号 {index}（共 {len(items)} 首）。')
        return None
    if len(items) == 1:
        return items[0]
    print('找到多首，请选择：')
    for i, it in enumerate(items, 1):
        print(f"  [{i}] {it['title']}")
    while True:
        n = input('选序号（默认 1）：').strip() or '1'
        try:
            return items[int(n) - 1]
        except (ValueError, IndexError):
            print('无效序号，请重试。')


def main(argv=None):
    _reconfigure_utf8()
    p = argparse.ArgumentParser(description='口风琴翻译 agent：搜简谱 → 下载图片 → Qwen 识图 → 翻译 .mel')
    p.add_argument('keyword', nargs='?', default=None, help='曲名（省略则交互输入）')
    p.add_argument('--pick', type=int, default=None, help='直接选第 N 条搜索结果')
    p.add_argument('--limit', type=int, default=10, help='搜索结果数上限（默认 10）')
    p.add_argument('--model', default=None, help='Qwen 视觉模型（默认 qwen-vl-plus）')
    p.add_argument('--no-translate', action='store_true', help='只下载图片 + 识图出简谱文本，不翻译成 .mel')
    p.add_argument('--min-sharps', action='store_true', help='翻译时自动选调，尽量少用升半音')
    p.add_argument('--bpm', type=float, default=None, help='翻译时覆盖速度')
    args = p.parse_args(argv)

    kw = args.keyword or input('请输入曲名：').strip()
    if not kw:
        print('未输入曲名。')
        return 0

    # 1. 搜索简谱之家
    print(f'简谱之家搜索「{kw}」……')
    try:
        hits = jianpujia.search(kw, limit=args.limit)
    except Exception as e:
        print(f'搜索失败：{e}')
        return 1
    if not hits:
        print('简谱之家未找到相关简谱，可换个关键词（曲名 / 歌手）。')
        return 0
    sel = _pick(hits, args.pick)
    if sel is None:
        return 1

    # 2. 下载曲谱图片
    dest = os.path.join(DOWNLOADS, 'jianpu')
    print('下载曲谱图片中……')
    try:
        paths = jianpujia.download(sel, dest)
    except Exception as e:
        print(f'下载失败：{e}')
        return 1
    for p in paths:
        print('  图片：' + os.path.relpath(p))

    # 3. Qwen 视觉识图（逐页）
    print('Qwen 视觉识别简谱中（逐页）……')
    parts = []
    for p in paths:
        try:
            text = qwen_vl.transcribe(p, model=args.model)
        except Exception as e:
            print(f'识图失败（{os.path.basename(p)}）：{e}')
            return 1
        parts.append(text)
    jianpu_text = '\n\n'.join(t for t in parts if t)

    base = jianpujia._safe_name(jianpujia._clean_title(sel['title']))
    txt_path = os.path.join(dest, base + '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(jianpu_text + '\n')

    print('\n----- 识别出的简谱文本 -----')
    print(jianpu_text)
    print('---------------------------')
    print('已存文本：' + os.path.relpath(txt_path))

    if args.no_translate:
        return 0

    # 4. 翻译成 .mel
    out = os.path.join(SCORES, base + '.mel')
    argv = [txt_path, '--out', out]
    if args.min_sharps:
        argv.append('--min-sharps')
    if args.bpm is not None:
        argv += ['--bpm', str(args.bpm)]

    import translate
    print('翻译成 .mel ……')
    if translate.main(argv) != 0:
        print('翻译失败：可手工修改上面的简谱文本（' + os.path.relpath(txt_path) +
              '）后，再运行 python translate.py 该文本。')
        return 1
    print('完成：' + os.path.relpath(out))
    print('可试听：python simulator.py ' + os.path.relpath(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
