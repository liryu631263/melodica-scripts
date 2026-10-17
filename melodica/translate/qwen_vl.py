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
from melodica.translate import jianpu

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


JSON_SYSTEM_PROMPT = """你是简谱（数字谱）转录助手。读取给定的简谱图片，输出其中「主旋律」的**结构化 JSON**，不要输出任何其它文本。

【必须忽略的内容】
- 歌词（数字下方的文字）、和弦字母（数字上方的字母）、标题、作者、版权信息
- 前奏 / 间奏 / 尾奏等纯器乐段落，只保留演唱主旋律
- 反复记号、连音线等，请按实际演唱顺序把旋律线性展开

【输出 JSON 结构】
{"key": "F", "bpm": 96, "notes": [{"d": 5, "o": 0, "b": 1.0}, ...]}
- key：调号（do 对应哪个音名，如 C/D/E/F/G/A/B；图上看不到时写 "C"）
- bpm：速度（图上没标时写 96）
- notes：主旋律音符数组，按演唱顺序排列

【notes 里每个音符的字段】
- d：音级，1~7 表示 do~si，0 表示休止符
- o：八度偏移 = 数字上方高音点的个数 − 数字下方低音点的个数（可为负数）
- b：时值（拍数，小数）：无记号=1；增时线每多一条 +1；下划线一条=0.5、两条=0.25；附点 ×1.5

【重要】
- 只做「看图转录」：把图上的音级、八度点、时值原样读出来即可，不要自己转调、选调或换算音高
- JSON 用紧凑格式（对象/数组元素之间不要空格），以减小体积、避免输出被截断
- 必须一次性输出完整、合法的 JSON，不要截断、不要省略任何音符
- 只输出一个合法 JSON 对象本身，不要任何解释、Markdown 代码块或前后缀。"""


def _post(base, key, payload):
    req = urllib.request.Request(
        base + '/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    )
    return urllib.request.urlopen(req, timeout=120)


def _chat(system_prompt, image_paths, user_text, model, json_mode=False):
    """一次调用视觉模型：系统提示词 + 多张图片 + 用户文本，返回 content 字符串。"""
    key, base, env_model = config()
    if not key:
        raise QwenError('缺少 API Key：请设置环境变量 DASHSCOPE_API_KEY，'
                        '或在项目根目录 .env 文件里写 DASHSCOPE_API_KEY=你的key')
    model = model or env_model

    content = [{'type': 'text', 'text': user_text}]
    for p in image_paths:
        with open(p, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        ext = os.path.splitext(p)[1].lower()
        mime = _MIME.get(ext, 'image/png')
        content.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}})

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': content},
        ],
        'temperature': 0.1,
        'max_tokens': 16000,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}

    try:
        with _post(base, key, payload) as r:
            resp = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if json_mode:
            # 部分模型不认 response_format，去掉后重试一次
            payload.pop('response_format', None)
            try:
                with _post(base, key, payload) as r:
                    resp = json.loads(r.read().decode('utf-8'))
            except urllib.error.HTTPError as e2:
                body = e2.read().decode('utf-8', 'replace')
                raise QwenError(f'API 调用失败（HTTP {e2.code}）：{body[:500]}') from e2
            except urllib.error.URLError as e2:
                raise QwenError(f'无法连接 API：{e2.reason}') from e2
        else:
            body = e.read().decode('utf-8', 'replace')
            raise QwenError(f'API 调用失败（HTTP {e.code}）：{body[:500]}') from e
    except urllib.error.URLError as e:
        raise QwenError(f'无法连接 API：{e.reason}') from e

    try:
        return resp['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as e:
        raise QwenError(f'API 返回格式异常：{json.dumps(resp, ensure_ascii=False)[:500]}') from e


def _parse_json_loose(text):
    """从模型输出里宽松地解析 JSON（容忍 ```json 围栏与前后缀）。"""
    text = _strip_fences(text or '').strip()
    if not text:
        raise QwenError('模型未返回内容。')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise QwenError(f'模型返回的不是 JSON：{text[:200]}')
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            frag = text[max(0, e.pos - 40):e.pos + 40]
            raise QwenError(f'模型返回的 JSON 不完整或非法（疑似在 {e.pos} 处被截断）：…{frag}…') from e


def transcribe(image_path, model=None):
    """读取简谱图片，返回转录出的简谱文本（自由文本格式）。"""
    content = _chat(SYSTEM_PROMPT, [image_path], '请转录这张简谱图片的主旋律。', model)
    return _normalize_jianpu(content)


def transcribe_json(image_paths, model=None):
    """读取一或多张简谱图片，返回结构化 JSON dict（key / bpm / notes）。"""
    content = _chat(JSON_SYSTEM_PROMPT, list(image_paths),
                    '请转录这些简谱图片的主旋律，按要求的 JSON 格式输出。', model, json_mode=True)
    data = _parse_json_loose(content)
    if not isinstance(data, dict):
        raise QwenError(f'模型返回的 JSON 不是对象：{str(data)[:200]}')
    return data


def _normalize_jianpu(text):
    """修正常见 LLM/OCR 输出（粘连音符、`i`→`1'` 等），复用简谱解析器的清洗逻辑。"""
    return jianpu.normalize_jianpu(text)


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
