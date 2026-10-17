"""Qwen（阿里百炼 / DashScope）视觉转录客户端。

通过 OpenAI 兼容接口调用 Qwen 视觉模型，把简谱图片转成简谱文本。
纯标准库实现（urllib + base64 + json），无需安装 openai 等 SDK。

配置（环境变量，或写在项目根目录 .env 文件里，二者可混用）：
    DASHSCOPE_API_KEY  百炼 API Key（必填）
    QWEN_BASE_URL      兼容接口地址（默认北京 maas 端点）
    QWEN_MODEL         视觉模型名（默认 qwen3-vl-plus）
"""

import base64
import json
import os
import urllib.error
import urllib.request

from melodica import ROOT

DEFAULT_BASE_URL = 'https://llm-n2tr15mt28kgsvtu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
DEFAULT_MODEL = 'qwen3-vl-plus'

_MIME = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
}

_MODIFIERS = set("'-_.,")


class QwenError(RuntimeError):
    pass


def _load_dotenv():
    """读取项目根目录 .env（若存在），只解析 KEY=VALUE 行，不覆盖已有环境变量。"""
    path = os.path.join(ROOT, '.env')
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding='utf-8') as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def config():
    """返回 (api_key, base_url, model)。"""
    _load_dotenv()
    key = os.environ.get('DASHSCOPE_API_KEY') or os.environ.get('QWEN_API_KEY')
    base = os.environ.get('QWEN_BASE_URL', DEFAULT_BASE_URL).rstrip('/')
    model = os.environ.get('QWEN_MODEL', DEFAULT_MODEL)
    return key, base, model


SYSTEM_PROMPT = """你是简谱（数字谱）转录助手。读取给定的简谱图片，输出其中「主旋律」的简谱文本，格式必须严格符合以下规则。

【输出结构】
- 第一行：调号，形如 `1=F`（图上看不到调号时写 `1=C`）
- 第二行：速度，形如 `T=90`（图上没标速度时写 `T=96`）
- 之后每行：主旋律音符，音符之间用空格分隔，可用 `|` 表示小节线（也可省略）

【音符写法】
- 1~7 表示 do~si，0 表示休止符
- 高音点（数字上方的点）：在数字后加 `'`，一个点加一个 `'`，如 `1'`
- 低音点（数字下方的点）：在数字后加 `,`，如 `5,`
- 升半音：数字前加 `#`，如 `#4`；降半音：数字前加 `b`，如 `b7`
- 增时线（数字后的横线）：加 `-`，每多一拍多加一个 `-`，如 `5-` 为 2 拍、`5--` 为 3 拍
- 下划线：数字下方一条线加 `_`（半拍），两条线加 `__`（四分之一拍）
- 附点：数字后加 `.`，如 `5.` 为 1.5 拍

【必须忽略的内容】
- 歌词（数字下方的文字）、和弦字母（数字上方的字母）、标题、作者、版权信息
- 前奏 / 间奏 / 尾奏等纯器乐段落，只保留演唱主旋律
- 反复记号、连音线等，请按实际演唱顺序把旋律线性展开成一行行

【输出要求】
- 所有记号（`'` `,` `#` `b` `-` `_` `.`）都必须紧贴数字、中间不要空格，如 `5-`、`5.`、`1_`、`1'`
- 只输出简谱文本本身，不要任何解释、说明、Markdown 代码块或前后缀。"""


def transcribe(image_path, model=None):
    """读取简谱图片，返回转录出的简谱文本。"""
    key, base, env_model = config()
    if not key:
        raise QwenError('缺少 API Key：请设置环境变量 DASHSCOPE_API_KEY，'
                        '或在项目根目录 .env 文件里写 DASHSCOPE_API_KEY=你的key')
    model = model or env_model

    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    ext = os.path.splitext(image_path)[1].lower()
    mime = _MIME.get(ext, 'image/png')

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': '请转录这张简谱图片的主旋律。'},
                {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}},
            ]},
        ],
        'temperature': 0.1,
        'max_tokens': 4000,
    }

    req = urllib.request.Request(
        base + '/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        raise QwenError(f'API 调用失败（HTTP {e.code}）：{body[:500]}') from e
    except urllib.error.URLError as e:
        raise QwenError(f'无法连接 API：{e.reason}') from e

    try:
        content = resp['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as e:
        raise QwenError(f'API 返回格式异常：{json.dumps(resp, ensure_ascii=False)[:500]}') from e

    return _normalize_jianpu(_strip_fences(content))


def _normalize_jianpu(text):
    """修正常见 LLM 输出：把与数字分开的时值/八度记号并回数字（如 `5 -` → `5-`）。"""
    out = []
    for line in text.splitlines():
        merged = []
        for tok in line.split():
            if tok and set(tok) <= _MODIFIERS and merged and merged[-1] != '|':
                merged[-1] += tok
            else:
                merged.append(tok)
        out.append(' '.join(merged))
    return '\n'.join(out)


def _strip_fences(text):
    """去掉模型可能包上的 Markdown 代码块，只保留正文。"""
    text = (text or '').strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    return text
