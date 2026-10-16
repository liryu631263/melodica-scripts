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

from melodica.core.notes import DEGREE_TO_SEMITONE

_TONE_TO_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

_KEY_RE = re.compile(r"^1\s*=\s*([A-Ga-g][#b]?)\b")
_TEMPO_RE = re.compile(r"^T\s*=\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_TOKEN_RE = re.compile(r"^(?P<acc>[#b]?)(?P<deg>[0-7])(?P<mod>[',_.-]*)$")


class JianpuError(ValueError):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.line = line

    def __str__(self):
        return f"{super().__str__()}（第 {self.line} 行）" if self.line else super().__str__()


def parse_jianpu(text, default_bpm=96.0):
    """解析简谱文本，返回 (events, bpm)。events = [(pitch|None, beats), ...]。"""
    tonic = 'C'
    bpm = default_bpm
    events = []

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
            if token == '|':
                continue
            events.append(_parse_token(token, tonic, lineno))

    if not events:
        raise JianpuError("简谱为空，没有解析到任何音符。")
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
