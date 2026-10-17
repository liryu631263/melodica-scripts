"""简谱图片 → 识图 → 翻译成 .mel 的核心流程（供 agent.py CLI 与 web.py 复用）。

把「下载图片 → Qwen 视觉识图输出结构化 JSON → 本地量化成 .mel」打包成一个函数，
CLI 与 Web 后端共用同一套逻辑，避免两处实现不一致。
"""

import os

from melodica import ROOT
from melodica.translate import jianpu, jianpujia, qwen_vl

DOWNLOADS = os.path.join(ROOT, 'downloads')
SCORES = os.path.join(ROOT, 'scores')


def transcribe_hit(hit, min_sharps=False, bpm=None, model=None, translate=True):
    """下载并识图翻译一首简谱之家曲谱。

    参数 hit：jianpujia.search() 返回的条目 dict（含 title / url / id）。

    返回 dict：{title, text, txt_path, paths, mel_path, n_notes, bpm}
        - text / txt_path / paths 始终有值（text 为可读简谱文本）
        - mel_path / n_notes / bpm 仅在 translate=True 时存在
    失败抛异常（qwen_vl.QwenError / jianpu.JianpuError / RuntimeError 等）。
    """
    dest = os.path.join(DOWNLOADS, 'jianpu')
    print('下载曲谱图片中……')
    paths = jianpujia.download(hit, dest)

    print(f'Qwen 视觉识别 {len(paths)} 页曲谱图片……')
    data = qwen_vl.transcribe_json(paths, model=model)

    base = jianpujia._safe_name(jianpujia._clean_title(hit['title']))
    text = jianpu.json_to_jianpu_text(data)
    txt_path = os.path.join(dest, base + '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text)

    result = {
        'title': hit['title'],
        'text': text,
        'txt_path': txt_path,
        'paths': paths,
    }
    if not translate:
        return result

    # 本地量化：JSON → 音高事件 → 自然音阶量化（确定性，无静默错音）
    from melodica.core.score import notes_to_text
    import translate as translate_cli

    print('翻译成 .mel ……')
    try:
        events, parsed_bpm = jianpu.json_to_events(data)
    except jianpu.JianpuError as e:
        raise RuntimeError(f'识图结果无法解析：{e}') from e

    out_bpm = bpm if bpm is not None else parsed_bpm
    notes = translate_cli.events_to_notes(events, min_sharps=min_sharps)
    # 去首尾休止（与 translate.py 保持一致，避免开头/结尾空等）
    while notes and notes[0].is_rest:
        notes.pop(0)
    while notes and notes[-1].is_rest:
        notes.pop()

    mel_path = os.path.join(SCORES, base + '.mel')
    with open(mel_path, 'w', encoding='utf-8') as f:
        f.write(notes_to_text(notes, out_bpm))

    result.update({'mel_path': mel_path, 'n_notes': len(notes), 'bpm': out_bpm})
    print(f'已翻译 {len(notes)} 个音符 -> {os.path.relpath(mel_path)}（BPM={out_bpm:g}）。')
    return result
