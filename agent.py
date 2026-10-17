"""口风琴「翻译 agent」：简谱之家搜曲 → 下载图片 → 视觉识图（GLM/DeepSeek/Qwen）→ 翻译成 .mel。

用法：
    python agent.py 夜曲                  # 搜索、选曲、下载、识图、翻译（默认 GLM）
    python agent.py 夜曲 --pick 1         # 直接取第 1 条搜索结果
    python agent.py 夜曲 --no-translate   # 只下载图片 + 识图出简谱文本，不翻译
    python agent.py 夜曲 --min-sharps     # 翻译时自动选调，少用升半音
    python agent.py 夜曲 --provider qwen  # 换 Qwen 模型
    python agent.py 夜曲 --mode twostep   # 强制两步式（只看图+本地量化），与端到端对比

依赖：需设置视觉模型 API Key（环境变量，或项目根目录 .env 文件里写）。
      默认 GLM：VL_PROVIDER=glm + GLM_API_KEY（视觉模型 glm-5.3-flash，可用 GLM_MODEL 覆盖）。
      DeepSeek：VL_PROVIDER=deepseek + DEEPSEEK_API_KEY（模型 deepseek-flash）。
      Qwen：VL_PROVIDER=qwen + DASHSCOPE_API_KEY（模型 qwen3-vl-plus）。
"""

import argparse
import os
import sys

from melodica.translate import jianpujia, jianpu_agent

ROOT = os.path.dirname(os.path.abspath(__file__))


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
    p = argparse.ArgumentParser(description='口风琴翻译 agent：搜简谱 → 下载图片 → 视觉识图 → 翻译 .mel')
    p.add_argument('keyword', nargs='?', default=None, help='曲名（省略则交互输入）')
    p.add_argument('--pick', type=int, default=None, help='直接选第 N 条搜索结果')
    p.add_argument('--limit', type=int, default=10, help='搜索结果数上限（默认 10）')
    p.add_argument('--provider', default=None, choices=('glm', 'deepseek', 'qwen'),
                   help='视觉模型厂商（默认读环境变量 VL_PROVIDER，缺省 glm）')
    p.add_argument('--mode', default=None, choices=('auto', 'end2end', 'twostep'),
                   help='翻译模式：auto=按厂商自动；end2end=模型直接出可演奏曲谱；twostep=只看图+本地量化（A/B 对比）')
    p.add_argument('--model', default=None, help='视觉模型名（GLM 默认 glm-5.3-flash，DeepSeek 默认 deepseek-flash，Qwen 默认 qwen3-vl-plus）')
    p.add_argument('--no-translate', action='store_true', help='只下载图片 + 识图出简谱文本，不翻译成 .mel')
    p.add_argument('--min-sharps', action='store_true', help='翻译时自动选调，尽量少用升半音')
    p.add_argument('--bpm', type=float, default=None, help='翻译时覆盖速度')
    args = p.parse_args(argv)

    kw = args.keyword or input('请输入曲名：').strip()
    if not kw:
        print('未输入曲名。')
        return 0

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

    try:
        result = jianpu_agent.transcribe_hit(
            sel, min_sharps=args.min_sharps, bpm=args.bpm,
            model=args.model, translate=not args.no_translate,
            provider=args.provider, mode=args.mode)
    except Exception as e:
        print(f'失败：{e}')
        return 1

    for p in result['paths']:
        print('  图片：' + os.path.relpath(p))
    print('\n----- 识别出的简谱文本 -----')
    print(result['text'])
    print('---------------------------')
    print('已存文本：' + os.path.relpath(result['txt_path']))

    if args.no_translate:
        return 0

    print('完成：' + os.path.relpath(result['mel_path']))
    print('可试听：python simulator.py ' + os.path.relpath(result['mel_path']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
