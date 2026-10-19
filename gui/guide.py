"""口风琴「手动演示」—— 节奏大师式下落音符引导（纯视觉、不注入任何按键）。

给担心自动注入封号的玩家：把一个 .mel 曲谱画成 8 轨下落的音符块，
玩家自己照着在游戏里按（Z X C V B N M = do~si，逗号 , = 高音 do；八度靠鼠标左/右键）。

- 无边框 + 始终置顶 + 贴在屏幕下沿，可浮在（无边框/窗口化全屏的）游戏窗口上方。
- 不发声、不注入按键，纯视觉引导。
- 块的下边沿触到判定线 = 开始按；块高度 = 该音时值，越长越要按住。
- 块上标记：↑ = 按住鼠标右键（升八度）、↓ = 按住鼠标左键（降八度）、# = 按住中键（升半音）。

用法：
    python gui/guide.py 曲谱.mel [--bpm N] [--countdown S] [--speed PX/S] [--height PX] [--no-topmost]

操作：
    点击轨道区 / 空格 = 开始（重开）；按住顶部灰色条拖动 = 移动窗口；Esc = 退出。
    提示：游戏需用「无边框窗口化」模式，否则独占全屏会盖住本悬浮条。
"""

import argparse
import os
import sys
import time
import tkinter as tk

# 本脚本位于 gui/ 子目录，先把仓库根加进 sys.path，保证能 import melodica
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from melodica.core.notes import DEGREE_TO_LABEL
from melodica.core.score import load_score, ScoreError

LANES = 8
LABELS = ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',']
LANE_COLORS = ['#e74c3c', '#e67e22', '#f1c40f', '#2ecc71', '#3498db', '#9b59b6', '#1abc9c', '#95a5a6']

BG = '#10151c'
GRID = '#2a3440'
HIT_LINE = '#ffffff'
TEXT = '#e5e7eb'
MUTED = '#8b98a5'

GRIP_H = 26      # 顶部拖动条 + 键名标签高度
HIT_MARGIN = 26  # 判定线距底边

MOD_HINT = {'↑': '按住鼠标右键', '↓': '按住鼠标左键', '#': '按住鼠标中键'}


def _lane_marker(note):
    """把一个 Note 转成 (lane, 键名, 标记列表)。degree 8（高音 do）落在第 8 轨（逗号键）。"""
    lane = note.degree - 1
    key = DEGREE_TO_LABEL[note.degree]
    markers = []
    if note.octave == 1:
        markers.append('↑')
    elif note.octave == -1:
        markers.append('↓')
    if note.sharp:
        markers.append('#')
    return lane, key, markers


class FallingGuide:
    def __init__(self, root, notes, bpm, opts, title=''):
        self.root = root
        self.notes = notes
        self.bpm = bpm
        self.opts = opts
        self.title = title

        self._events = []  # (lane, key, markers, start_t, end_t, beats)
        spb = 60.0 / bpm
        t = 0.0
        for n in notes:
            if not n.is_rest:
                lane, key, markers = _lane_marker(n)
                self._events.append((lane, key, markers, t, t + n.beats * spb, n.beats))
            t += n.beats * spb
        self._total = t

        self._state = 'idle'  # idle / countdown / playing / done
        self._state_start = 0.0
        self._play_start = 0.0
        self._dragging = False
        self._press_x = self._press_y = 0
        self._win_x = self._win_y = 0

        self._build()
        self._bind()
        self._tick()

    # ---------- 窗口 ----------
    def _build(self):
        self.root.overrideredirect(True)
        if not self.opts.no_topmost:
            self.root.wm_attributes('-topmost', True)
        self.root.configure(bg=BG)

        self.w = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.h = self.opts.height
        self.hit_y = self.h - HIT_MARGIN
        self.root.geometry(f'{self.w}x{self.h}+0+{sh - self.h - self.opts.y_offset}')

        self.canvas = tk.Canvas(self.root, width=self.w, height=self.h,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

    def _bind(self):
        self.root.bind('<space>', lambda e: self._start())
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)

    # ---------- 交互 ----------
    def _on_press(self, e):
        self._press_x, self._press_y = e.x_root, e.y_root
        self._win_x, self._win_y = self.root.winfo_x(), self.root.winfo_y()
        self._dragging = False

    def _on_drag(self, e):
        dx, dy = e.x_root - self._press_x, e.y_root - self._press_y
        if not self._dragging and (abs(dx) + abs(dy)) > 5:
            self._dragging = True
        if self._dragging:
            self.root.geometry(f'+{self._win_x + dx}+{self._win_y + dy}')

    def _on_release(self, e):
        if self._dragging:
            return
        if e.y > GRIP_H:  # 点击轨道区才触发开始/重开，顶部条留给拖动
            self._start()

    def _start(self):
        if self._state in ('playing', 'countdown'):
            return
        self._state = 'countdown'
        self._state_start = time.monotonic()

    # ---------- 循环 ----------
    def _tick(self):
        if self._state == 'countdown':
            if time.monotonic() - self._state_start >= self.opts.countdown:
                self._state = 'playing'
                self._play_start = time.monotonic()
        elif self._state == 'playing':
            if time.monotonic() - self._play_start >= self._total + 0.4:
                self._state = 'done'
        self._render()
        self.root.after(16, self._tick)

    def _render(self):
        c = self.canvas
        c.delete('all')
        w, h = self.w, self.h
        lane_w = w / LANES

        # 轨道分隔线 + 键名标签
        for i in range(LANES):
            cx = (i + 0.5) * lane_w
            c.create_text(cx, GRIP_H / 2, text=LABELS[i], fill=LANE_COLORS[i],
                          font=('Consolas', 12, 'bold'))
            if i:
                c.create_line(i * lane_w, GRIP_H, i * lane_w, h, fill=GRID)
        c.create_line(0, GRIP_H, w, GRIP_H, fill=GRID)
        c.create_line(0, self.hit_y, w, self.hit_y, fill=HIT_LINE, width=2)

        if self._state == 'idle':
            c.create_text(w / 2, h / 2, text='点击轨道区或按空格开始', fill=TEXT,
                          font=('Consolas', 20, 'bold'))
            c.create_text(w / 2, h / 2 + 34, text=self.title, fill=MUTED,
                          font=('Microsoft YaHei', 11))
        elif self._state == 'countdown':
            remaining = self.opts.countdown - (time.monotonic() - self._state_start)
            num = max(1, int(remaining) + 1)
            c.create_text(w / 2, h / 2, text=str(num), fill='#fff',
                          font=('Consolas', 56, 'bold'))
        elif self._state == 'playing':
            self._render_notes(c, lane_w, time.monotonic() - self._play_start)
        elif self._state == 'done':
            c.create_text(w / 2, h / 2, text='完成 · 点击或空格重开', fill=TEXT,
                          font=('Consolas', 18, 'bold'))

    def _render_notes(self, c, lane_w, elapsed):
        speed = self.opts.speed
        h = self.h
        current = None
        for ev in self._events:
            lane, key, markers, start_t, end_t, beats = ev
            if start_t > elapsed:  # 未来，下落中
                bottom_y = self.hit_y - (start_t - elapsed) * speed
                if bottom_y <= h and (start_t - elapsed) <= self.opts.lead:
                    self._draw_block(c, lane_w, lane, key, markers, beats, bottom_y, hit=False)
            elif elapsed < end_t:  # 当前正在演奏
                current = ev
                self._draw_block(c, lane_w, lane, key, markers, beats, self.hit_y, hit=True)

        # 顶部条：标题 + 当前该按什么
        c.create_text(8, GRIP_H / 2, text=self.title, anchor='w', fill=MUTED,
                      font=('Microsoft YaHei', 10))
        if current is not None:
            _, key, markers, _, _, _ = current
            hint = ' '.join(MOD_HINT[m] for m in markers if m in MOD_HINT)
            text = f'现在按 {key}' + (f'（{hint}）' if hint else '')
        else:
            text = ''
        c.create_text(self.w - 8, GRIP_H / 2, text=text, anchor='e', fill='#fff',
                      font=('Microsoft YaHei', 11, 'bold'))

    def _draw_block(self, c, lane_w, lane, key, markers, beats, bottom_y, hit):
        color = LANE_COLORS[lane]
        spb = 60.0 / self.bpm
        bh = max(10.0, beats * spb * self.opts.speed)  # 块高 = 时值(秒) × 速度
        x0 = lane * lane_w + 4
        x1 = (lane + 1) * lane_w - 4
        top_y = bottom_y - bh
        c.create_rectangle(x0, top_y, x1, bottom_y, fill=color,
                           outline='#ffffff' if hit else '#000000',
                           width=2 if hit else 1)
        c.create_text((x0 + x1) / 2, (top_y + bottom_y) / 2,
                      text=''.join(markers) + key, fill='#fff',
                      font=('Consolas', 13, 'bold'))


def main(argv=None):
    p = argparse.ArgumentParser(description='口风琴手动演示：节奏大师式下落音符（纯视觉，不注入按键）')
    p.add_argument('score', help='.mel 曲谱文件')
    p.add_argument('--bpm', type=float, default=None, help='覆盖曲谱速度（默认读 T=）')
    p.add_argument('--countdown', type=float, default=4.0, help='开始前倒计时秒数（默认 4）')
    p.add_argument('--speed', type=float, default=150.0, help='下落速度 px/秒（默认 150）')
    p.add_argument('--lead', type=float, default=4.0, help='音符最多提前多少秒出现（默认 4）')
    p.add_argument('--height', type=int, default=360, help='悬浮条高度 px（默认 360）')
    p.add_argument('--y-offset', type=int, default=0, help='底边再上移多少 px（避免遮任务栏）')
    p.add_argument('--no-topmost', action='store_true', help='关闭始终置顶（调试用）')
    args = p.parse_args(argv)

    try:
        notes, bpm = load_score(args.score)
    except (OSError, ScoreError) as e:
        print(f'载入失败：{e}')
        return 1
    if args.bpm:
        bpm = args.bpm

    title = os.path.splitext(os.path.basename(args.score))[0]
    root = tk.Tk()
    FallingGuide(root, notes, bpm, args, title=title)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
