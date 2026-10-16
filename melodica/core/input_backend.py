"""键鼠注入后端：纯 ctypes 调用 Win32 SendInput（物理扫描码方式），零第三方依赖。

- 键盘用物理扫描码（KEYEVENTF_SCANCODE），与输入法/键盘布局无关，
  也更适合读原始键位的游戏（三角洲行动这类）。
- 停止热键用 GetAsyncKeyState 轮询，无需全局钩子、无需额外权限。

注意：
  1. 若游戏以管理员身份运行，请同样以管理员运行本脚本，否则系统 UIPI
     会拦截低权限进程注入的输入（SendInput 与 GetAsyncKeyState 都受影响）。
  2. 反作弊（ACE）是否会拦截合成输入，需在游戏内实测。
"""

import ctypes
from ctypes import wintypes

# ---- Win32 结构定义 ----
ULONG_PTR = ctypes.c_size_t

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (
        ('ki', KEYBDINPUT),
        ('mi', MOUSEINPUT),
        ('hi', HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ('type', wintypes.DWORD),
        ('u', _INPUTUNION),
    )


user32 = ctypes.windll.user32
user32.SendInput.restype = ctypes.c_uint
user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)

# 鼠标按键名 -> (按下标志, 抬起标志)
_MOUSE_FLAGS = {
    'left': (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    'right': (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    'middle': (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key_input(scan, up):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wScan = scan
    inp.u.ki.dwFlags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    return inp


def _mouse_input(button, up):
    down_flag, up_flag = _MOUSE_FLAGS[button]
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dwFlags = up_flag if up else down_flag
    return inp


class InputBackend:
    """输入后端接口。"""

    def press_key(self, scan):
        raise NotImplementedError

    def release_key(self, scan):
        raise NotImplementedError

    def press_mouse(self, button):
        raise NotImplementedError

    def release_mouse(self, button):
        raise NotImplementedError

    def release_all(self):
        """释放所有本后端仍在按住的键。默认不追踪，子类按需实现。"""


class Win32Backend(InputBackend):
    """基于 SendInput 的实现。"""

    def __init__(self):
        self._held_keys = set()
        self._held_buttons = set()

    def press_key(self, scan):
        _send(_key_input(scan, up=False))
        self._held_keys.add(scan)

    def release_key(self, scan):
        _send(_key_input(scan, up=True))
        self._held_keys.discard(scan)

    def press_mouse(self, button):
        _send(_mouse_input(button, up=False))
        self._held_buttons.add(button)

    def release_mouse(self, button):
        _send(_mouse_input(button, up=True))
        self._held_buttons.discard(button)

    def release_all(self):
        for scan in list(self._held_keys):
            self.release_key(scan)
        for button in list(self._held_buttons):
            self.release_mouse(button)


def create_backend(name='win32'):
    if name == 'win32':
        return Win32Backend()
    raise ValueError(f"未知输入后端：{name}")


def is_key_down(vk):
    """轮询某个虚拟键是否被按下（全局，无需焦点）。返回 bool。"""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


VK_F12 = 0x7B
