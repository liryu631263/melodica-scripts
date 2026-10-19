"""键鼠注入自检：验证 SendInput 是否真的把按键/鼠标送达系统。

两种模式：
  auto —— 自动往返自检：注入「按下」后用 GetAsyncKeyState 确认系统确实收到，
          再注入「抬起」确认恢复，逐键 / 逐鼠标按键打印 PASS / FAIL。
  demo —— 人工可视化：倒计时后依次「打出」Z X C V B N M 到当前焦点窗口（如记事本），
          再左/右/中键各点一下，同时打印系统自检结果，供肉眼 + 系统双重确认。

说明：本脚本只能验证到「操作系统层面确实收到了输入」。游戏内是否生效还取决于
  - UIPI：游戏以管理员运行、脚本也要以管理员运行，否则低权限进程注入的输入会被拦；
  - 反作弊：ACE 是否拦截合成输入，需在游戏内实测。

用法：
    python tools/verify_input.py [auto|demo] [--interval 0.15]
"""

import argparse
import ctypes
import functools
import os
import sys
import time

# 本脚本位于 tools/ 子目录，先把仓库根加进 sys.path，保证能 import melodica
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from melodica.core.input_backend import Win32Backend, ensure_admin, is_key_down
from melodica.core.notes import DEGREE_TO_SCAN

# 虚拟键码：字母键与鼠标按键
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04

MAPVK_VSC_TO_VK = 3

user32 = ctypes.windll.user32
user32.MapVirtualKeyW.restype = ctypes.c_uint
user32.MapVirtualKeyW.argtypes = (ctypes.c_uint, ctypes.c_uint)

# 待测键位：(展示名, 扫描码) —— 与口风琴键位一一对应
KEYS = [
    ('Z(do)', DEGREE_TO_SCAN[1]),
    ('X(re)', DEGREE_TO_SCAN[2]),
    ('C(mi)', DEGREE_TO_SCAN[3]),
    ('V(fa)', DEGREE_TO_SCAN[4]),
    ('B(sol)', DEGREE_TO_SCAN[5]),
    ('N(la)', DEGREE_TO_SCAN[6]),
    ('M(si)', DEGREE_TO_SCAN[7]),
    ('逗号(高音1)', DEGREE_TO_SCAN[8]),
]

MOUSE = [
    ('左键(降八度)', 'left', VK_LBUTTON),
    ('右键(升八度)', 'right', VK_RBUTTON),
    ('中键(升半音)', 'middle', VK_MBUTTON),
]


def _vk_from_scan(scan):
    """扫描码 -> 虚拟键码（按当前键盘布局），供 GetAsyncKeyState 校验用。"""
    vk = user32.MapVirtualKeyW(scan, MAPVK_VSC_TO_VK)
    return vk or scan


def _roundtrip(down_fn, up_fn, vk, interval):
    """注入按下 -> 确认系统收到 -> 注入抬起 -> 确认系统恢复。返回 (收到按下, 已恢复)。"""
    down_fn()
    time.sleep(interval)
    got_down = is_key_down(vk)
    up_fn()
    time.sleep(interval)
    got_up = not is_key_down(vk)
    return got_down, got_up


def check_keys(backend, interval):
    rows = []
    for name, scan in KEYS:
        vk = _vk_from_scan(scan)
        down, up = _roundtrip(
            functools.partial(backend.press_key, scan),
            functools.partial(backend.release_key, scan),
            vk, interval,
        )
        rows.append((name, down, up))
    return rows


def check_mouse(backend, interval):
    rows = []
    for name, btn, vk in MOUSE:
        down, up = _roundtrip(
            functools.partial(backend.press_mouse, btn),
            functools.partial(backend.release_mouse, btn),
            vk, interval,
        )
        rows.append((name, down, up))
    return rows


def _print_table(title, rows):
    print(f"\n== {title} ==")
    ok = True
    for name, down, up in rows:
        state = 'PASS' if (down and up) else 'FAIL'
        if state == 'FAIL':
            ok = False
        detail = []
        if not down:
            detail.append('按下未送达')
        if not up:
            detail.append('抬起未恢复')
        suffix = ('  ' + '、'.join(detail)) if detail else ''
        print(f"  [{state}] {name}{suffix}")
    return ok


def run_auto(backend, interval):
    print("自动往返自检开始 —— 会真实地按下/抬起每个键与鼠标按键，请勿干预。")
    k_ok = _print_table('键盘（物理扫描码 -> 虚拟键校验）', check_keys(backend, interval))
    m_ok = _print_table('鼠标（左/右/中键）', check_mouse(backend, interval))
    backend.release_all()
    print("\n总结：", '全部通过 ✓' if (k_ok and m_ok) else '存在失败项 ✗')
    if not (k_ok and m_ok):
        print("提示：失败通常是 UIPI 权限问题 —— 请用管理员身份运行本脚本（游戏管理员运行时尤需如此）。")
    return 0 if (k_ok and m_ok) else 1


def run_demo(backend, interval):
    print("3 秒后开始：请把焦点切到记事本 / 输入框（或游戏），观察是否被「打出」/「点击」。")
    for i in range(3, 0, -1):
        print(f"  {i}…")
        time.sleep(1.0)

    print("\n—— 键盘：依次按下 8 个音键（Z X C V B N M 逗号）——")
    for name, scan in KEYS:
        vk = _vk_from_scan(scan)
        down, up = _roundtrip(
            functools.partial(backend.press_key, scan),
            functools.partial(backend.release_key, scan),
            vk, interval,
        )
        print(f"  {name:<14} 系统{'收到' if down else '未收到'}  {'已恢复' if up else '未恢复'}")

    print("\n—— 鼠标：左/右/中键各点一下（左键在文本里可见光标，右键/中键建议进游戏验证）——")
    for name, btn, vk in MOUSE:
        down, up = _roundtrip(
            functools.partial(backend.press_mouse, btn),
            functools.partial(backend.release_mouse, btn),
            vk, interval,
        )
        print(f"  {name:<14} 系统{'收到' if down else '未收到'}  {'已恢复' if up else '未恢复'}")

    backend.release_all()
    print("\n演示结束。")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description='键鼠注入自检（验证 SendInput 是否真正送达系统）')
    p.add_argument('mode', nargs='?', default='auto', choices=['auto', 'demo'],
                   help='auto=自动往返自检（默认）；demo=人工可视化演示')
    p.add_argument('--interval', type=float, default=0.15,
                   help='按下/抬起之间的间隔秒数（默认 0.15，太小可能漏检）')
    p.add_argument('--no-elevate', action='store_true',
                   help='不自动请求管理员权限（游戏管理员运行时可能无法注入）')
    args = p.parse_args(argv)

    if ensure_admin(args.no_elevate) == 'relaunched':
        return 0

    backend = Win32Backend()
    if args.mode == 'auto':
        return run_auto(backend, args.interval)
    return run_demo(backend, args.interval)


if __name__ == '__main__':
    sys.exit(main())
