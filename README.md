# 三角洲行动 · 口风琴演奏工具

在《三角洲行动》端游的「守夜人口风琴」吹奏模式里，按曲谱自动演奏。

## 功能
- **演奏**：解析「简谱数字」曲谱，按 BPM 通过 Win32 `SendInput`（物理扫描码）自动按下/抬起键盘与鼠标变调键；倒计时开始、按 F12 随时停止
- **口风琴模拟器（GUI）**：无需进游戏、不会封号，带声音 + 琴键高亮，可听曲谱效果、可手动演奏
- **翻译**：把 MIDI 文件或简谱文本自动翻译成口风琴可吹的 `.mel`（自动选调、量化到自然音阶、节奏量化）
- **曲库**：本地曲谱检索（列出/搜索 `scores/`，新曲谱用翻译模块拖入即可）
- **网络检索**：联网搜索公开 MIDI 站并一键下载翻译（灰色版权，仅供个人练习）

> 联网检索的边界：流媒体 App（QQ 音乐等）只提供加密音频、无曲谱接口，无法接入；网络检索走的是**公开 MIDI 站**（bitmidi 等），以英文/经典/游戏音乐为主，中文流行歌命中率低、质量参差。

## 运行环境
- Windows + Python 3.8+
- 演奏 / 模拟器：**无需任何第三方库**（纯标准库 ctypes 实现）
- 翻译 MIDI：需 `pip install mido`（只做演奏可不装）
- 网络检索：需 `pip install scoreseek`（只做本地可不装）
- 翻译 agent（简谱图片 → .mel）：需设置 `DASHSCOPE_API_KEY`（Qwen 百炼视觉识图，见下文）
- 游戏内请切换到英文输入法

## 快速启动

双击 `start.bat`（或在项目目录运行 `python start.py`）：自动启动后端服务，并用默认浏览器打开前端页面。

其它入口仍可单独运行：

```bash
python main.py scores/xxx.mel   # 游戏演奏
python search.py                # 交互检索（本地/联网）
python translate.py xxx.mid     # 曲谱翻译
python library.py               # 本地曲库列表
python simulator.py             # 口风琴模拟器（GUI）
```

## 口风琴模拟器（推荐先用这个）

一个离线的虚拟口风琴：不用进游戏、不碰反作弊、不需要真的口风琴，还能**发声**让你直接听曲谱效果。琴键与变调逻辑和真实口风琴完全一致（共用同一套音符模型）。

```bash
# 打开模拟器（可选直接带一个曲谱文件）
python simulator.py
python simulator.py scores/twinkle.mel
```

- 用鼠标点琴键，或按键盘 **Z X C V B N M** 演奏
- 变调：自然 / 降八度(左键) / 升八度(右键)；升半音(中键)仅模拟器可用，游戏内不可靠
- 载入 `.mel` 曲谱 → 点 **▶ 播放曲谱**，琴键会实时高亮，**■ 停止**随时停

> 音色是简化的正弦+谐波合成，不模拟游戏内「3.6 秒渐强」的缓慢包络；但**音高、键位、时值**与游戏内一致，足够用来试听曲谱、练习指法。

## 用法

```bash
# 只查看解析结果（不演奏，先校验曲谱是否正确）
python main.py scores/twinkle.mel --list-notes

# 正式演奏（默认 5 秒倒计时，请趁此时切到游戏窗口）
python main.py scores/twinkle.mel

# 常用选项
python main.py scores/watch.mel --bpm 100 --countdown 3 --gap 0.03

# 冒烟测试：向前台窗口（如记事本）依次敲出 zxcvbnm, 以校验键盘注入
python main.py --smoke
```

演奏过程中按 **F12** 随时停止。

## 曲谱格式（简谱数字）

每行用空白分隔音符，`#` 开头是注释，`|` 是小节线（可忽略），`T=96` 设置速度。

一个音符 = `[前缀][1-8|0][:时值]`（游戏有 do~si 七个自然音键 + 高音 do 逗号键，八度靠鼠标）：

| 写法 | 含义 |
|------|------|
| `1` ~ `7` | 音级 do~si（键位 Z X C V B N M） |
| `8` | 高音 do（键位逗号 `,`） |
| `0` | 休止符 |
| `-` 前缀 | 降八度（按住鼠标左键，游戏内不可靠） |
| `+` 前缀 | 升八度（按住鼠标右键，常用） |
| `#` 前缀 | 升半音（按住鼠标中键，游戏内不可靠；解析兼容，翻译不再输出） |
| `:N` 后缀 | 时值 N 拍（默认 1，可用 `:0.5`、`:2` 等） |

> 高音 do 写作 `8`（逗号键，少按一个鼠标）；也可写作 `+1`（升八度）。翻译器输出只含 `1~8` + `+`/`-` 八度，不含 `#`。

示例（小星星）：

```
T=96
1 1 5 5 6 6 5:2
4 4 3 3 2 2 1:2
```

游戏内曲谱写法的对应：`降调5` → `-5`；`升调` → `+`；`长按` → 加大时值（如 `:2`）。

## 翻译模块（MIDI / 简谱 → 曲谱）

把任意歌曲翻译成口风琴可吹的版本，输出 `.mel`，可直接给模拟器/演奏器用。

```bash
python translate.py song.mid              # MIDI 文件（自动选音符最多的轨当主旋律）
python translate.py song.txt              # 简谱文本（.txt/.jianpu/.jp）

# 常用选项
python translate.py song.mid --track 1        # 指定 MIDI 轨道
python translate.py song.mid --min-sharps     # 量化到自然音阶（现为默认行为，可省略）
python translate.py song.mid --transpose -2   # 手动移调 -2 半音
python translate.py song.mid --bpm 100 --grid 0.5   # 覆盖速度 / 时值量化网格
python translate.py song.mid --list-notes     # 只预览解析结果，不写文件
```

翻译流水线：提取主旋律（重叠取最高音、自动补休止符）→ 量化到最近的大调自然音阶（自动选调、就近归音级）→ 整八度居中到口风琴音域 → 节奏量化。输出用 do~si 七个自然音 + 高音 do（逗号键）+ 升/降八度，无需升半音。

### 简谱文本格式

纯文本简谱，每行用空白分隔音符：

| 记号 | 含义 |
|------|------|
| `1=C` / `1=F` | 调号（do 对应哪个音名，默认 1=C） |
| `T=96` | 速度 BPM |
| `1` ~ `7` | 音级；`0` 休止符 |
| `1'` / `1,` | 高八度 / 低八度 |
| `#4` / `b7` | 升 / 降半音 |
| `5-` / `1_` / `5.` | 加一拍 / 减半 / 附点（×1.5） |
| `\|` | 小节线（忽略） |

示例：

```
1=F
T=90
5 5 6 6 5- | 3 3 2 2 1-
```

## 曲库检索

```bash
python library.py            # 列出 scores/ 下全部曲谱
python library.py 夜莺        # 按文件名/标题/别名搜索
```

**交互式「输入曲名 → 选曲 → 试听/演奏」**：

```bash
python search.py              # 交互输入曲名
python search.py 小星星        # 直接搜，命中后选下一步
python search.py 小星星 --sim   # 搜到直接模拟器试听
python search.py 小星星 --game  # 搜到直接进游戏演奏
python search.py 小星星 --show  # 只显示曲谱
```

支持中文名、拼音、英文名搜索：曲谱文件里的 `# @别名` 行可加拼音/别名，例如：

```
# 小星星（Twinkle Twinkle Little Star）
# @别名 xiaoxingxing
```

新曲谱入曲库：把 MIDI 或简谱翻译后放进 `scores/` 即可：

```bash
python translate.py song.mid --out scores/我的曲子.mel
```

### 网络检索（公开 MIDI 站）

```bash
python search.py "happy birthday" --online          # 联网搜索 + 选曲 + 试听/演奏
python search.py "canon" --online --pick 1 --sim    # 直接下第 1 条并试听
python search.py "fur elise" --online --limit 5     # 限制结果数
python search.py --download-lakh                   # 下载 Lakh 数据集（约 234MB，扩充欧美曲库）
```

- 结果来自公开 MIDI 站（bitmidi / midis101 / midiworld），**灰色版权内容，仅供个人练习，请勿分发**。
- 下载后自动翻译成 `.mel`，存到 `downloads/` 目录。
- 可下载 **Lakh MIDI 数据集**（约 1.7 万首欧美流行/经典歌）扩充检索命中率；放到 `lakh/` 目录后自动启用。
- **中文流行歌几乎没有公开免费 MIDI 源**，搜索命中率低是内容覆盖问题、不是 bug。中文歌可用 `--jianpu` 到「简谱之家」搜简谱图片（见下节），或改用「简谱文本」翻译：

  ```bash
  python translate.py 简谱.txt --out scores/我的曲子.mel
  ```

- MIDI 多为多轨编曲，若主旋律不对可用 `--track N` 换轨。

### 简谱之家（中文简谱图片检索）

中文歌在公开 MIDI 站几乎搜不到，可到「简谱之家」搜中文简谱并下载曲谱图片：

```bash
python search.py 夜曲 --jianpu              # 搜索 + 选曲 + 下载简谱图片
python search.py 小星星 --jianpu --pick 1   # 直接下载第 1 条结果
```

- 结果来自简谱之家（jianpujia.com），**曲谱是 PNG 图片、非文本**，下载到 `downloads/jianpu/`。
- 图片需转成简谱文本再翻译成 `.mel`——可用下面的 agent 自动识别，或人工转录。

### 简谱识别翻译（agent，Qwen 百炼视觉）

一键把简谱之家搜到的**简谱图片**自动转成 `.mel`（搜索 → 下载图片 → Qwen 视觉识图 → 翻译）：

```bash
# 先配置 API Key（二选一）：
#   环境变量：set DASHSCOPE_API_KEY=你的key
#   或在项目根目录建 .env 文件（复制 .env.example 改名 .env，已加入 .gitignore）

python agent.py 夜曲                  # 搜索、选曲、下载、识图、翻译
python agent.py 夜曲 --pick 1         # 直接取第 1 条结果
python agent.py 夜曲 --min-sharps     # 量化到自然音阶（默认行为，降低演奏难度）
python agent.py 夜曲 --no-translate   # 只识图出简谱文本，不翻译
```

- 视觉模型走 Qwen 百炼的 OpenAI 兼容接口，默认 `qwen3-vl-plus`；可用 `--model` 或环境变量 `QWEN_MODEL` 换模型。
- 识图结果（简谱文本）先打印、并存到 `downloads/jianpu/<曲名>.txt`，方便人工核对/修改后再翻译。
- 翻译失败时可手工改上面的文本，再 `python translate.py 该文本 --out scores/xxx.mel`。
- 也可在 **Web 前端**（`start.py`）里操作：检索模式选「简谱」→ 点结果看图片 → 点「识图翻译」→ 试听/演奏。

## 游戏内任务曲谱（节奏/变调为推测，需实测微调）

| 曲目 | 本工具写法 |
|------|-----------|
| 佐拉【守望】 | `7 6 7 6:2 3 5 4` |
| 老乔【夜莺】 | `-5 1 2 3 5 4 3 1 2 3` |
| 唐吉【风起】 | `-6 -7 1 2 1 -7 1` |
| 佐拉【破晓】 | `7 6 3 6 7 6 7 +1 +4 +3 +4` |

## 注意事项 / 已知限制

- **管理员权限**：若游戏以管理员身份运行，请以管理员运行本脚本，否则系统 UIPI 会拦截注入的输入。
- **反作弊**：三角洲带 ACE 反作弊，合成键鼠是否被拦截需在游戏内实测；本工具仅用于乐器彩蛋演奏。
- **半音不可靠**：游戏内升半音（鼠标中键）/ 降八度（鼠标左键）并不可靠，翻译时已把旋律量化到自然音阶、只用升八度（右键）变调；带 ♭/♯ 的音会就近归到 do~si。
- **音量包络**：游戏起音约 0.25s 达六成、约 3.6s 才渐强到稳定，短音符音量偏小，属游戏自身机制。
- 建议顺序：先用 `--list-notes` 校验 → 再用 `--smoke` 在记事本测键盘 → 最后进游戏实测鼠标变调。

## 目录结构

```
main.py            # 入口：游戏演奏（命令行）
search.py          # 入口：交互式检索（本地曲库 / --online 联网）
translate.py       # 入口：曲谱翻译（MIDI/简谱 -> .mel）
library.py         # 入口：本地曲库检索（扫描/别名/模糊匹配）
simulator.py       # 入口：口风琴模拟器（GUI，无需游戏）
melodica/          # 核心包（库代码，按功能分两个子包）
  core/            #   核心演奏引擎
    notes.py       #     音符模型 + 键位/扫描码映射 + 自然音阶量化（音级 1-8）
    score.py       #     .mel 曲谱解析 / 序列化（文本 <-> Note 序列）
    audio.py       #     音色合成与播放（模拟器发声用）
    input_backend.py #    Win32 SendInput 键鼠注入 + 停止热键轮询
    player.py      #     播放引擎（BPM 定时调度，进游戏演奏用）
  translate/       #   翻译/曲库底层
    jianpu.py      #     简谱文本解析（调号/八度/时值 -> 音高事件）
    midi_import.py #     MIDI 解析（.mid -> 各轨音符，需 mido）
    net_search.py  #     网络检索（scoreseek：搜公开 MIDI 站 + 下载）
scores/            # 本地曲库（示例曲谱）
downloads/         # 网络检索下载的曲谱（运行时生成）
```
