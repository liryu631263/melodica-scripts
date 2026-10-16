"""口风琴模拟器（GUI）—— 不用进游戏、不会封号的虚拟口风琴。

功能：
  - 用鼠标点击琴键，或用键盘 Z/X/C/V/B/N/M/, 演奏，带声音。
  - 变调：自然 / 降八度(左键) / 升八度(右键) / 升半音(中键)。
  - 载入 .mel 曲谱后自动演奏，琴键实时高亮。
  - 复用 melodica.py / score.py / audio.py，与真实口风琴同一套音符模型。

用法：
    python simulator.py [曲谱文件]
"""

import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import audio
from melodica import Note
from score import load_score, ScoreError

DEGREES = (1, 2, 3, 4, 5, 6, 7, 8)  # 8 = 高音 1
KEY_LABELS = {1: 'Z', 2: 'X', 3: 'C', 4: 'V', 5: 'B', 6: 'N', 7: 'M', 8: ','}
NOTE_NAMES = {1: 'do', 2: 're', 3: 'mi', 4: 'fa', 5: 'sol', 6: 'la', 7: 'si', 8: '高音 do'}
_KEYMAP = {'z': 1, 'x': 2, 'c': 3, 'v': 4, 'b': 5, 'n': 6, 'm': 7, 'comma': 8, 'less': 8}

KEY_BG = '#e8e8e8'
KEY_ACTIVE = '#f6c453'
MANUAL_TAP_SECONDS = 0.6


class MelodicaSimulator:
    def __init__(self, root):
        self.root = root
        root.title('口风琴模拟器 · 三角洲行动')
        self.octave_var = tk.IntVar(value=0)       # -1/0/1
        self.sharp_var = tk.BooleanVar(value=False)
        self.bpm_var = tk.StringVar(value='96')
        self.path_var = tk.StringVar(value='')
        self.status_var = tk.StringVar(value='点击琴键或按 Z~, 演奏；也可载入曲谱后点播放。')

        self.notes = []
        self._playing = False
        self._play_start = 0.0
        self._intervals = []  # [(start, end, degree)] 自动演奏时的音轨
        self._total = 0.0
        self._key_buttons = {}

        self._build_ui()
        self._bind_keys()

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill='x', padx=8, pady=6)
        tk.Label(top, text='曲谱:').pack(side='left')
        tk.Entry(top, textvariable=self.path_var, width=34).pack(side='left', padx=4)
        tk.Button(top, text='浏览…', command=self._browse).pack(side='left', padx=2)
        tk.Button(top, text='载入', command=self._load).pack(side='left', padx=2)
        tk.Label(top, text='BPM:').pack(side='left', padx=(10, 0))
        tk.Entry(top, textvariable=self.bpm_var, width=5).pack(side='left', padx=2)

        ctrl = tk.Frame(self.root)
        ctrl.pack(fill='x', padx=8)
        tk.Button(ctrl, text='▶ 播放曲谱', command=self._play).pack(side='left', padx=2)
        tk.Button(ctrl, text='■ 停止', command=self._stop).pack(side='left', padx=2)

        mod = tk.Frame(self.root)
        mod.pack(fill='x', padx=8, pady=6)
        tk.Label(mod, text='变调(模拟鼠标):').pack(side='left')
        tk.Radiobutton(mod, text='自然', variable=self.octave_var, value=0).pack(side='left', padx=2)
        tk.Radiobutton(mod, text='降八度(左键)', variable=self.octave_var, value=-1).pack(side='left', padx=2)
        tk.Radiobutton(mod, text='升八度(右键)', variable=self.octave_var, value=1).pack(side='left', padx=2)
        tk.Checkbutton(mod, text='升半音(中键)', variable=self.sharp_var).pack(side='left', padx=6)

        keys = tk.Frame(self.root)
        keys.pack(padx=8, pady=6)
        for i, deg in enumerate(DEGREES):
            b = tk.Button(
                keys,
                text=f'{KEY_LABELS[deg]}\n{NOTE_NAMES[deg]}',
                width=5, height=3, font=('Consolas', 12, 'bold'),
                bg=KEY_BG, activebackground=KEY_ACTIVE, relief='raised',
                command=lambda d=deg: self._tap(d),
            )
            b.grid(row=0, column=i, padx=2)
            self._key_buttons[deg] = b

        tk.Label(self.root, textvariable=self.status_var, anchor='w').pack(
            fill='x', padx=8, pady=4)

    # ---------- 事件 ----------
    def _bind_keys(self):
        self.root.bind('<KeyPress>', self._on_key)

    def _on_key(self, event):
        if isinstance(self.root.focus_get(), tk.Entry):
            return  # 正在输入路径/速度，不触发演奏
        deg = _KEYMAP.get(event.keysym.lower())
        if deg is not None:
            self._tap(deg)
            return 'break'

    def _browse(self):
        path = filedialog.askopenfilename(
            title='选择曲谱',
            filetypes=[('曲谱', '*.mel *.txt'), ('所有文件', '*.*')],
        )
        if path:
            self.path_var.set(path)
            self._load()

    def _load(self):
        path = self.path_var.get().strip()
        if not path:
            return
        try:
            notes, bpm = load_score(path)
        except (OSError, ScoreError) as e:
            messagebox.showerror('载入失败', str(e))
            return
        self.notes = notes
        self.bpm_var.set(str(int(bpm)) if float(bpm).is_integer() else f'{bpm:g}')
        self.status_var.set(f'已载入 {len(notes)} 个音符，BPM={bpm:g}。点击 ▶ 播放。')

    def _tap(self, degree):
        note = Note(degree=degree, octave=self.octave_var.get(), sharp=self.sharp_var.get())
        data = audio.note_wav(note.midi(), MANUAL_TAP_SECONDS)
        audio.play_wav(data, async_play=True)
        self._flash(degree)
        self.status_var.set(f'{NOTE_NAMES[degree]}  [{KEY_LABELS[degree]}]  MIDI={note.midi()}')

    def _flash(self, degree):
        b = self._key_buttons.get(degree)
        if b is None:
            return
        b.config(bg=KEY_ACTIVE)
        self.root.after(120, lambda: b.config(bg=KEY_BG))

    # ---------- 自动演奏 ----------
    def _play(self):
        if not self.notes:
            messagebox.showinfo('提示', '请先载入曲谱。')
            return
        self._stop()
        try:
            bpm = float(self.bpm_var.get() or 96)
        except ValueError:
            bpm = 96.0
        if bpm <= 0:
            bpm = 96.0

        spb = 60.0 / bpm
        gap = min(0.03, spb * 0.5)
        data, _ = audio.score_wav(self.notes, bpm, note_gap=0.03)

        # 计算每个音符的时间区间（用于高亮）
        self._intervals = []
        t = 0.0
        for n in self.notes:
            end = t + n.beats * spb
            if not n.is_rest:
                self._intervals.append((t, max(t, end - gap), n.degree))
            t = end
        self._total = t

        self._playing = True
        self._play_start = time.monotonic()
        audio.play_wav(data, async_play=True)
        self.status_var.set(f'演奏中…（BPM={bpm:g}）')
        self._tick()

    def _tick(self):
        if not self._playing:
            return
        elapsed = time.monotonic() - self._play_start
        active = set()
        for s, e, d in self._intervals:
            if s <= elapsed < e:
                active.add(d)
        for deg, b in self._key_buttons.items():
            b.config(bg=KEY_ACTIVE if deg in active else KEY_BG)
        if elapsed < self._total + 0.2:
            self.root.after(30, self._tick)
        else:
            self._finish()

    def _stop(self):
        audio.stop_all()
        self._playing = False
        self._reset_keys()
        self.status_var.set('已停止。')

    def _finish(self):
        self._playing = False
        self._reset_keys()
        self.status_var.set('演奏完成。')

    def _reset_keys(self):
        for b in self._key_buttons.values():
            b.config(bg=KEY_BG)


def main(argv=None):
    root = tk.Tk()
    app = MelodicaSimulator(root)
    args = sys.argv[1:] if argv is None else argv
    if args:
        app.path_var.set(args[0])
        app._load()
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
