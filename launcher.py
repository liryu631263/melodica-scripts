"""口风琴工具启动器 —— 菜单式选择要运行的模块。

双击 start.bat（或在项目目录运行 `python launcher.py`）即可。
菜单会根据当前分支自动显示可用的前端（app.py / web.py）。
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _reconfigure_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass


def _run(*args):
    """在本项目目录下用当前解释器运行一个入口脚本。"""
    return subprocess.call([sys.executable, *args], cwd=ROOT)


def _play():
    path = input('曲谱文件路径（如 scores/twinkle.mel）：').strip()
    if path:
        _run('main.py', path)
    else:
        print('未输入路径，返回菜单。')


def _translate():
    path = input('输入文件路径（.mid/.midi/.txt/.jianpu/.jp）：').strip()
    if path:
        _run('translate.py', path, '--min-sharps')
    else:
        print('未输入路径，返回菜单。')


def main():
    _reconfigure_utf8()
    while True:
        options = [
            ('模拟器试听（GUI，不封号）', lambda: _run('simulator.py')),
            ('交互检索（本地/联网 → 试听/演奏）', lambda: _run('search.py')),
            ('游戏演奏（选 .mel 曲谱进游戏）', _play),
            ('曲谱翻译（MIDI/简谱 → .mel）', _translate),
            ('本地曲库列表', lambda: _run('library.py')),
        ]
        if os.path.exists(os.path.join(ROOT, 'app.py')):
            options.append(('桌面前端（Tkinter）', lambda: _run('app.py')))
        if os.path.exists(os.path.join(ROOT, 'web.py')):
            options.append(('网页前端（浏览器）', lambda: _run('web.py')))

        print()
        print('=== 口风琴工具 · 三角洲行动 ===')
        for i, (label, _fn) in enumerate(options, 1):
            print(f'  [{i}] {label}')
        print('  [0] 退出')

        choice = input('选择：').strip() or '0'
        if choice == '0':
            break
        try:
            idx = int(choice)
        except ValueError:
            idx = -1
        if 1 <= idx <= len(options):
            options[idx - 1][1]()
        else:
            print('无效选择，请重试。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
