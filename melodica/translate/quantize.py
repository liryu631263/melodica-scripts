"""自然音阶量化：把（音高, 拍）事件序列翻译成口风琴可演奏的 Note 序列（音级 1-8）。

游戏口风琴有 do~si 七个自然音 + 高音 do（逗号键，degree 8）；升半音不可靠，因此把旋律
量化到最近的大调音阶：先选一个误差最小的调，再把每个音就近归到该调的自然音级，
最后整八度居中；高音 do 映射到 degree 8（逗号键），其余音级 1-7。

本模块从 CLI（translate_cli.py）抽入包内，供 CLI 与两步式识图翻译（jianpu_agent）共用，
避免包内反向 import 顶层 CLI 脚本。
"""

from melodica.core.notes import MAJOR_PC, Note, pitch_to_natural_note

# 自然音区（不按鼠标）对应的 MIDI 范围：do(72) ~ si(83)
_SWEET_LO, _SWEET_HI = 72, 83
# 推荐范围：do(72) ~ 高音si(95)，即「自然音区 + 升八度」，尽量少用降八度
_RANGE_LO, _RANGE_HI = 72, 95


def _snap_to_major(pc):
    """返回 (最近的大调音级半音, 误差半音数)，大调主音视为 0。"""
    best = min(MAJOR_PC, key=lambda m: min((pc - m) % 12, (m - pc) % 12))
    err = min((pc - best) % 12, (best - pc) % 12)
    return best, err


def _circ_delta(a, b):
    """音级 a 到 b 的最小有符号半音位移（-6..+5）。"""
    return ((b - a + 6) % 12) - 6


def _octave_fit(pitches):
    """按整八度平移，把旋律中心对齐到自然音区，尽量落在 do~高音si 内（少用降八度）。"""
    lo, hi = min(pitches), max(pitches)
    center = (lo + hi) / 2
    shift = int(round(((_SWEET_LO + _SWEET_HI) / 2 - center) / 12)) * 12
    if lo + shift < _RANGE_LO:
        shift += 12
    elif hi + shift > _RANGE_HI:
        shift -= 12
    return shift


def events_to_notes(events, grid=0.25, transpose=0, min_sharps=False):
    """把 (pitch|None, beats) 事件序列翻译成自然音阶 Note 序列（音级 1-8 + 八度，无半音）。

    游戏口风琴有 do~si 七个自然音 + 高音 do（逗号键）；升半音不可靠，因此这里把旋律
    量化到最近的大调音阶：先选一个误差最小的调，再把每个音就近归到该调的自然音级，
    最后整八度居中；高音 do 映射到 degree 8（逗号键），其余音级 1-7。
    """
    # 1. 时值量化
    ev = []
    for p, d in events:
        q = round(d / grid) * grid if d > 0 else grid
        ev.append((p, max(grid, q)))

    # 2. 手动移调（半音，作用于量化前的原始音高）
    if transpose:
        ev = [(None if p is None else p + transpose, d) for p, d in ev]

    # 3. 量化到自然大调音阶（选调 + 就近归音级，再转回 C 大调）
    pitches = [p for p, _ in ev if p is not None]
    if pitches:
        k = min(range(12), key=lambda T: sum(_snap_to_major((p - T) % 12)[1] for p in pitches))
        snapped = {}
        for p in set(pitches):
            best, _ = _snap_to_major((p - k) % 12)
            target = (k + best) % 12
            delta = _circ_delta(p % 12, target)
            snapped[p] = p + delta - k   # 就近归音级，并整体移到 C 大调
        shift = _octave_fit(list(snapped.values()))
        ev = [(None if p is None else snapped[p] + shift, d) for p, d in ev]

    # 4. 音高映射（自然音阶）
    notes = []
    for p, d in ev:
        if p is None:
            notes.append(Note(degree=0, beats=d))
        else:
            n = pitch_to_natural_note(p)
            n.beats = d
            notes.append(n)
    return notes
