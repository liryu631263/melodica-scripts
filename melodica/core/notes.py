"""三角洲行动 口风琴 —— 音符模型与键位映射。

游戏内吹奏模式键位（PC 端，建议英文输入法）：
  音符键 : Z X C V B N M ,  ->  1 2 3 4 5 6 7 8（8 = 高音 1）
  变调键 : 按住鼠标左键 = 降八度；按住右键 = 升八度；按住中键 = 升半音。

本模块用「键盘物理扫描码」表示键位（与输入法/键盘布局无关），见 DEGREE_TO_SCAN。
"""

from dataclasses import dataclass

# 音级 1-8 对应的物理键（PS/2 Set 1 扫描码），8 = 高音 1（逗号键）
DEGREE_TO_SCAN = {
    1: 0x2C,  # Z
    2: 0x2D,  # X
    3: 0x2E,  # C
    4: 0x2F,  # V
    5: 0x30,  # B
    6: 0x31,  # N
    7: 0x32,  # M
    8: 0x33,  # ,（即 < 键）
}

# 用于展示
DEGREE_TO_LABEL = {1: 'Z', 2: 'X', 3: 'C', 4: 'V', 5: 'B', 6: 'N', 7: 'M', 8: ','}

# 每个音级相对 1（do）的半音数（自然大调音阶），index 0 = degree 1
DEGREE_TO_SEMITONE = (0, 2, 4, 5, 7, 9, 11, 12)


@dataclass
class Note:
    degree: int          # 1-8（8 = 高音 1）；0 = 休止符
    octave: int = 0      # -1 降八度 / 0 自然 / +1 升八度
    sharp: bool = False  # 升半音（按住鼠标中键）
    beats: float = 1.0   # 时值（拍数）

    @property
    def is_rest(self) -> bool:
        return self.degree == 0

    @property
    def scan(self):
        """对应的键盘扫描码；休止符返回 None。"""
        return None if self.is_rest else DEGREE_TO_SCAN[self.degree]

    @property
    def label(self) -> str:
        return '休止' if self.is_rest else DEGREE_TO_LABEL[self.degree]

    def mouse_buttons(self):
        """该音符需要按住的鼠标按键列表（'left'/'right'/'middle'）。"""
        btns = []
        if self.octave == -1:
            btns.append('left')
        elif self.octave == 1:
            btns.append('right')
        if self.sharp:
            btns.append('middle')
        return btns

    def midi(self):
        """映射为 MIDI 音高（自然大调 + 八度 + 半音）。基准：自然 1 = C5 = MIDI 72。
        休止符返回 None。此映射为后续「任意歌曲翻译成口风琴」模块做准备。"""
        if self.is_rest:
            return None
        return 72 + 12 * self.octave + (1 if self.sharp else 0) + DEGREE_TO_SEMITONE[self.degree - 1]


def pitch_to_note(midi):
    """把绝对 MIDI 音高映射为口风琴音符编码（midi() 的逆运算），优先少用鼠标变调。

    规则：优先落在自然音区（八度 0，不按鼠标）；C/C♯ 处于八度边界时，
    用「高音 1」键（音级 8）代替升八度，进一步减少需要按住的鼠标键。
    """
    midi = int(midi)
    pc = midi % 12
    sharp = pc in (1, 3, 6, 8, 10)
    degree = {0: 1, 1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5, 9: 6, 10: 6, 11: 7}[pc]
    semi = DEGREE_TO_SEMITONE[degree - 1]
    octave = (midi - 72 - (1 if sharp else 0) - semi) // 12
    # C(0) 与 C♯(1) 存在「高音 1」键的等价编码，选鼠标负担更小的那个
    if pc in (0, 1):
        oct8 = (midi - 84 - pc) // 12
        if abs(oct8) < abs(octave):
            return Note(degree=8, octave=oct8, sharp=sharp)
    return Note(degree=degree, octave=octave, sharp=sharp)
