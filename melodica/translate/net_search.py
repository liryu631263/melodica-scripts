"""网络曲谱检索（MIDI）：通过 scoreseek 搜索公开 MIDI 源并下载。

- 需要 `pip install scoreseek`（仅网络检索用到，不影响其它功能）。
- 结果来自公开 MIDI 站（bitmidi / midis101 / midiworld 等），
  属灰色/版权内容，仅供个人练习，请勿分发。
- 可选本地源：Lakh MIDI 数据集（约 1.7 万首欧美流行/经典歌，234MB），
  放到项目下的 lakh/ 目录（或设置环境变量 MELODICA_LAKH 指向文件/目录）后自动启用。
  下载：python cli/search.py --download-lakh
"""

import os

from melodica import ROOT

LAKH_URL = "http://hog.ee.columbia.edu/craffel/lmd/clean_midi.tar.gz"
LAKH_DIR = os.path.join(ROOT, 'lakh')


class NetSearchError(RuntimeError):
    pass


def _lakh_path():
    """检测本地 Lakh 数据集的路径（tarball 或解压目录）；没有则返回 None。"""
    candidates = []
    env = os.environ.get('MELODICA_LAKH')
    if env:
        candidates.append(env)
    for name in ('clean_midi.tar.gz', 'clean_midi'):
        candidates.append(os.path.join(LAKH_DIR, name))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def lakh_available():
    """本地 Lakh 数据集是否可用。"""
    return _lakh_path() is not None


def _client():
    try:
        import scoreseek
        from scoreseek import register_source
        from scoreseek.sources import WebMidiSource
    except ImportError as e:
        raise NetSearchError('网络检索需要安装 scoreseek：pip install scoreseek') from e
    if 'webmidi' not in scoreseek.list_sources():
        register_source(WebMidiSource(timeout=15))
    return scoreseek


def _ensure_lakh(scoreseek):
    """若本地有 Lakh 数据集，注册 LakhMidiSource；返回源名或 None。"""
    if 'lakh' in scoreseek.list_sources():
        return 'lakh'
    path = _lakh_path()
    if not path:
        return None
    try:
        from scoreseek.sources import LakhMidiSource
        scoreseek.register_source(LakhMidiSource(path))
        return 'lakh'
    except Exception:
        return None


def search_online(query, limit=10):
    """在线搜索，返回 [{title, composer, source, url, formats, ref}]（仅 MIDI 结果）。

    会同时搜索公开 MIDI 站（webmidi）与本地 Lakh 数据集（若已下载）。
    """
    scoreseek = _client()
    sources = ['webmidi']
    if _ensure_lakh(scoreseek):
        sources.append('lakh')
    refs = scoreseek.search(query, sources=sources, allow_copyrighted=True, limit=limit)
    hits = []
    for r in refs:
        fmts = tuple(f.lower() for f in r.formats)
        if 'midi' not in fmts and 'mid' not in fmts:
            continue  # 只保留能直接转成 .mel 的 MIDI 结果
        hits.append({
            'title': r.title or '(无标题)',
            'composer': r.composer or '',
            'source': r.source,
            'url': r.url,
            'formats': fmts,
            'ref': r,
        })
    return hits


def download_midi(hit):
    """下载并返回本地 MIDI 文件路径（Lakh 命中则直接返回本地路径）。"""
    ref = hit['ref']
    try:
        return ref.fetch(fmt='mid')
    except Exception:
        return ref.fetch()


def download_lakh(path=None):
    """下载 Lakh MIDI 数据集（约 234MB）到 lakh/ 目录，返回 tarball 路径。"""
    import urllib.request

    dest = path or os.path.join(LAKH_DIR, 'clean_midi.tar.gz')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f'Lakh 数据集已存在：{dest}')
        return dest

    print(f'开始下载 Lakh MIDI 数据集（约 234MB，欧美流行/经典歌约 1.7 万首）：')
    print(f'  {dest}')

    def _hook(blocks, block_size, total):
        if total > 0:
            done = blocks * block_size
            pct = min(100, done * 100 // total)
            print(f'\r  下载中 {done // (1024 * 1024)}/{total // (1024 * 1024)} MB '
                  f'({pct}%)', end='', flush=True)

    urllib.request.urlretrieve(LAKH_URL, dest, reporthook=_hook)
    print('\n下载完成。')
    return dest


def no_result_hint(query):
    """搜索无结果时的引导提示（中文歌 / 未装 Lakh / 通用）。"""
    tips = []
    if any('一' <= ch <= '鿿' for ch in query):
        tips.append('中文歌可到「简谱之家」搜简谱图片：python cli/search.py 曲名 --jianpu')
        tips.append('或把简谱转成文本翻译：python cli/translate_cli.py 简谱.txt')
        tips.append('或试试英文名 / 拼音搜索')
    if not lakh_available():
        tips.append('可下载 Lakh 数据集扩充欧美流行/经典歌曲库：'
                    'python cli/search.py --download-lakh')
    tips.append('公开 MIDI 站以英文歌名 / 经典 / 游戏音乐为主')
    return '；'.join(tips) + '。'
