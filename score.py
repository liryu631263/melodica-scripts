"""曲谱解析：把简谱数字文本解析成 Note 序列。

格式（第一版，简谱数字风格）：
  - `#` 开头为注释（整行忽略）；`|` 为小节线（忽略）；音符以空白分隔。
  - 每个音符 token：`[前缀][0-8][:时值]`
      前缀：`-` 降八度、`+` 升八度、`#` 升半音（可组合，如 `-#` 表示降八度且升半音）
      数字：1-8（8 = 高音 1）；0 = 休止符
      时值：`:N` 拍数，默认 1 拍，支持小数（如 `:0.5`、`:2`）
  - `T=96` 设置速度 BPM（默认 96）。

示例：
    T=96
    # 小星星
    1 1 5 5 6 6 5:2 | 4 4 3 3 2 2 1:2
"""

import re

from melodica import Note

_TOKEN_RE = re.compile(r"^(?P<prefix>[-+#]*)(?P<degree>[0-8])(?::(?P<beats>\d+(?:\.\d+)?))?$")


class ScoreError(ValueError):
    """曲谱解析错误，附带行号与出错的 token。"""

    def __init__(self, message, line=None, token=None):
        super().__init__(message)
        self.line = line
        self.token = token

    def __str__(self):
        loc = f"（第 {self.line} 行）" if self.line else ""
        return f"{super().__str__()}{loc}"


def parse_score(text, default_bpm=96.0):
    """解析曲谱文本，返回 (notes, bpm)。"""
    notes = []
    bpm = default_bpm

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue

        m = re.match(r"^T\s*=\s*(\d+(?:\.\d+)?)\s*$", line, re.IGNORECASE)
        if m:
            bpm = float(m.group(1))
            continue

        for token in line.split():
            if token == '|':
                continue
            notes.append(_parse_token(token, lineno))

    if not notes:
        raise ScoreError("曲谱为空，没有解析到任何音符。")
    return notes, bpm


def _parse_token(token, lineno):
    m = _TOKEN_RE.match(token)
    if not m:
        raise ScoreError(f"无法识别的音符 token：{token!r}", line=lineno, token=token)

    prefix = m.group('prefix')
    degree = int(m.group('degree'))
    beats = float(m.group('beats')) if m.group('beats') else 1.0

    if beats <= 0:
        raise ScoreError(f"时值必须为正数：{token!r}", line=lineno, token=token)

    octave = -1 if '-' in prefix else (1 if '+' in prefix else 0)
    sharp = '#' in prefix

    return Note(degree=degree, octave=octave, sharp=sharp, beats=beats)


def load_score(path, default_bpm=96.0):
    """从文件读取并解析曲谱，返回 (notes, bpm)。"""
    with open(path, 'r', encoding='utf-8') as f:
        return parse_score(f.read(), default_bpm)


def notes_to_text(notes, bpm=None):
    """把 Note 序列序列化回 .mel 文本（parse_score 的逆操作）。"""
    lines = []
    if bpm is not None:
        lines.append(f"T={bpm:g}")
    row = []
    for n in notes:
        if n.is_rest:
            tok = '0'
        else:
            prefix = ('-' if n.octave == -1 else '+' if n.octave == 1 else '') + ('#' if n.sharp else '')
            tok = prefix + str(n.degree)
        if n.beats != 1.0:
            tok += f':{n.beats:g}'
        row.append(tok)
        if len(row) >= 8:
            lines.append(' '.join(row))
            row = []
    if row:
        lines.append(' '.join(row))
    return '\n'.join(lines) + '\n'
