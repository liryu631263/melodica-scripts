"""简谱图片 → 识图 → 翻译成 .mel 的核心流程（供 agent.py CLI 与 web.py 复用）。

把「下载图片 → Qwen 视觉识图 → 写简谱文本 → translate 成 .mel」打包成一个函数，
CLI 与 Web 后端共用同一套逻辑，避免两处实现不一致。
"""

import os

from melodica import ROOT
from melodica.translate import jianpujia, qwen_vl

DOWNLOADS = os.path.join(ROOT, 'downloads')
SCORES = os.path.join(ROOT, 'scores')


def transcribe_hit(hit, min_sharps=False, bpm=None, model=None, translate=True):
    """下载并识图翻译一首简谱之家曲谱。

    参数 hit：jianpujia.search() 返回的条目 dict（含 title / url / id）。

    返回 dict：{title, text, txt_path, paths, mel_path, n_notes, bpm}
        - text / txt_path / paths 始终有值
        - mel_path / n_notes / bpm 仅在 translate=True 时存在
    失败抛异常（qwen_vl.QwenError / RuntimeError 等）。
    """
    dest = os.path.join(DOWNLOADS, 'jianpu')
    print('下载曲谱图片中……')
    paths = jianpujia.download(hit, dest)

    parts = []
    for i, p in enumerate(paths, 1):
        print(f'Qwen 视觉识别第 {i}/{len(paths)} 页……')
        parts.append(qwen_vl.transcribe(p, model=model))
    text = '\n\n'.join(t for t in parts if t)

    base = jianpujia._safe_name(jianpujia._clean_title(hit['title']))
    txt_path = os.path.join(dest, base + '.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text + '\n')

    result = {
        'title': hit['title'],
        'text': text,
        'txt_path': txt_path,
        'paths': paths,
    }
    if not translate:
        return result

    mel_path = os.path.join(SCORES, base + '.mel')
    argv = [txt_path, '--out', mel_path]
    if min_sharps:
        argv.append('--min-sharps')
    if bpm is not None:
        argv += ['--bpm', str(bpm)]

    import translate as translate_cli
    print('翻译成 .mel ……')
    if translate_cli.main(argv) != 0:
        raise RuntimeError('翻译失败，见上方控制台输出。')

    from melodica.core.score import load_score
    notes, out_bpm = load_score(mel_path)
    result.update({'mel_path': mel_path, 'n_notes': len(notes), 'bpm': out_bpm})
    return result
