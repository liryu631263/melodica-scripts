"""三角洲行动 口风琴工具核心包。

- melodica.core      核心演奏引擎：音符模型 / 曲谱解析 / 音色合成 / 键鼠注入 / 播放调度
- melodica.translate 翻译与曲库底层：简谱解析 / MIDI 解析 / 网络曲谱检索
- melodica.library   本地曲库检索（扫描 / 别名 / 模糊匹配）

可运行入口脚本按类型分目录：
  main.py / start.py（根目录，控制入口）、cli/（命令行）、gui/（模拟器/引导）、
  web/（Web 前端）、tools/（诊断工具）。
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根目录

