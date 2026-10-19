"""视觉转录客户端：调用视觉大模型把简谱图片转成结构化 JSON（GLM / DeepSeek / Qwen）。

通过 OpenAI 兼容接口调用视觉模型，纯标准库实现（urllib + base64 + json）。
厂商通过环境变量 VL_PROVIDER 切换（glm / deepseek / qwen，默认 glm）。

配置（环境变量，或写在项目根目录 .env 文件里，二者可混用）：
    VL_PROVIDER         视觉模型厂商：glm（默认）/ deepseek / qwen
    GLM_API_KEY         智谱 bigmodel API Key（glm 时必填）
    GLM_BASE_URL        GLM 接口地址（默认 https://open.bigmodel.cn/api/paas/v4）
    GLM_MODEL           GLM 视觉模型名（默认 glm-5.3-flash）
    GLM_REASONING       GLM 推理力度：low（默认，快）/ high / max（glm-5.3 强制思考，不支持关闭）
    DEEPSEEK_API_KEY    DeepSeek API Key（deepseek 时必填）
    DEEPSEEK_BASE_URL   DeepSeek 接口地址（默认 https://api.deepseek.com）
    DEEPSEEK_MODEL      DeepSeek 视觉模型名（默认 deepseek-flash）
    DASHSCOPE_API_KEY   阿里百炼 API Key（qwen 时必填）
    QWEN_BASE_URL       Qwen 兼容接口地址（默认北京 maas 端点）
    QWEN_MODEL          Qwen 视觉模型名（默认 qwen3-vl-plus）
"""

import base64
import json
import os
import socket
import urllib.error
import urllib.request

from melodica import ROOT
from melodica.translate import jianpu

GLM_DEFAULT_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
GLM_DEFAULT_MODEL = 'glm-5.3-flash'
QWEN_DEFAULT_BASE_URL = 'https://llm-n2tr15mt28kgsvtu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
QWEN_DEFAULT_MODEL = 'qwen3-vl-plus'
DEEPSEEK_DEFAULT_BASE_URL = 'https://api.deepseek.com'
DEEPSEEK_DEFAULT_MODEL = 'deepseek-flash'

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


def provider():
    """当前使用的视觉模型厂商：'glm' / 'deepseek' / 'qwen'（环境变量 VL_PROVIDER 控制，默认 glm）。"""
    _load_dotenv()
    p = (os.environ.get('VL_PROVIDER') or 'glm').strip().lower()
    if p in ('deepseek', 'ds'):
        return 'deepseek'
    if p in ('glm', 'zhipu', 'zai'):
        return 'glm'
    return 'qwen'


def config():
    """返回 (api_key, base_url, model)，按 VL_PROVIDER 在 GLM / DeepSeek / Qwen 间切换。"""
    _load_dotenv()
    p = provider()
    if p == 'deepseek':
        key = os.environ.get('DEEPSEEK_API_KEY')
        base = os.environ.get('DEEPSEEK_BASE_URL', DEEPSEEK_DEFAULT_BASE_URL).rstrip('/')
        model = os.environ.get('DEEPSEEK_MODEL', DEEPSEEK_DEFAULT_MODEL)
    elif p == 'glm':
        key = os.environ.get('GLM_API_KEY') or os.environ.get('ZAI_API_KEY')
        base = os.environ.get('GLM_BASE_URL', GLM_DEFAULT_BASE_URL).rstrip('/')
        model = os.environ.get('GLM_MODEL', GLM_DEFAULT_MODEL)
    else:
        key = os.environ.get('DASHSCOPE_API_KEY') or os.environ.get('QWEN_API_KEY')
        base = os.environ.get('QWEN_BASE_URL', QWEN_DEFAULT_BASE_URL).rstrip('/')
        model = os.environ.get('QWEN_MODEL', QWEN_DEFAULT_MODEL)
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
- 若是钢琴伴奏谱或带伴奏（谱面有琶音、分解和弦、连续八/十六分音符伴奏音型），只取最上方「能唱出来」的单音旋律线；丢弃分解和弦、琶音、伴奏音型、低音声部

【输出 JSON 结构】
{"key":"F","bpm":96,"notes":[[5,0,1],[0,0,0.5],[6,1,1.5],...]}
- key：调号（do 对应哪个音名，如 C/D/E/F/G/A/B；图上看不到时写 "C"）
- bpm：速度（图上没标时写 96）
- notes：主旋律音符数组，按演唱顺序排列

【notes 里每个音符的格式】
每个音符是一个紧凑的三元数组 [d, o, b]：
- d：音级，1~7 表示 do~si，0 表示休止符
- o：八度偏移 = 高音点个数 − 低音点个数（可为负数）
- b：时值（拍数，小数）：无记号=1；增时线每多一条 +1；下划线一条=0.5、两条=0.25；附点 ×1.5
- 节奏务必忠实：增时线「5---」是【一个】4 拍的音，绝不能拆成 4 个「5」；附点、下划线、休止符 0 都要如实读出，不要把整首读成等长的四分音符

【重要】
- 只做「看图转录」：把图上的音级、八度点、时值原样读出来即可，不要自己转调、选调或换算音高
- 音符用紧凑三元数组表示（不要用对象、元素间不要空格），尽量减小体积、避免输出被截断
- 必须一次性输出完整、合法的 JSON，不要截断、不要省略任何音符
- 只输出一个合法 JSON 对象本身，不要任何解释、Markdown 代码块或前后缀。"""


MEL_SYSTEM_PROMPT = """你是三角洲行动「口风琴」曲谱翻译助手。读取给定的简谱图片，把它翻译成口风琴能直接演奏的 JSON 曲谱，只输出 JSON，不要任何其它文本。

【口风琴映射规则（务必遵守）】
- 口风琴有 8 个音键：1(do) 2(re) 3(mi) 4(fa) 5(sol) 6(la) 7(si) 对应 Z X C V B N M，
  第 8 键是「高音 do」= 逗号 ,，比 1(do) 高一个八度，用音级 8 表示
- 没有升半音/降半音键（#/b 都不可用）
- 八度靠鼠标：不按 = 自然八度；按住右键 = 升一个八度；按住左键 = 降一个八度
- 最终每个音符只能是 1~8 的音级 + 八度 -1/0/+1；绝不能出现 #4、b7 之类的记号
- 「高音 do」务必写成 8（逗号键，八度 0），不要写成 1 + 升八度（那样要多按一个鼠标右键）
- 若原谱带调号（如 1=F），先把旋律就近归到自然大调音阶并换算成 1~8，使整首尽量落在自然音区、升降半音最少

【输出 JSON 结构】
{"key":"C","bpm":96,"notes":[[1,0,1.0],[0,0,0.5],[8,0,1.5],...]}
- key：原谱调号（do 对应音名，仅备注，不影响演奏）
- bpm：速度（图上没标就写 96）
- notes：按演唱顺序排列的音符数组，每个音符是紧凑三元数组 [d, o, b]
  - d：音级 1~8（已换算到自然大调，8=高音 do 逗号键），0 = 休止符
  - o：八度，-1=降八度 / 0=自然 / +1=升八度（把整条旋律居中，尽量用 0 少用鼠标）
  - b：拍数（小数）：无记号=1；增时线每条 +1；下划线一条=0.5、两条=0.25；附点 ×1.5

【必须忽略】
- 歌词、和弦字母、标题、作者、版权信息
- 前奏/间奏/尾奏等纯器乐段落，只保留能唱的主旋律
- 钢琴伴奏谱/琶音/分解和弦/低音声部，只取最上方能唱出来的单音旋律线

【节奏务必忠实】
- 增时线「5---」是【一个】4 拍的音，绝不能拆成 4 个「5」
- 附点、下划线、休止符 0 都要如实读出，不要把整首读成等长的四分音符

【重要】
- 音符用紧凑三元数组（不要用对象、元素间不要空格），尽量减小体积避免输出被截断
- 一次输出完整、合法的 JSON，不要截断、不要省略任何音符
- 只输出一个合法 JSON 对象本身，不要任何解释、Markdown 代码块或前后缀。"""


def _post(base, key, payload):
    req = urllib.request.Request(
        base + '/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    )
    # GLM 推理模型生成整首曲谱可能较慢，读超时放宽到 10 分钟。
    return urllib.request.urlopen(req, timeout=600)


def _chat(system_prompt, image_paths, user_text, model, json_mode=False):
    """一次调用视觉模型：系统提示词 + 多张图片 + 用户文本，返回 content 字符串。"""
    key, base, env_model = config()
    prov = provider()
    if not key:
        var = {'deepseek': 'DEEPSEEK_API_KEY', 'glm': 'GLM_API_KEY'}.get(prov, 'DASHSCOPE_API_KEY')
        raise QwenError(f'缺少 API Key：请设置环境变量 {var}，'
                        f'或在项目根目录 .env 文件里写 {var}=你的key')
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
    # GLM-5.3 是「强制思考」推理模型，reasoning_effort 仅支持 low/high/max（默认 max）。
    # 读谱是感知任务，low 即可大幅提速；用 GLM_REASONING 可切回 high/max。
    if prov == 'glm':
        reasoning = (os.environ.get('GLM_REASONING') or 'low').strip().lower()
        if reasoning in ('low', 'high', 'max'):
            payload['reasoning_effort'] = reasoning
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
    except (TimeoutError, socket.timeout):
        raise QwenError('API 请求超时（视觉模型生成曲谱过慢，已超过 600 秒）。可重试一次，或改用更快模型。')

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


def transcribe_json(image_paths, model=None, max_pages_per_call=2, retries=2):
    """读取一或多张简谱图片，返回结构化 JSON dict（key / bpm / notes）。

    为避免整首旋律一次输出超出模型长度上限而被截断，按页（或每几页）分组转录，
    再把各组 notes 按顺序拼接。key / bpm 取第一组的调号与速度。
    模型输出偶发被截断（非确定），解析失败时对同一组重试最多 retries 次。
    """
    image_paths = list(image_paths)
    if not image_paths:
        raise QwenError('没有曲谱图片。')
    chunks = [image_paths[i:i + max_pages_per_call]
              for i in range(0, len(image_paths), max_pages_per_call)]

    notes = []
    key = 'C'
    bpm = 96.0
    for ci, chunk in enumerate(chunks):
        if len(chunks) == 1:
            user_text = '请转录这些简谱图片的主旋律，按要求的 JSON 格式输出。'
        else:
            user_text = f'请转录第 {ci + 1}/{len(chunks)} 组简谱图片的主旋律，按要求的 JSON 格式输出。'
        data = _transcribe_chunk(chunk, user_text, model, retries)
        if ci == 0:
            key = str(data.get('key', 'C') or 'C').strip() or 'C'
            try:
                bpm = float(data.get('bpm') or 96.0)
            except (TypeError, ValueError):
                bpm = 96.0
        notes.extend(data.get('notes') or [])

    if not notes:
        raise QwenError('模型未返回任何音符。')
    return {'key': key, 'bpm': bpm, 'notes': notes}


def transcribe_mel_json(image_paths, model=None, max_pages_per_call=2, retries=2):
    """读取简谱图片，直接返回口风琴可演奏的 JSON（key / bpm / notes）。

    与 transcribe_json 的区别：用 MEL_SYSTEM_PROMPT（含口风琴映射规则），
    notes 里的音级已换算成自然大调 1~8（8=高音 do 逗号键）、八度已居中为 -1/0/+1，本地无需再量化。
    同样按页分块转录、解析失败重试。
    """
    image_paths = list(image_paths)
    if not image_paths:
        raise QwenError('没有曲谱图片。')
    chunks = [image_paths[i:i + max_pages_per_call]
              for i in range(0, len(image_paths), max_pages_per_call)]

    notes = []
    key = 'C'
    bpm = 96.0
    for ci, chunk in enumerate(chunks):
        if len(chunks) == 1:
            user_text = '请把这张简谱图片翻译成口风琴可演奏的 JSON 曲谱。'
        else:
            user_text = f'请把第 {ci + 1}/{len(chunks)} 组简谱图片翻译成口风琴可演奏的 JSON 曲谱。'
        data = _transcribe_chunk(chunk, user_text, model, retries, system_prompt=MEL_SYSTEM_PROMPT)
        if ci == 0:
            key = str(data.get('key', 'C') or 'C').strip() or 'C'
            try:
                bpm = float(data.get('bpm') or 96.0)
            except (TypeError, ValueError):
                bpm = 96.0
        notes.extend(data.get('notes') or [])

    if not notes:
        raise QwenError('模型未返回任何音符。')
    return {'key': key, 'bpm': bpm, 'notes': notes}


def _transcribe_chunk(chunk, user_text, model, retries, system_prompt=JSON_SYSTEM_PROMPT):
    """转录一组图片，解析失败（截断/非法 JSON）时重试。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            content = _chat(system_prompt, chunk, user_text, model, json_mode=True)
            data = _parse_json_loose(content)
            if not isinstance(data, dict):
                raise QwenError(f'模型返回的 JSON 不是对象：{str(data)[:200]}')
            return data
        except QwenError as e:
            last_err = e
    raise last_err


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
