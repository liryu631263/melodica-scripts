"""播放引擎：把 Note 序列按 BPM 定时注入键鼠。"""

import time

from input_backend import is_key_down, VK_F12


class Player:
    def __init__(self, backend, note_gap=0.03, stop_vk=VK_F12):
        self.backend = backend
        self.note_gap = note_gap  # 音符之间释放的间隙（秒），避免粘连
        self.stop_vk = stop_vk
        self._stopped = False

    def _stop_requested(self):
        if is_key_down(self.stop_vk):
            self._stopped = True
        return self._stopped

    def _wait_until(self, deadline):
        """等待到绝对时间点；期间响应停止热键。返回是否被停止。"""
        while time.monotonic() < deadline:
            if self._stop_requested():
                return False
            time.sleep(0.002)
        return True

    def play(self, notes, bpm, countdown=5.0):
        self._stopped = False
        spb = 60.0 / bpm  # 每拍秒数
        gap = min(self.note_gap, spb * 0.5)

        # 倒计时
        print(f"即将演奏 {len(notes)} 个音符，BPM={bpm:g}。")
        for i in range(int(countdown), 0, -1):
            print(f"  {i} 秒后开始…（按 F12 可随时停止）")
            if not self._wait_until(time.monotonic() + 1.0):
                print("已取消。")
                return
        print("开始演奏 —— 请确保游戏窗口在前台。")

        held_buttons = set()
        next_start = time.monotonic()
        completed = False
        try:
            for note in notes:
                # 等待到该音符开始
                if not self._wait_until(next_start):
                    return

                # 变调：更新鼠标按键状态
                target = set(note.mouse_buttons())
                for b in target - held_buttons:
                    self.backend.press_mouse(b)
                for b in held_buttons - target:
                    self.backend.release_mouse(b)
                held_buttons = target

                # 按下音符键（休止符不按键）
                scan = note.scan
                if scan is not None:
                    self.backend.press_key(scan)

                # 按住到结束（留出间隙）
                hold = max(0.0, note.beats * spb - gap)
                if not self._wait_until(next_start + hold):
                    return

                if scan is not None:
                    self.backend.release_key(scan)

                next_start += note.beats * spb
            completed = True
        finally:
            self.backend.release_all()
            if completed:
                print("演奏完成。")
            elif self._stopped:
                print("已停止。")
