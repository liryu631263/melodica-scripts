"""简谱文本解析：把常见简谱记号解析成（音高, 时值）序列。

支持的 ASCII 纯文本记号：
  调号   ：`1=C` / `1=F`（do 对应哪个音名，默认 1=C）
  速度   ：`T=96`
  音符   ：1-7；0 = 休止符
  八度   ：`'` 升一个八度（高音）、`,` 降一个八度（低音），如 `1'`、`5,`
  变音   ：`#` 升半音、`b` 降半音，写在数字前，如 `#4`、`b7`
  时值   ：默认 1 拍；`-` 每加一拍（`5-`=2 拍）；`_` 减半（`1_`=0.5 拍）；
           `.` 附点（×1.5，如 `5.` = 1.5 拍）
  小节线 ：`|`（忽略）
  注释   ：`#` 后跟空格或文字视为注释；`#数字` 视为升半音（见变音）

示例：
    1=C
    T=96
    1 1 5 5 6 6 5- | 4 4 3 3 2 2 1-
"""

import re
import sys

from melodica.core.notes import DEGREE_TO_SEMITONE

_TONE_TO_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

_KEY_RE = re.compile(r"^1\s*=\s*([A-Ga-g][#b]?)\b")
_TEMPO_RE = re.compile(r"^T\s*=\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_TOKEN_RE = re.compile(r"^(?P<acc>[#b]?)(?P<deg>[0-7])(?P<mod>[',_.-]*)$")

_MODIFIERS = set("'-_.,")
_NOTE_RE = re.compile(r"[#b]?[0-7][',_.-]*")


def normalize_jianpu(text):
    """清洗简谱文本（视觉识图/LLM 输出的常见噪声），返回可解析的干净文本。

    - 字母 `i`/`I` 常被误认为高音 do，还原成 `1'`（如 `i`→`1'`、`2i`→`2 1'`、`i7`→`1' 7`）
    - 把与数字分离的时值/八度记号并回（`5 -`→`5-`、`1 '`→`1'`）
    - 拆开被粘连的音符（`67`→`6 7`、`166`→`1 6 6`、`2_5`→`2_ 5`）

    只处理音符行；调号/速度/注释行原样保留。
    """
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or _KEY_RE.match(s) or _TEMPO_RE.match(s):
            out.append(s)
            continue
        if s.startswith('#') and not (len(s) > 1 and s[1].isdigit()):
            out.append(s)
            continue
        # 1. 高音 do 的字母 i/I 还原
        s = s.replace('I', "1'").replace('i', "1'")
        # 2. 孤立的修饰符 token 并回前一个音符
        toks = []
        for tok in s.split():
            if tok and set(tok) <= _MODIFIERS and toks and toks[-1] != '|':
                toks[-1] += tok
            else:
                toks.append(tok)
        # 3. 按音符边界拆开粘连
        merged = []
        for tok in toks:
            if tok == '|':
                merged.append(tok)
                continue
            pieces = _NOTE_RE.findall(tok)
            merged.extend(pieces if pieces else [tok])
        out.append(' '.join(merged))
    return '\n'.join(out)


class JianpuError(ValueError):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.line = line

    def __str__(self):
        return f"{super().__str__()}（第 {self.line} 行）" if self.line else super().__str__()


def parse_jianpu(text, default_bpm=96.0):
    """解析简谱文本，返回 (events, bpm)。events = [(pitch|None, beats), ...]。"""
    text = normalize_jianpu(text)
    tonic = 'C'
    bpm = default_bpm
    events = []
    skipped = 0

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        m = _KEY_RE.match(line)
        if m:
            tonic = m.group(1)[0].upper()
            continue
        m = _TEMPO_RE.match(line)
        if m:
            bpm = float(m.group(1))
            continue
        if line.startswith('#') and not (len(line) > 1 and line[1].isdigit()):
            continue  # 注释行

        for token in line.split():
            if token and set(token) <= {'|'}:
                continue  # 小节线 / 终止线（|、|| 等）
            try:
                events.append(_parse_token(token, tonic, lineno))
            except JianpuError:
                skipped += 1  # 残留的无法识别记号（歌词等）直接跳过，不中断整首翻译

    if not events:
        raise JianpuError("简谱为空，没有解析到任何音符。")
    if skipped:
        print(f"警告：已跳过 {skipped} 个无法识别的简谱记号。", file=sys.stderr)
    return events, bpm


def _parse_token(token, tonic, lineno):
    m = _TOKEN_RE.match(token)
    if not m:
        raise JianpuError(f"无法识别的简谱 token：{token!r}", line=lineno)

    acc = m.group('acc')
    deg = int(m.group('deg'))
    mod = m.group('mod')
    beats = _parse_beats(mod)

    if deg == 0:
        return (None, beats)  # 休止符

    oct_marks = mod.count("'") - mod.count(',')
    semitone = DEGREE_TO_SEMITONE[deg - 1]
    if acc == '#':
        semitone += 1
    elif acc == 'b':
        semitone -= 1
    pitch = 60 + _TONE_TO_PC[tonic] + 12 * oct_marks + semitone
    return (pitch, beats)


def _parse_beats(mod):
    beats = 1.0
    for ch in mod:
        if ch == '-':
            beats += 1.0
        elif ch == '_':
            beats *= 0.5
        elif ch == '.':
            beats *= 1.5
    return beats


def json_to_events(data):
    """把视觉模型返回的结构化 JSON dict 转成 (events, bpm)。

    events = [(pitch|None, beats), ...]，pitch 为绝对 MIDI 音高（与 parse_jianpu 同口径）。
    只做「调号 + 音级 + 八度 → 音高」的机械换算，不选调、不量化。
    """
    key = str(data.get('key', 'C') or 'C').strip()
    tonic = key[0].upper() if key else 'C'
    if tonic not in _TONE_TO_PC:
        tonic = 'C'
    bpm = float(data.get('bpm') or 96.0)
    events = []
    for it in data.get('notes') or []:
        if not isinstance(it, dict):
            continue
        try:
            d = int(it.get('d', 0))
            o = int(it.get('o', 0))
            b = float(it.get('b', 1.0) or 1.0)
        except (TypeError, ValueError):
            continue
        if b <= 0:
            b = 1.0
        if d == 0:
            events.append((None, b))
        elif 1 <= d <= 7:
            pitch = 60 + _TONE_TO_PC[tonic] + 12 * o + DEGREE_TO_SEMITONE[d - 1]
            events.append((pitch, b))
        # 非法音级直接跳过
    if not events:
        raise JianpuError("识图结果中没有解析到任何音符。")
    return events, bpm


def _beats_suffix(b):
    """把拍数渲染成简谱时值记号（近似，仅用于展示/存档）。"""
    if b == 1.0:
        return ''
    if b == 0.5:
        return '_'
    if b == 0.25:
        return '__'
    if b == 0.75:
        return '_.'
    if b == 1.5:
        return '.'
    if b == int(b) and b >= 2:
        return '-' * (int(b) - 1)
    return ''


def json_to_jianpu_text(data):
    """把视觉模型返回的 JSON dict 渲染成人类可读的简谱文本（供前端展示与 txt 存档）。"""
    key = str(data.get('key', 'C') or 'C').strip() or 'C'
    bpm = data.get('bpm', 96)
    lines = [f'1={key}', f'T={bpm:g}']
    row = []
    for it in data.get('notes') or []:
        if not isinstance(it, dict):
            continue
        try:
            d = int(it.get('d', 0))
            o = int(it.get('o', 0))
            b = float(it.get('b', 1.0) or 1.0)
        except (TypeError, ValueError):
            continue
        if d == 0:
            tok = '0'
        else:
            tok = str(d) + ("'" * o if o > 0 else ',' * (-o) if o < 0 else '')
        tok += _beats_suffix(b)
        row.append(tok)
        if len(row) >= 16:
            lines.append(' '.join(row))
            row = []
    if row:
        lines.append(' '.join(row))
    return '\n'.join(lines) + '\n'
