"""简谱之家（jianpujia.com）检索与下载：搜中文简谱并下载曲谱图片。

站点为 EmpireCMS 服务端渲染、无公开 API：
- 搜索：POST /e/search/index.php（表单字段见 search()）
- 详情：GET /jianpu/<id>.html，正文里的 <img src="https://image.jianpujia.com/.../*.png">
  即曲谱图片（一首可能多页多图）
- 曲谱本体是 PNG 图片而非文本；转成 .mel 需先人工/视觉识别成简谱文本，
  本模块只负责「搜索 + 下载图片」，不自动翻译。

纯标准库实现（urllib + re），无需第三方依赖。
"""

import os
import re
import urllib.parse
import urllib.request

BASE = 'https://www.jianpujia.com'
SEARCH_URL = BASE + '/e/search/index.php'
IMG_HOST = 'image.jianpujia.com'

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

# 标题里带这些词的通常是伴奏/器乐改编谱（钢琴、吉他、和弦等），
# 主旋律被伴奏盖住、逐音吹出来像杂音，默认排到后面，优先取纯声乐简谱。
_ACCOMPANIMENT_KEYS = (
    '钢琴', '伴奏', '和弦', '吉他', '尤克里里', '口琴', '葫芦丝', '笛子',
    '二胡', '古筝', '琵琶', '小提琴', '大提琴', '电子琴', '弹唱', '指弹',
    '独奏', '演奏', '变奏', '器乐', '纯音乐', '合奏', '四手联弹',
)


def _open(url, data=None, referer=None):
    headers = dict(_HEADERS)
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', 'replace')


def _safe_name(s, maxlen=40):
    s = re.sub(r'[\\/:*?"<>|]+', '_', s).strip().strip('.')
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen] or 'untitled'


def _clean_title(t):
    """去掉标题尾部常见的「简谱/曲谱」后缀，便于做文件名。"""
    t = re.sub(r'(简谱|曲谱|歌谱|钢琴简谱)\s*$', '', t).strip()
    return t or '未命名'


def search(query, limit=10):
    """搜索简谱之家，返回 [{title, url, id}]（仅 /jianpu/ 简谱结果）。"""
    data = urllib.parse.urlencode({
        'show': 'title',
        'tempid': '1',
        'tbname': 'news',
        'mid': '1',
        'dopost': 'search',
        'keyboard': query,
    }).encode('utf-8')
    html = _open(SEARCH_URL, data=data, referer=BASE)

    out = []
    seen = set()
    for m in re.finditer(r'<a\s+href="(/jianpu/(\d+)\.html)"([^>]*)>(.*?)</a>', html, re.S):
        url, jid, attrs, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        if jid in seen:
            continue
        tm = re.search(r'title="([^"]*)"', attrs)
        title = tm.group(1).strip() if tm else re.sub(r'<[^>]+>', '', inner).strip()
        if not title:
            continue
        seen.add(jid)
        out.append({'title': title, 'url': BASE + url, 'id': jid})
        if len(out) >= limit:
            break
    # 稳定排序：伴奏/器乐改编谱排到后面，优先取纯声乐简谱（默认取第 1 条时更稳）
    out.sort(key=lambda h: any(k in h['title'] for k in _ACCOMPANIMENT_KEYS))
    return out


def detail_images(url):
    """打开详情页，返回曲谱图片 URL 列表（可能多页多图，已去重）。"""
    html = _open(url, referer=BASE)
    imgs = []
    for m in re.finditer(r'<img[^>]+src="(https?://' + re.escape(IMG_HOST) + r'/[^"]+)"', html):
        u = m.group(1)
        if u not in imgs:
            imgs.append(u)
    return imgs


def download(hit, dest_dir):
    """下载一首曲谱的全部图片到 dest_dir，返回本地路径列表。"""
    os.makedirs(dest_dir, exist_ok=True)
    urls = detail_images(hit['url'])
    if not urls:
        raise RuntimeError('未在详情页找到曲谱图片：' + hit['url'])

    base = _safe_name(_clean_title(hit['title']))
    paths = []
    for i, url in enumerate(urls, 1):
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.png'
        name = base if len(urls) == 1 else f'{base}_{i}'
        path = os.path.join(dest_dir, name + ext)
        req = urllib.request.Request(url, headers={
            'User-Agent': _HEADERS['User-Agent'],
            'Referer': hit['url'],
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(path, 'wb') as f:
            f.write(data)
        paths.append(path)
    return paths
