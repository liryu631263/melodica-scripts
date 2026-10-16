"""启动后端（web.py）并自动打开前端页面。

用法：
    python start.py

等效于运行 `python web.py`，只是额外用默认浏览器自动打开前端页面。
"""

import sys
import threading
import webbrowser

import web

HOST = '127.0.0.1'
PORT = 8000
URL = f'http://{HOST}:{PORT}'


def main(argv=None):
    # 等服务器起来后自动打开浏览器（避免在端口就绪前打开）
    timer = threading.Timer(0.6, webbrowser.open, args=(URL,))
    timer.daemon = True
    timer.start()
    return web.main(argv)


if __name__ == '__main__':
    sys.exit(main())
