"""网络曲谱检索（MIDI）：通过 scoreseek 搜索公开 MIDI 源并下载。

- 需要 `pip install scoreseek`（仅网络检索用到，不影响其它功能）。
- 结果来自公开 MIDI 站（bitmidi / midis101 / midiworld 等），
  属灰色/版权内容，仅供个人练习，请勿分发。
"""


class NetSearchError(RuntimeError):
    pass


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


def search_online(query, limit=10):
    """在线搜索，返回 [{title, composer, source, url, formats, ref}]（仅 MIDI 结果）。"""
    scoreseek = _client()
    refs = scoreseek.search(query, sources=['webmidi'], allow_copyrighted=True, limit=limit)
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
    """下载并返回本地 MIDI 文件路径。"""
    ref = hit['ref']
    try:
        return ref.fetch(fmt='mid')
    except Exception:
        return ref.fetch()
