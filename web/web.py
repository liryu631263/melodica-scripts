"""口风琴工具 Web 界面 —— 本地浏览器里检索 → 翻译 → 试听/演奏。

纯标准库实现（http.server），无需 Flask 等依赖。只监听 127.0.0.1。

用法：
    python web/web.py [--port 8000]
    然后浏览器打开 http://127.0.0.1:8000

功能：
  - 本地曲库 / 联网 MIDI 检索
  - 浏览器内试听（服务器合成 WAV 返回 <audio>）
  - 游戏演奏（服务器 subprocess 启动 main.py）
  - 查看曲谱 / 入曲库 / 上传翻译导入
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 本脚本位于 web/ 子目录，先把仓库根加进 sys.path，保证能 import melodica
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request

from melodica import ROOT
from melodica import library
from melodica.core import audio
from melodica.core.score import load_score
from melodica.translate import jianpujia, jianpu_agent, net_search

DOWNLOADS = os.path.join(ROOT, 'downloads')
RECYCLE_DIR = os.path.join(ROOT, '回收站')
CLI_TRANSLATE = os.path.join(ROOT, 'cli', 'translate_cli.py')

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
  header { background: #1e293b; color: #fff; padding: 14px 20px; position: relative; }
  #closeBtn { position: absolute; top: 8px; right: 12px; border: none;
              background: transparent; color: #cbd5e1; font-size: 18px;
              cursor: pointer; padding: 2px 10px; border-radius: 6px; }
  #closeBtn:hover { background: #334155; color: #fff; }
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
          background: #fff; overflow-y: auto; max-height: 40vh; }
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
  .row .del { border: none; background: transparent; color: #cbd5e1; cursor: pointer;
              padding: 0 6px; font-size: 14px; border-radius: 4px; line-height: 1; }
  .row .del:hover { color: #dc2626; background: #fee2e2; }
  .row .chk { margin: 0; accent-color: #2563eb; }
  .row .mini { border: 1px solid #cbd5e1; background: #fff; color: #2563eb; cursor: pointer;
               padding: 2px 8px; font-size: 12px; border-radius: 4px; white-space: nowrap; }
  .row .mini.danger { color: #dc2626; }
  .row .mini:hover { filter: brightness(1.05); }
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
  <button id="closeBtn" onclick="closePage()" title="关闭页面">✕</button>
  <h1>🎺 口风琴工具 · 三角洲行动</h1>
  <p>检索 → 翻译 → 试听 / 进游戏演奏，全程本地运行。</p>
</header>
<div class="wrap">
  <div class="bar" id="bar">
    <input type="text" id="q" placeholder="输入曲名 / 拼音 / 英文名…">
    <select id="mode">
      <option value="local">本地曲库</option>
      <option value="online">联网 MIDI</option>
      <option value="jianpu">简谱</option>
    </select>
    <button class="primary" onclick="search()">搜索</button>
    <button onclick="search(true)">刷新</button>
    <button id="batchDelBtn" onclick="batchDelete()" style="display:none">删除所选</button>
    <button id="recycleBtn" onclick="toggleRecycle()">🗑 回收站</button>
  </div>

  <div class="bar" id="recycleBar" style="display:none">
    <span class="muted">回收站</span>
    <button onclick="purgeAllRecycle()">清空回收站</button>
    <button onclick="toggleRecycle()">← 返回曲库</button>
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
        <button onclick="guidePlay()">🎹 手动演示</button>
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
let view = 'library';
let recycleItems = [];

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
    document.getElementById('batchDelBtn').style.display = 'none';
    return;
  }
  el.innerHTML = items.map((it, i) =>
    '<div class="row" id="row' + i + '" onclick="select(' + i + ')">' +
    (it.deletable ? '<input type="checkbox" class="chk" value="' + i + '" onclick="event.stopPropagation()">' : '') +
    '<span class="title">' + esc(it.title) + '</span>' +
    '<span class="src ' + it.kind + '">' + esc(it.source) + '</span>' +
    '<span class="meta">' + (it.n_notes ?? '—') + ' 音符 · BPM ' + (it.bpm ?? '—') + '</span>' +
    (it.deletable ? '<button class="del" title="删除" onclick="delScore(' + i + ', event)">🗑</button>' : '') +
    '</div>').join('');
  document.getElementById('batchDelBtn').style.display =
    items.some(it => it.deletable) ? '' : 'none';
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
    sc.innerHTML = '<img src="/api/jianpu_img?id=' + encodeURIComponent(selected.id) + '&n=0&t=' + Date.now() + '" alt="简谱" style="max-width:100%">';
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

async function guidePlay() {
  if (!selected) return;
  setStatus('启动手动演示（下落音符悬浮窗，照着按）…');
  await post('/api/guide?id=' + encodeURIComponent(selected.id));
}

function closePage() {
  navigator.sendBeacon('/api/quit');
  window.close();
  setTimeout(function () {
    setStatus('如页面未自动关闭，请手动关闭此标签页（Ctrl+W）。');
  }, 200);
}

async function toLibrary() {
  if (!selected) return;
  const r = await post('/api/library?id=' + encodeURIComponent(selected.id));
  setStatus(r.message || '已入库。');
}

async function delScore(i, ev) {
  ev.stopPropagation();
  const it = items[i];
  if (!confirm('将曲谱「' + it.title + '」移入回收站？')) return;
  try {
    const r = await post('/api/delete?id=' + encodeURIComponent(it.id));
    if (r.error) throw new Error(r.error);
    if (selected && selected.id === it.id) {
      selected = null;
      document.getElementById('panel').style.display = 'none';
    }
    setStatus(r.message || '已移入回收站。');
    list();
  } catch (e) { setStatus('删除失败：' + (e && e.message || e), true); }
}

async function batchDelete() {
  const boxes = Array.from(document.querySelectorAll('#list .chk:checked'));
  if (!boxes.length) { setStatus('请先勾选要删除的曲谱。', true); return; }
  const its = boxes.map(b => items[+b.value]);
  if (!confirm('将所选 ' + its.length + ' 首曲谱移入回收站？')) return;
  try {
    const r = await post('/api/delete?ids=' + encodeURIComponent(its.map(x => x.id).join(',')));
    if (r.error) throw new Error(r.error);
    setStatus(r.message || '已移入回收站。');
    list();
  } catch (e) { setStatus('删除失败：' + (e && e.message || e), true); }
}

function toggleRecycle() {
  if (view === 'recycle') {
    view = 'library';
    document.getElementById('bar').style.display = 'flex';
    document.getElementById('recycleBar').style.display = 'none';
    list();
  } else {
    view = 'recycle';
    document.getElementById('bar').style.display = 'none';
    document.getElementById('recycleBar').style.display = 'flex';
    renderRecycle();
  }
}

async function renderRecycle() {
  setStatus('加载回收站…');
  try {
    const d = await (await fetch('/api/recycle')).json();
    recycleItems = d.items || [];
    const el = document.getElementById('list');
    if (!recycleItems.length) {
      el.innerHTML = '<div class="row muted">回收站是空的。</div>';
    } else {
      el.innerHTML = recycleItems.map((it, i) =>
        '<div class="row">' +
        '<span class="title">' + esc(it.title) + '</span>' +
        '<span class="meta">' + (it.n_notes ?? '—') + ' 音符 · ' + fmtSize(it.size) + '</span>' +
        '<button class="mini" onclick="restoreRecycle(' + i + ')">↩ 恢复</button>' +
        '<button class="mini danger" onclick="purgeRecycle(' + i + ')">彻底删除</button>' +
        '</div>').join('');
    }
    setStatus('回收站 · 共 ' + recycleItems.length + ' 个文件。');
  } catch (e) { setStatus('加载回收站失败：' + e, true); }
}

async function restoreRecycle(i) {
  const it = recycleItems[i];
  try {
    const r = await post('/api/recycle_restore?name=' + encodeURIComponent(it.name));
    if (r.error) throw new Error(r.error);
    setStatus(r.message || '已恢复。');
    renderRecycle();
  } catch (e) { setStatus('恢复失败：' + (e && e.message || e), true); }
}

async function purgeRecycle(i) {
  const it = recycleItems[i];
  if (!confirm('彻底删除「' + it.title + '」？此操作不可恢复。')) return;
  try {
    const r = await post('/api/recycle_purge?name=' + encodeURIComponent(it.name));
    if (r.error) throw new Error(r.error);
    setStatus(r.message || '已彻底删除。');
    renderRecycle();
  } catch (e) { setStatus('删除失败：' + (e && e.message || e), true); }
}

async function purgeAllRecycle() {
  if (!recycleItems.length) { setStatus('回收站已是空的。'); return; }
  if (!confirm('彻底删除回收站中全部 ' + recycleItems.length + ' 个文件？此操作不可恢复。')) return;
  try {
    const r = await post('/api/recycle_purge_all');
    if (r.error) throw new Error(r.error);
    setStatus(r.message || '已清空。');
    renderRecycle();
  } catch (e) { setStatus('清空失败：' + (e && e.message || e), true); }
}

function fmtSize(b) {
  if (b == null) return '—';
  return b < 1024 ? b + ' B' : (b / 1024).toFixed(1) + ' KB';
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
document.addEventListener('visibilitychange', function () {
  fetch('/api/ping').catch(function () {});
});
setInterval(function () {
  fetch('/api/ping').catch(function () {});
}, 2000);
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


def _watchdog(srv):
    """心跳看门狗：前端页面定期 ping；页面关闭后 ping 停止，超时则关闭后端服务。"""
    while True:
        time.sleep(1.0)
        if srv.last_seen is not None and (time.monotonic() - srv.last_seen) > srv.ping_timeout:
            print('[web] 前端已关闭，正在退出服务…')
            srv.shutdown()
            break


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
        if subprocess.call([sys.executable, CLI_TRANSLATE, mid, '--out', mel, '--min-sharps'], cwd=ROOT) != 0:
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
            elif path == '/api/ping':
                self.server.last_seen = time.monotonic()
                self._json(200, {'ok': True})
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
            elif path == '/api/recycle':
                self._recycle_list(q)
            else:
                self._json(404, {'error': 'not found'})
        except Exception as e:
            self._json(500, {'error': str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        q = self._query()
        try:
            if path == '/api/quit':
                self._json(200, {'ok': True, 'message': '服务已退出。'})
                threading.Timer(0.2, self.server.shutdown).start()
            elif path == '/api/play':
                mel = self._resolve(q.get('id', [''])[0])
                subprocess.Popen([sys.executable, os.path.join(ROOT, 'main.py'), mel], cwd=ROOT)
                self._json(200, {'ok': True, 'message': '已启动游戏演奏。'})
            elif path == '/api/guide':
                mel = self._resolve(q.get('id', [''])[0])
                subprocess.Popen([sys.executable, os.path.join(ROOT, 'gui', 'guide.py'), mel], cwd=ROOT)
                self._json(200, {'ok': True, 'message': '已启动手动演示。'})
            elif path == '/api/library':
                mel = self._resolve(q.get('id', [''])[0])
                item = self.server.registry[q['id'][0]]
                dest = os.path.join(library.LIB_DIR, _safe_name(item['title']) + '.mel')
                shutil.copyfile(mel, dest)
                self._json(200, {'ok': True, 'message': '已入库：' + dest})
            elif path == '/api/delete':
                self._delete(q)
            elif path == '/api/recycle_restore':
                self._recycle_restore(q)
            elif path == '/api/recycle_purge':
                self._recycle_purge(q)
            elif path == '/api/recycle_purge_all':
                self._recycle_purge_all(q)
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
                            'path': it['path'], 'deletable': True}
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
        if subprocess.call([sys.executable, CLI_TRANSLATE, tmp, '--out', out, '--min-sharps'], cwd=ROOT) != 0:
            raise RuntimeError('翻译失败，见服务器控制台。')
        try:
            os.remove(tmp)
        except OSError:
            pass
        self._json(200, {'ok': True, 'out': out})

    def _delete(self, q):
        raw = q.get('ids', [''])[0] or q.get('id', [''])[0]
        iids = [x for x in raw.split(',') if x]
        if not iids:
            raise ValueError('未指定要删除的曲目。')
        lib = os.path.realpath(library.LIB_DIR)
        moved = []
        for iid in iids:
            item = self.server.registry.get(iid)
            if item is None or item['kind'] != 'local':
                continue
            mel = item['path']
            real = os.path.realpath(mel)
            if real != lib and not real.startswith(lib + os.sep):
                continue
            if not os.path.exists(mel):
                continue
            os.makedirs(RECYCLE_DIR, exist_ok=True)
            dest = os.path.join(RECYCLE_DIR, os.path.basename(mel))
            if os.path.exists(dest):  # 同名文件已在回收站，加时间戳后缀避免覆盖
                stem, ext = os.path.splitext(os.path.basename(mel))
                dest = os.path.join(RECYCLE_DIR, f'{stem}_{int(time.time())}{ext}')
            shutil.move(mel, dest)
            moved.append(os.path.basename(mel))
        if not moved:
            raise ValueError('没有可删除的曲谱。')
        self._json(200, {'ok': True, 'message': f'已移入回收站 {len(moved)} 首曲谱。'})

    def _recycle_list(self, q):
        items = []
        if os.path.isdir(RECYCLE_DIR):
            for fn in sorted(os.listdir(RECYCLE_DIR)):
                if not fn.lower().endswith('.mel'):
                    continue
                path = os.path.join(RECYCLE_DIR, fn)
                title, _ = library._meta_from(path)
                try:
                    notes, bpm = load_score(path)
                    n_notes = len(notes)
                except Exception:
                    n_notes, bpm = None, None
                st = os.stat(path)
                items.append({'name': fn, 'title': title or os.path.splitext(fn)[0],
                              'n_notes': n_notes, 'bpm': bpm,
                              'size': st.st_size, 'mtime': int(st.st_mtime)})
        self._json(200, {'items': items})

    def _recycle_restore(self, q):
        name = os.path.basename(q.get('name', [''])[0])
        src = os.path.join(RECYCLE_DIR, name)
        if not name or not os.path.isfile(src):
            raise ValueError('回收站中找不到该文件。')
        stem, ext = os.path.splitext(name)
        orig = re.sub(r'_\d{10}$', '', stem) + ext  # 去掉移入时加的时间戳后缀
        os.makedirs(library.LIB_DIR, exist_ok=True)
        dest = os.path.join(library.LIB_DIR, orig)
        if os.path.exists(dest):
            dest = os.path.join(library.LIB_DIR, f'{stem}_{int(time.time())}{ext}')
        shutil.move(src, dest)
        self._json(200, {'ok': True, 'message': '已恢复：' + os.path.basename(dest)})

    def _recycle_purge(self, q):
        name = os.path.basename(q.get('name', [''])[0])
        src = os.path.join(RECYCLE_DIR, name)
        if not name or not os.path.isfile(src):
            raise ValueError('回收站中找不到该文件。')
        os.remove(src)
        self._json(200, {'ok': True, 'message': '已彻底删除：' + name})

    def _recycle_purge_all(self, q):
        n = 0
        if os.path.isdir(RECYCLE_DIR):
            for fn in os.listdir(RECYCLE_DIR):
                if fn.lower().endswith('.mel'):
                    try:
                        os.remove(os.path.join(RECYCLE_DIR, fn))
                        n += 1
                    except OSError:
                        pass
        self._json(200, {'ok': True, 'message': f'已清空回收站（彻底删除 {n} 个文件）。'})


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
    srv.last_seen = None
    # 后台标签页里浏览器会节流 setInterval（约 1 次/分钟），5 秒会误判「页面已关闭」。
    # 放宽到 5 分钟，覆盖切到游戏后台的场景；前台仍每 2 秒 ping 一次。
    srv.ping_timeout = 300.0
    threading.Thread(target=_watchdog, args=(srv,), daemon=True).start()
    print(f'口风琴工具 Web 界面：http://{args.host}:{args.port}')
    print('按 Ctrl+C 退出。')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已退出。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
