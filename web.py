"""口风琴工具 Web 界面 —— 本地浏览器里检索 → 翻译 → 试听/演奏。

纯标准库实现（http.server），无需 Flask 等依赖。只监听 127.0.0.1。

用法：
    python web.py [--port 8000]
    然后浏览器打开 http://127.0.0.1:8000

功能与 app.py（Tkinter 版）一致：
  - 本地曲库 / 联网 MIDI 检索
  - 浏览器内试听（服务器合成 WAV 返回 <audio>）
  - 游戏演奏（服务器 subprocess 启动 main.py）
  - 查看曲谱 / 入曲库 / 上传翻译导入
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import library
import translate
import urllib.request

from melodica.core import audio
from melodica.core.score import load_score
from melodica.translate import jianpujia, jianpu_agent, net_search

ROOT = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(ROOT, 'downloads')

INDEX_HTML = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>口风琴工具 · 三角洲行动</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0;
         background: #f4f5f7; color: #1f2937; }
  header { background: #1e293b; color: #fff; padding: 14px 20px; }
  header h1 { margin: 0; font-size: 20px; }
  header p { margin: 4px 0 0; font-size: 13px; color: #94a3b8; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 16px; }
  .bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  input[type=text] { flex: 1; min-width: 200px; padding: 8px 10px; font-size: 14px;
                     border: 1px solid #cbd5e1; border-radius: 6px; }
  select, button { padding: 8px 12px; font-size: 14px; border-radius: 6px;
                   border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
  button.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
  button:hover { filter: brightness(1.05); }
  #list { margin-top: 12px; border: 1px solid #e2e8f0; border-radius: 8px;
          background: #fff; overflow: hidden; }
  .row { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; cursor: pointer;
         display: flex; gap: 10px; align-items: baseline; }
  .row:hover { background: #f8fafc; }
  .row.sel { background: #eff6ff; }
  .row .title { flex: 1; font-weight: 600; }
  .row .meta { color: #64748b; font-size: 13px; white-space: nowrap; }
  .row .src { font-size: 12px; color: #fff; background: #94a3b8; padding: 1px 7px;
              border-radius: 10px; }
  .row .src.online { background: #0ea5e9; }
  .row .src.jianpu { background: #d97706; }
  #panel { margin-top: 14px; display: flex; gap: 14px; flex-wrap: wrap; }
  #panel > * { flex: 1 1 400px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }
  .card h2 { margin: 0 0 10px; font-size: 15px; }
  #score { font-family: Consolas, monospace; font-size: 13px; white-space: pre;
           overflow: auto; max-height: 320px; background: #f8fafc; padding: 10px;
           border-radius: 6px; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  #status { margin-top: 12px; color: #475569; font-size: 13px; min-height: 1.2em; }
  #status.err { color: #dc2626; }
  #import { margin-top: 14px; }
  #import input[type=file] { font-size: 13px; }
  .muted { color: #94a3b8; }
</style>
</head>
<body>
<header>
  <h1>🎺 口风琴工具 · 三角洲行动</h1>
  <p>检索 → 翻译 → 试听 / 进游戏演奏，全程本地运行。</p>
</header>
<div class="wrap">
  <div class="bar">
    <input type="text" id="q" placeholder="输入曲名 / 拼音 / 英文名…">
    <select id="mode">
      <option value="local">本地曲库</option>
      <option value="online">联网 MIDI</option>
      <option value="jianpu">简谱</option>
    </select>
    <button class="primary" onclick="search()">搜索</button>
    <button onclick="search(true)">刷新</button>
  </div>

  <div id="list"></div>
  <div id="status" class="muted">就绪。</div>

  <div id="panel" style="display:none">
    <div class="card">
      <h2 id="score-title">曲谱</h2>
      <div id="score"></div>
      <div class="actions">
        <span id="vlOpts" style="display:none">
          <select id="provider">
            <option value="">模型：自动</option>
            <option value="glm">GLM（glm-5.3-flash）</option>
            <option value="deepseek">DeepSeek（deepseek-flash）</option>
            <option value="qwen">Qwen（qwen3-vl-plus）</option>
          </select>
          <select id="xmode">
            <option value="end2end">端到端（推荐·准）</option>
            <option value="twostep">两步式（备选）</option>
          </select>
        </span>
        <button id="ocrBtn" onclick="jianpuTranslate()" style="display:none">🖼 识图翻译</button>
        <button class="primary" onclick="preview()">▶ 试听</button>
        <button onclick="gamePlay()">🎮 游戏演奏</button>
        <button onclick="toLibrary()">✚ 入曲库</button>
        <button onclick="download()">⬇ 下载 .mel</button>
      </div>
      <audio id="audio" controls style="margin-top:10px;width:100%"></audio>
    </div>

    <div class="card" id="import">
      <h2>翻译导入</h2>
      <p class="muted">上传 MIDI / 简谱文本，翻译后自动入曲库。</p>
      <input type="file" id="file" accept=".mid,.midi,.txt,.jianpu,.jp,.text">
    </div>
  </div>
</div>

<script>
let items = [];
let selected = null;
let lastHint = null;
let audio = document.getElementById('audio');

async function search(refresh) {
  const q = refresh ? '' : document.getElementById('q').value.trim();
  const mode = document.getElementById('mode').value;
  if (!q && !refresh) { list(); return; }
  setStatus(refresh ? '刷新中…' : (mode === 'online' ? '联网搜索中，请稍候…' : mode === 'jianpu' ? '简谱搜索中，请稍候…' : '搜索中…'));
  try {
    const ep = mode === 'jianpu' ? '/api/jianpu' : '/api/search';
    const r = await fetch(ep + '?q=' + encodeURIComponent(q) + '&mode=' + mode);
    const d = await r.json();
    items = d.items; lastHint = d.hint;
    render();
    setStatus('共 ' + items.length + ' 条结果，点击选中。');
  } catch (e) { setStatus('搜索失败：' + e, true); }
}

async function list() {
  const d = await (await fetch('/api/search?q=&mode=local')).json();
  items = d.items; lastHint = d.hint;
  render();
  setStatus('共 ' + items.length + ' 首本地曲谱。');
}

function render() {
  const el = document.getElementById('list');
  if (!items.length) {
    el.innerHTML = '<div class="row muted">无匹配结果。' +
      (lastHint ? '<br>' + esc(lastHint) : '') + '</div>';
    return;
  }
  el.innerHTML = items.map((it, i) =>
    '<div class="row" id="row' + i + '" onclick="select(' + i + ')">' +
    '<span class="title">' + esc(it.title) + '</span>' +
    '<span class="src ' + it.kind + '">' + esc(it.source) + '</span>' +
    '<span class="meta">' + (it.n_notes ?? '—') + ' 音符 · BPM ' + (it.bpm ?? '—') + '</span>' +
    '</div>').join('');
}

async function select(i) {
  selected = items[i];
  document.querySelectorAll('.row').forEach(r => r.classList.remove('sel'));
  document.getElementById('row' + i).classList.add('sel');
  document.getElementById('panel').style.display = 'flex';
  document.getElementById('score-title').textContent = '曲谱 · ' + selected.title;
  const sc = document.getElementById('score');
  document.getElementById('ocrBtn').style.display = selected.kind === 'jianpu' ? '' : 'none';
  document.getElementById('vlOpts').style.display = selected.kind === 'jianpu' ? '' : 'none';
  if (selected.kind === 'jianpu') {
    sc.innerHTML = '<img src="/api/jianpu_img?id=' + encodeURIComponent(selected.id) + '&n=0" alt="简谱" style="max-width:100%">';
    setStatus('这是简谱图片，点「识图翻译」自动转成可演奏曲谱。');
    return;
  }
  if (selected.kind === 'local') { sc.textContent = '(点击「查看曲谱」或试听时载入)'; return; }
  setStatus('联网下载翻译中，请稍候…');
  try {
    const r = await fetch('/api/score?id=' + encodeURIComponent(selected.id));
    const d = await r.json();
    sc.textContent = d.text;
    setStatus('已解析 ' + d.n_notes + ' 个音符。');
  } catch (e) { setStatus('下载/翻译失败：' + e, true); }
}

async function jianpuTranslate() {
  if (!selected) return;
  const ocrBtn = document.getElementById('ocrBtn');
  const provider = document.getElementById('provider').value;
  const xmode = document.getElementById('xmode').value;
  ocrBtn.disabled = true;
  setStatus('识图翻译中（' + (provider || '自动') + ' 视觉识别，请稍候）…');
  try {
    const r = await fetch('/api/jianpu_translate?id=' + encodeURIComponent(selected.id) +
      '&provider=' + encodeURIComponent(provider) + '&mode=' + encodeURIComponent(xmode), { method: 'POST' });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    document.getElementById('score').textContent = d.text;
    selected = { id: d.id, title: d.title, kind: 'local', source: '简谱翻译', n_notes: d.n_notes, bpm: d.bpm };
    ocrBtn.style.display = 'none';
    setStatus('翻译完成：' + d.n_notes + ' 个音符，可试听 / 演奏 / 下载。');
  } catch (e) { setStatus('识图翻译失败：' + e, true); }
  finally { ocrBtn.disabled = false; }
}

async function preview() {
  if (!selected) return;
  setStatus('试听合成中…');
  try {
    const r = await fetch('/api/audio?id=' + encodeURIComponent(selected.id));
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { const d = await r.json(); if (d && d.error) msg = d.error; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await r.blob();
    if (audio.src && audio.src.startsWith('blob:')) URL.revokeObjectURL(audio.src);
    audio.src = URL.createObjectURL(blob);
    await audio.play();
    setStatus('试听中…');
  } catch (e) {
    setStatus('试听失败：' + (e && e.message || e), true);
  }
}

async function gamePlay() {
  if (!selected) return;
  setStatus('启动游戏演奏（请切到游戏窗口，F12 随时停）…');
  await post('/api/play?id=' + encodeURIComponent(selected.id));
}

async function toLibrary() {
  if (!selected) return;
  const r = await post('/api/library?id=' + encodeURIComponent(selected.id));
  setStatus(r.message || '已入库。');
}

function download() {
  if (!selected) return;
  window.location = '/api/download?id=' + encodeURIComponent(selected.id);
}

document.getElementById('file').addEventListener('change', async e => {
  const f = e.target.files[0];
  if (!f) return;
  setStatus('上传翻译中，请稍候…');
  try {
    const r = await fetch('/api/import?name=' + encodeURIComponent(f.name),
                          { method: 'POST', body: f });
    const d = await r.json();
    setStatus('已翻译并入库：' + d.out);
    search(true);
  } catch (err) { setStatus('导入失败：' + err, true); }
});

async function post(url) {
  const r = await fetch(url, { method: 'POST' });
  return r.json();
}

function setStatus(msg, err) {
  const s = document.getElementById('status');
  s.textContent = msg;
  s.className = err ? 'err' : 'muted';
}

function esc(s) { return String(s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

document.getElementById('q').addEventListener('keydown', e => {
  if (e.key === 'Enter') search();
});
list();
</script>
</body>
</html>
"""


def _safe_name(s, maxlen=40):
    import re
    s = re.sub(r'[\\/:*?"<>|]+', '_', s).strip().strip('.')
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen] or 'untitled'


class Handler(BaseHTTPRequestHandler):
    server_version = 'MelodicaWeb/1.0'

    def log_message(self, fmt, *args):
        sys.stderr.write('[web] %s - %s\n' % (self.address_string(), fmt % args))

    # ---------- 工具 ----------
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, obj)

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    def _resolve(self, iid):
        """返回指定 id 对应的 .mel 本地路径；联网项会先下载并翻译。"""
        item = self.server.registry.get(iid)
        if item is None:
            raise KeyError('无效的曲目 id')
        if item['kind'] == 'local':
            return item['path']
        if iid in self.server.resolved:
            return self.server.resolved[iid]
        hit = self.server.hits[iid]
        mid = net_search.download_midi(hit)
        os.makedirs(DOWNLOADS, exist_ok=True)
        mel = os.path.join(DOWNLOADS, _safe_name(item['title']) + '.mel')
        if translate.main([mid, '--out', mel, '--min-sharps']) != 0:
            raise RuntimeError('翻译失败，见服务器控制台。')
        self.server.resolved[iid] = mel
        return mel

    # ---------- 路由 ----------
    def do_GET(self):
        path = urlparse(self.path).path
        q = self._query()
        try:
            if path == '/':
                self._send(200, INDEX_HTML, 'text/html; charset=utf-8')
            elif path == '/api/search':
                self._search(q)
            elif path == '/api/jianpu':
                self._jianpu_search(q)
            elif path == '/api/jianpu_img':
                self._jianpu_img(q)
            elif path == '/api/score':
                self._score(q)
            elif path == '/api/audio':
                self._audio(q)
            elif path == '/api/download':
                self._download(q)
            else:
                self._json(404, {'error': 'not found'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        q = self._query()
        try:
            if path == '/api/play':
                mel = self._resolve(q.get('id', [''])[0])
                subprocess.Popen([sys.executable, os.path.join(ROOT, 'main.py'), mel], cwd=ROOT)
                self._json(200, {'ok': True, 'message': '已启动游戏演奏。'})
            elif path == '/api/library':
                mel = self._resolve(q.get('id', [''])[0])
                item = self.server.registry[q['id'][0]]
                dest = os.path.join(library.LIB_DIR, _safe_name(item['title']) + '.mel')
                shutil.copyfile(mel, dest)
                self._json(200, {'ok': True, 'message': '已入库：' + dest})
            elif path == '/api/import':
                self._import(q)
            elif path == '/api/jianpu_translate':
                self._jianpu_translate(q)
            else:
                self._json(404, {'error': 'not found'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    # ---------- 具体接口 ----------
    def _search(self, q):
        mode = q.get('mode', ['local'])[0]
        query = q.get('q', [''])[0].strip()
        reg = self.server.registry = {}
        hits = self.server.hits = {}
        self.server.resolved = {}
        if mode == 'online':
            try:
                items = net_search.search_online(query, limit=10) if query else []
            except net_search.NetSearchError as e:
                self._json(200, {'items': [], 'hint': str(e)})
                return
            hint = net_search.no_result_hint(query) if (query and not items) else None
            out = []
            for i, h in enumerate(items):
                iid = 'o%d' % i
                reg[iid] = {'id': iid, 'title': h['title'], 'kind': 'online',
                            'source': '网络', 'n_notes': None, 'bpm': None}
                hits[iid] = h
                out.append(reg[iid])
            self._json(200, {'items': out, 'hint': hint})
        else:
            items = library.search(query, library.scan()) if query else library.scan()
            out = []
            for i, it in enumerate(items):
                iid = 'l%d' % i
                reg[iid] = {'id': iid, 'title': it['title'], 'kind': 'local',
                            'source': '本地', 'n_notes': it['n_notes'], 'bpm': it['bpm'],
                            'path': it['path']}
                out.append(reg[iid])
            self._json(200, {'items': out, 'hint': None})

    def _jianpu_search(self, q):
        query = q.get('q', [''])[0].strip()
        hits = self.server.jianpu_hits = {}
        if not query:
            self._json(200, {'items': [], 'hint': None})
            return
        try:
            items = jianpujia.search(query, limit=10)
        except Exception as e:
            self._json(200, {'items': [], 'hint': '简谱之家搜索失败：' + str(e)})
            return
        out = []
        for i, h in enumerate(items):
            iid = 'j%d' % i
            hits[iid] = h
            out.append({'id': iid, 'title': h['title'], 'kind': 'jianpu',
                        'source': '简谱之家', 'n_notes': None, 'bpm': None})
        hint = None if items else '简谱之家未找到相关简谱，可换个关键词（曲名 / 歌手）。'
        self._json(200, {'items': out, 'hint': hint})

    def _jianpu_img(self, q):
        hit = self.server.jianpu_hits.get(q.get('id', [''])[0])
        if hit is None:
            self._json(404, {'error': '无效的简谱 id'})
            return
        try:
            urls = jianpujia.detail_images(hit['url'])
        except Exception as e:
            self._json(500, {'error': str(e)})
            return
        if not urls:
            self._json(404, {'error': '未找到曲谱图片'})
            return
        try:
            n = int(q.get('n', ['0'])[0] or '0')
        except ValueError:
            n = 0
        url = urls[min(n, len(urls) - 1)]
        req = urllib.request.Request(url, headers={
            'User-Agent': jianpujia._HEADERS['User-Agent'],
            'Referer': hit['url'],
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                ctype = r.headers.get('Content-Type', 'image/png')
        except Exception as e:
            self._json(500, {'error': '图片下载失败：' + str(e)})
            return
        self._send(200, data, ctype)

    def _jianpu_translate(self, q):
        iid = q.get('id', [''])[0]
        hit = self.server.jianpu_hits.get(iid)
        if hit is None:
            self._json(404, {'error': '无效的简谱 id'})
            return
        provider = q.get('provider', [''])[0].strip() or None
        mode = q.get('mode', [''])[0].strip() or None
        try:
            result = jianpu_agent.transcribe_hit(hit, min_sharps=True,
                                                 provider=provider, mode=mode)
        except Exception as e:
            self._json(500, {'error': str(e)})
            return
        nid = 'jp' + iid
        self.server.registry[nid] = {
            'id': nid, 'title': result['title'], 'kind': 'local',
            'source': '简谱翻译', 'n_notes': result['n_notes'], 'bpm': result['bpm'],
            'path': result['mel_path'],
        }
        self._json(200, {
            'ok': True, 'id': nid, 'title': result['title'],
            'text': result['text'], 'n_notes': result['n_notes'], 'bpm': result['bpm'],
        })

    def _score(self, q):
        mel = self._resolve(q.get('id', [''])[0])
        notes, bpm = load_score(mel)
        with open(mel, encoding='utf-8') as f:
            text = f.read()
        self._json(200, {'text': text, 'n_notes': len(notes), 'bpm': bpm})

    def _audio(self, q):
        mel = self._resolve(q.get('id', [''])[0])
        notes, bpm = load_score(mel)
        data, _ = audio.score_wav(notes, bpm)
        self._send(200, data, 'audio/wav')

    def _download(self, q):
        mel = self._resolve(q.get('id', [''])[0])
        with open(mel, 'rb') as f:
            data = f.read()
        name = os.path.basename(mel)
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename="%s"' % name)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _import(self, q):
        name = q.get('name', [''])[0] or 'import'
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        ext = os.path.splitext(name)[1].lower()
        if ext not in ('.mid', '.midi', '.txt', '.jianpu', '.jp', '.text'):
            raise ValueError('不支持的文件类型：' + (ext or '(无扩展名)'))
        os.makedirs(DOWNLOADS, exist_ok=True)
        tmp = os.path.join(DOWNLOADS, '_import_' + _safe_name(name, 30))
        with open(tmp, 'wb') as f:
            f.write(data)
        base = os.path.splitext(os.path.basename(name))[0]
        out = os.path.join(library.LIB_DIR, _safe_name(base) + '.mel')
        if translate.main([tmp, '--out', out, '--min-sharps']) != 0:
            raise RuntimeError('翻译失败，见服务器控制台。')
        try:
            os.remove(tmp)
        except OSError:
            pass
        self._json(200, {'ok': True, 'out': out})


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description='口风琴工具 Web 界面')
    p.add_argument('--port', type=int, default=8000, help='监听端口（默认 8000）')
    p.add_argument('--host', default='127.0.0.1', help='监听地址（默认 127.0.0.1）')
    args = p.parse_args(argv)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.registry = {}
    srv.hits = {}
    srv.resolved = {}
    srv.jianpu_hits = {}
    print(f'口风琴工具 Web 界面：http://{args.host}:{args.port}')
    print('按 Ctrl+C 退出。')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已退出。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
