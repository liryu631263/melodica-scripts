"""启动后端（web/web.py）并自动打开前端页面。

用法：
    python start.py

等效于运行 `python web/web.py`，只是额外用默认浏览器自动打开前端页面。
"""

import os
import subprocess
import sys
import threading
import webbrowser

from melodica import ROOT

HOST = '127.0.0.1'
PORT = 8000
URL = f'http://{HOST}:{PORT}'
WEB = os.path.join(ROOT, 'web', 'web.py')


def main(argv=None):
    # 等服务器起来后自动打开浏览器（避免在端口就绪前打开）
    timer = threading.Timer(0.6, webbrowser.open, args=(URL,))
    timer.daemon = True
    timer.start()
    return subprocess.call([sys.executable, WEB] + (argv or []), cwd=ROOT)


if __name__ == '__main__':
    sys.exit(main())
