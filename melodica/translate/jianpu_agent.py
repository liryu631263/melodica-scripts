"""简谱图片 → 识图 → 翻译成 .mel 的核心流程（供 agent.py CLI 与 web.py 复用）。

把「下载图片 → 视觉识图（GLM/DeepSeek/Qwen）→ 量化成 .mel」打包成一个函数，
CLI 与 Web 后端共用同一套逻辑，避免两处实现不一致。
"""

import os

from melodica import ROOT
from melodica.core.score import notes_to_text
from melodica.translate import jianpu, jianpujia, qwen_vl
from melodica.translate.quantize import events_to_notes

DOWNLOADS = os.path.join(ROOT, 'downloads')
SCORES = os.path.join(ROOT, 'scores')


def transcribe_hit(hit, min_sharps=False, bpm=None, model=None, translate=True, provider=None, mode=None):
    """下载并识图翻译一首简谱之家曲谱。

    参数 hit：jianpujia.search() 返回的条目 dict（含 title / url / id）。
    参数 provider：'glm' / 'deepseek' / 'qwen'（默认 None = 读环境变量 VL_PROVIDER）。
    参数 mode：'end2end' / 'twostep'（默认 None = 端到端）。
        - end2end：提示词带上口风琴映射规则，模型直接返回可演奏 JSON → 写 .mel（效果更好）
        - twostep：识图出简谱 JSON → 本地量化成 .mel（量化确定性，备选）
        默认端到端；可用 mode='twostep' 显式强制两步式（A/B 对比）。

    返回 dict：{title, text, txt_path, paths, mel_path, n_notes, bpm}
        - text / txt_path / paths 始终有值（text 为可读曲谱文本）
        - mel_path / n_notes / bpm 仅在 translate=True 时存在
    失败抛异常（qwen_vl.QwenError / jianpu.JianpuError / RuntimeError 等）。
    """
    dest = os.path.join(DOWNLOADS, 'jianpu')
    print('下载曲谱图片中……')
    paths = jianpujia.download(hit, dest)

    base = jianpujia._safe_name(jianpujia._clean_title(hit['title']))
    txt_path = os.path.join(dest, base + '.txt')
    prov = provider or qwen_vl.provider()
    if mode in ('end2end', 'mel', 'e2e'):
        use_end_to_end = True
    elif mode in ('twostep', 'jianpu', 'raw'):
        use_end_to_end = False
    else:
        # 默认端到端：模型直接做「看图 + 口风琴映射」，效果优于两步式；
        # 配合 GLM_REASONING=low，端到端实测 ~10s/页，速度不再是问题。
        use_end_to_end = True
    label = {'glm': 'GLM', 'deepseek': 'DeepSeek', 'qwen': 'Qwen'}.get(prov, prov)

    if use_end_to_end:
        print(f'{label} 视觉识别 {len(paths)} 页曲谱图片（端到端映射规则）……')
        data = qwen_vl.transcribe_mel_json(paths, model=model)
        notes = jianpu.mel_json_to_notes(data)
        # 去首尾休止，避免开头/结尾空等
        while notes and notes[0].is_rest:
            notes.pop(0)
        while notes and notes[-1].is_rest:
            notes.pop()
        out_bpm = bpm if bpm is not None else float(data.get('bpm') or 96.0)
        text = notes_to_text(notes, out_bpm)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)

        result = {'title': hit['title'], 'text': text, 'txt_path': txt_path, 'paths': paths}
        if not translate:
            return result

        mel_path = os.path.join(SCORES, base + '.mel')
        with open(mel_path, 'w', encoding='utf-8') as f:
            f.write(text)
        result.update({'mel_path': mel_path, 'n_notes': len(notes), 'bpm': out_bpm})
        print(f'已翻译 {len(notes)} 个音符 -> {os.path.relpath(mel_path)}（BPM={out_bpm:g}）。')
        return result

    # Qwen 两步路径：识图出简谱 JSON → 本地确定性量化
    print(f'{label} 视觉识别 {len(paths)} 页曲谱图片……')
    data = qwen_vl.transcribe_json(paths, model=model)

    text = jianpu.json_to_jianpu_text(data)
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

    print('翻译成 .mel ……')
    try:
        events, parsed_bpm = jianpu.json_to_events(data)
    except jianpu.JianpuError as e:
        raise RuntimeError(f'识图结果无法解析：{e}') from e

    out_bpm = bpm if bpm is not None else parsed_bpm
    notes = events_to_notes(events, min_sharps=min_sharps)
    # 去首尾休止（与 translate_cli.py 保持一致，避免开头/结尾空等）
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
