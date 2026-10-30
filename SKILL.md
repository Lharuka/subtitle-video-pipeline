---
name: subtitle-video-pipeline
description: 用个人翻译工具箱（脚本内置于本 skill 目录，路径自定位，可在任意工作目录调用）完成"媒体文件 → 转写 → 翻译 → 字幕微调 → 封面视频"的完整流水线。触发场景：用户给出广播/播客音频或视频，要听写、翻译、烧字幕、合成封面视频、剪切片段、调整字幕时间轴或做节目摘要。覆盖 step1/step2 转写、字幕翻译与校对、reorganize_srt 自动重组、renumber_srt 手动微调、clip_media 剪切、audio_to_video 出片、convert_image 图片转换。
---

# 字幕视频流水线（个人翻译工具箱）

> 本手册是 **agent 作战手册**；skill 的安装与使用见同目录 **`README.md`**，人类用户直接在命令行使用工具时看 **`COMMANDLINE.md`**（命令行速查）。

**本 skill 自带全部工具脚本**（与 SKILL.md 同目录的 15 个 `.py`），脚本**路径自定位**：`raw/`、`models/` 等目录以脚本所在目录（即本 skill 目录）为基准；`output/` 与 `temp/` 默认也在 skill 目录，但设了 `TOOLBOX_OUTPUT_DIR` 时会转到该任务目录下，**与当前工作目录无关**。因此在任何目录都可以直接用绝对路径调用脚本，无需 cd。

**三个目录，不要混淆**：
- **你的项目目录**：你当前会话所在的目录，用户任务发生地。媒体文件在这里或任意位置都行，用绝对路径传给工具即可。
- **skill 目录**：`<skill目录>`，脚本和本手册所在地。`raw/`、`models/` 默认在这里。
- **产物与中间缓存去向**：设了环境变量 **`TOOLBOX_OUTPUT_DIR`**（设为任务工作目录的绝对路径）则产物（srt/mp4/剪辑）和 ASR 临时音频（`temp/`）都落到那里；未设置时默认 skill 目录下的 `output/` 与 `temp/`。

标准调用流程：
1. 在你的项目目录接受任务，输入文件用绝对路径传给工具参数
2. **每个 Bash 调用都是全新 shell，conda 激活和环境变量不跨调用保留**。所以每条调工具的命令（尤其后台长命令）必须先激活对应环境（主流水线 `video-trans`、Qwen `qwen3-asr`、Kotoba `kotoba-whisper`）。Git Bash 中统一使用以下标准前缀，不要只写 `conda activate`（未初始化 conda 时会报 `CondaError: Run 'conda init' before 'conda activate'`）：
   ```bash
   source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate <环境>
   ```
   随后在同一命令中写入 `export TOOLBOX_OUTPUT_DIR=<你的项目目录>`、（机器上已有模型库时）`export TOOLBOX_MODELS_DIR=<已有 models 目录>`。不设 `TOOLBOX_OUTPUT_DIR` 产物落在 skill 目录 `output/`；漏设 `TOOLBOX_MODELS_DIR` 时，默认 faster-whisper 会经 ModelScope 下载 GB 级模型，Qwen/Kotoba 则会因 skill 目录下没有本地模型而报错。
3. 在上述前缀和环境变量之后调用工具：`python "<skill目录>\<工具>.py" <绝对路径输入> ...`
4. 从 `TOOLBOX_OUTPUT_DIR` 取产物交付。**`TOOLBOX_OUTPUT_DIR` 就是产物根目录本身**（产物在 `<TOOLBOX_OUTPUT_DIR>/<stem>/...`），不会再套一层 `output/`；向用户汇报产物路径前先 `ls` 核实真实位置，不要脑补目录层级。

环境与依赖：主流水线用 `conda activate video-trans`（依赖见 `requirements.txt`：faster-whisper/openai/modelscope）；可选 Qwen 后端必须用独立的 `qwen3-asr` 环境（依赖见 `requirements-qwen.txt`），可选 Kotoba 后端使用独立的 `kotoba-whisper` 环境（依赖见 `requirements-kotoba.txt`），不要混装。ffmpeg/ffprobe 在 PATH。路径契约：`<stem>` = 文件名去扩展名。**模型库**：step2 默认需要 faster-whisper 模型（GB 级），默认经 **ModelScope** 下载到 `models/faster-whisper-<size>/`；Qwen 后端读取 `Qwen3-ASR-1.7B` 和 `speech_fsmn_vad_zh-cn-16k-common-pytorch`；Kotoba 后端读取 `kotoba-whisper-v2.2`。机器上已有模型库时，先 `export TOOLBOX_MODELS_DIR=<已有 models 目录>` 避免重复下载。**唯一权威副本**：脚本以本 skill 目录为准，不要混用其他目录中的旧副本。`common.py` 是内部公共模块（路径解析/ffmpeg 封装），不直接运行。

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `large-v3-turbo` | 本地 ASR 模型大小；`models/faster-whisper-<size>` 已存在则直接用，否则经 ModelScope 自动下载 |
| `WHISPER_DEVICE` | `auto` | `cuda` / `cpu` / `auto` |
| `WHISPER_COMPUTE_TYPE` | `int8` | GPU 可设 `float16` 提速 |
| `WHISPER_BEAM_SIZE` | `5` | 解码束宽（GPU 上 run-to-run 不完全可复现，同文件两次转写条目数可能不同） |
| `QWEN_MODEL_DIR` | `models/Qwen3-ASR-1.7B` | Qwen ASR 本地模型目录 |
| `QWEN_VAD_DIR` | `models/speech_fsmn_vad_zh-cn-16k-common-pytorch` | FSMN-VAD 本地模型目录 |
| `QWEN_DEVICE` | `auto` | `cuda` / `cpu` / `auto`；GPU 用 BF16，CPU 用 FP32 |
| `QWEN_LANGUAGE` | `Japanese` | Qwen 识别语言 |
| `QWEN_CONTEXT` | 空 | 可选上下文或专名提示，能改善部分专名 |
| `QWEN_VAD_MERGE_SECONDS` | `15` | VAD 合并及最大分块秒数，范围 1～60；每块后更新 SRT |
| `KOTOBA_MODEL_DIR` | `models/kotoba-whisper-v2.2` | Kotoba 本地模型目录 |
| `KOTOBA_DEVICE` | `auto` | `cuda` / `cpu` / `auto`；GPU 用 FP16，CPU 用 FP32 |
| `KOTOBA_CHUNK_SECONDS` | `15` | Whisper 内部块长，范围 1～30 |
| `KOTOBA_GROUP_SECONDS` | `60` | 每组识别后更新 SRT |
| `KOTOBA_BATCH_SIZE` | `4` | 批大小 |
| `ASR_BACKEND` | `local` | `cloud` 时用硅基流动（纯文本+本地近似时间轴兜底，需 `SILICONFLOW_API_KEY`） |
| `SILICONFLOW_API_KEY` | 空 | cloud ASR 密钥 |
| `WHISPER_MODEL` | `FunAudioLLM/SenseVoiceSmall` | cloud ASR 模型 |
| `TOOLBOX_OUTPUT_DIR` | 空 | 产物输出根目录，跨项目使用时设为任务工作目录 |
| `TOOLBOX_MODELS_DIR` | 空 | 指向已有 ASR 模型库，避免重复下载 |

## 一、标准流水线（先问清用户要哪种产物）

**音频出片（广播节目常规）**：
```
step1_extract_audio.py → step2_transcribe.py → 翻译写 _zh.srt → reorganize_srt.py → audio_to_video.py --cover <封面> --srt <字幕>
```

**视频出片**：
```
step1 → step2 → 翻译写 _zh.srt → reorganize_srt.py（改善烧字幕观感）→ step4_burn_subtitles.py
```

**只要文字**：step1 → step2，直接交付 SRT/文本。

**双语字幕**：标准流水线跑到 reorganize/renumber 全部完成 → `merge_bilingual_srt.py` 合成双语 SRT → **交用户人工审核** → 改完 `renumber_srt.py` 重排编号 → 需要分语言样式时 `srt_to_ass.py` 转 ASS → `--srt` 指定双语产物出片。**合成和转 ASS 必须分两步，中间隔人工审核+重排，不要合并成一步。**审核时某一侧不需要的条目（如 jingle 只有原文）：**留单个空格 `" "` 占位，不要整行删除**——parse 把单空格当合法占位文本，两行结构保住，样式归属不错位、烧录时空白侧不显示。

产物命名（工具间靠这个衔接，不要改；设了 `TOOLBOX_OUTPUT_DIR` 时以下路径都在该目录下）：
- `<输出根>/temp/<stem>/audio.wav`：16kHz 单声道（ASR 专用，**不要拿它出片**，音质有损）
- `<输出根>/<stem>/<stem>_src.srt`：ASR 原文听写
- `<输出根>/<stem>/<stem>_zh.srt`：中文字幕（agent 产物；"已翻译"标记，工具优先用它）
- `<输出根>/<stem>/<stem>_video.mp4`：audio_to_video 产物；`<stem>_zh.mp4`：step4 产物

长音频转写和出片放后台跑并等完成通知；本机 28 分钟音频实测 faster-whisper/Kotoba 约 1 分钟，Qwen 约 3～5 分钟，静态封面出片约 7 分钟。后台命令里务必激活后端对应环境并带上全部环境变量（见上面第 2 条），出片类任务 timeout 提到 1800s（默认 600s 余量不足）。**后台任务随应用退出被整树杀掉（断网不影响本地进程）**：长任务期间不要退出应用；会话恢复后先用 `tasklist` 查 ffmpeg/python 进程 + 看产物文件大小是否增长，确认已死再重跑。

## 二、翻译（agent 职责，核心规范）

1. 读 `_src.srt` 逐条翻译写回 `_zh.srt`：译文逐条替换 content，**序号/时间轴一个字符都不动**，条目数严格一致。
2. **只派一个 sub agent 全程翻译**，禁止分段并行——并行必然风格漂移（人名译法、口语腔调、加减译尺度不一致）。超长文件让单代理分多次 Read 读完再逐段写回（分段"读一批写一批"即可，**不要求整篇读完才动笔**——整篇憋在思考里打草稿反而漏行，见第 6 条）。
3. 用户给了官方资料（节目名/人名写法）时，先全局统一译名再翻；ASR 明显错误（作品名、熟语）允许按上下文纠正，不确定的保留原文并告知用户。
4. 派 sub agent 时提示词写全：文件路径、条目范围（每条 4 行时条目 n = 行 4n-3~4n-1）、输出路径、硬约束。**条目数先用脚本数出精确值写进提示词**（不要写"约 615 条"——子代理的组装脚本会拿它当 assert 基准，差 1 条就白跑）。sub agent 汇报的"校验通过"不可尽信，**主代理必须跑 `verify_srt.py <_zh.srt>` 硬核对**（条目数、序号行/时间轴行逐字符比对，不过则非零退出），不通过就打回重做，禁止凭汇报放行。
5. 译名纠错这类确定性改动写成一次性脚本（从备份读入→覆盖写回），不靠手工逐条改。**批量修复脚本必须"先全部 assert 通过再统一写盘"**——assert→写→print 交错时，中途一次崩溃（如 GBK print 炸）会留下"改了一半"的状态，重跑时 assert 因目标已被替换而失败，难以收拾。
6. 子代理产出"每条一行"的纯文本译文清单极易漂移（漏行、整段错行都实测发生过）。根因：推理模型会把整篇译文先在思考里打草稿再誊抄写盘（实测 616 条 = 3 段 2.6万~3.4万字符的思考，输出 token 翻倍），漏行/错行就发生在誊抄环节。对策：提示词要求**"读一批就直接把该批译文写进中间文件，不要在思考里攒整篇草稿"**，并让子代理产出带序号的中间格式（`序号<TAB>译文`）或直接写完整 SRT，再由脚本按序号组装校验，缺行/错行立即暴露。

## 三、字幕时间轴工具

| 场景 | 工具 | 说明 |
|---|---|---|
| 自动批量修（短句合并/长句拆分/消除 <0.8s） | `reorganize_srt.py [srt] [--dry-run] [--bilingual] [--src-first]` | 先 dry-run 看统计再写回（单条超过 `--max-chars` 时仅警告并继续统计，正式写回仍会硬校验失败）；首次自动备份同名 `.bak`；阈值全可调（--merge-chars 6 / --split-chars 26 / --max-chars 38 / --min-dur-ms 800 等）；缺省取 raw/ 第一个媒体对应的 `_zh.srt`。**双语文件必须加 `--bilingual`**：字数阈值只看译文行，合并时两行各自配对连接、拆分时原文行按译文子条字数比例切分；两侧都非空才允许合并（防止"只有日文"+"只有中文"跨语言拼对）；普通模式处理双语会打散配对 |
| 手动微调（挪文本/改时间轴/增删条目都行，直接编辑 SRT） | 改完跑 `renumber_srt.py [srt]` | 把序号重排为 1..N 并规范格式（LF）；只动序号，条目内容/顺序/时间轴原样保留（空格占位行也原样保留）；start>=end 报错退出，时间重叠/乱序只警告不中断；缺省取 raw/ 第一个媒体对应的 `_zh.srt` |
| 硬性核对（翻译后必跑，替代 sub agent 自述"校验通过"） | `verify_srt.py <_zh.srt> [<_src.srt>]` 或 `--single` | 对比模式：条目数 + 序号行/时间轴行逐字符比对 + 无空译文（src 缺省取同目录同名 `_src.srt`）；`--single` 单文件体检（序号连续、start<end，重叠/乱序/<0.8s 警告）；两种模式都查编码（UTF-8 无 BOM、LF）并报告时长最长的 5 条（reorganize 后确认超长条是 jingle 段）；不过则非零退出 |
| 双语合成（**最后一步**，reorganize/renumber 全部完成后才做） | `merge_bilingual_srt.py <_zh.srt> [<_src.srt>] [-o 输出] [--src-first]` | 先内嵌对齐硬校验（条目数+时间轴毫秒级一致，不过非零退出），再合并出纯双语 SRT（每条目两行，默认译文在上原文在下，与烧录布局一致）→ `<stem>_bilingual.srt`，**交用户人工审核**。双语产物如需再自动重组，用 `reorganize_srt.py --bilingual`（普通模式会打散配对） |
| 双语 SRT 转双样式 ASS（审核 + renumber 之后） | `srt_to_ass.py <双语.srt> [-o 输出] [--src-first] [--src-font F] [--zh-size N] [--src-color C] [--zh-...]` | 每条目第 1 行→ZH 样式、第 2 行→SRC 样式（`--src-first` 交换；单行条目按 ZH 处理并警告）；烧录布局：**都在画面底部，中文在上、外文在下**（ZH MarginV 80，SRC MarginV 20 贴底边；80 是 64/48 字号下不触发 libass 行盒重叠的最小边距），字体/字号/颜色/加粗可调（默认双色均白色加粗：译文微软雅黑 64、原文 Yu Gothic 48，`--zh-bold`/`--src-bold` 传 0 关闭），烧录时传给 `--srt` |

## 四、媒体处理工具

| 工具 | 用法 |
|---|---|
| `step1_extract_audio.py [媒体]` | 提取 16kHz 单声道 wav → `<输出根>/temp/<stem>/audio.wav`（视频/音频均可；缺省取 raw/ 第一个媒体；**ASR 专用，勿拿它出片**） |
| `step2_transcribe.py [媒体]` | 本地 faster-whisper 转写（需先跑 step1；缺省取 raw/ 第一个媒体；产物 `<输出根>/<stem>/<stem>_src.srt`；30 分钟节目约 1 分钟，放后台跑） |
| `step2_transcribe_qwen.py [媒体]` | 独立 `qwen3-asr` 环境，读取本地 Qwen3-ASR + FSMN-VAD；默认 BF16、batch 1、15 秒 VAD 合并块；VAD 提供时间轴，Qwen 逐块识别并更新 `<stem>_src.srt`；不再需要 ForcedAligner。与其他转写工具产物同名，切换后端前备份 |
| `step2_transcribe_kotoba.py [媒体]` | 独立 `kotoba-whisper` 环境，读取本地 Kotoba-Whisper v2.2；默认 FP16 GPU、batch 4、15 秒内部块、60 秒分组更新 `<stem>_src.srt`；使用标准 ASR 管线，不启用说话人分离。与其他转写工具产物同名，切换后端前备份 |
| `step4_burn_subtitles.py [视频] [--srt 字幕] [--video-bitrate source] [--cpu\|--hw]` | 把字幕硬烧进原视频 → `<stem>_zh.mp4`（默认取 `_zh.srt`；`--srt` 可指定任意 srt/ass，产物名跟随字幕后缀如 `<stem>_bilingual.mp4`；音频输入自动跳过；缺省取 raw/ 第一个媒体；`--video-bitrate source` 按源视频流码率烧录且音频无损复制，缺省仍为 CRF 18；**默认仅 NVENC 自动启用 GPU**，`--hw` 强制任意硬件编码，`--cpu` 强制 libx264） |
| `clip_media.py <媒体> <起> [止] [输出] [--copy] [--video-bitrate source] [--cpu\|--hw] [-ab 96k]` | 剪切片段。时间支持 `90.5`/`1:30`/`00:01:30,500`；省略止=到末尾。默认重编码（切口精确、可与字幕对轨）且**仅 NVENC 自动启用 GPU**；视频用 `--video-bitrate source` 匹配源视频流码率且音频无损复制，不能与 `--copy` 同用；音频码率 `-ab auto`=对齐源码率上取整 48–192k 档；`--copy` 快但切口不可靠；`--hw` 强制任意硬件编码，`--cpu` 强制 libx264 |
| `audio_to_video.py <音频> --cover <图> [--srt 路径\|--no-srt] [--size WxH] [--fps N] [--crf N] [--preset P] [--cpu\|--hw]` | 封面+烧字幕出 MP4。字幕缺省取 `_zh.srt`、无则 `_src.srt`；aac/m4a 音轨无损复制，wav/flac 转 AAC 192k；默认 1920x1080@30 crf26 g600，静态封面小体积；封面任意尺寸自动缩放黑边填充；产物 `<输出根>/<stem>/<stem>_video.mp4` 跟随音频 stem；**默认仅 NVENC 自动启用 GPU**，`--hw` 强制任意硬件编码，`--cpu` 强制 libx264 |
| `convert_image.py <图> <格式或路径> [-q 2]` | webp/png/jpg/bmp/tiff 互转；jpg 质量 2(高)~31(低) |
| `download_model.py [size]` | 经 ModelScope 下载 whisper 模型到 `models/faster-whisper-<size>/`（国内友好、断点续传；官方镜像不全时自动回退全尺寸镜像；已存在则跳过） |

## 五、已知坑（血泪教训，改动时防回归）

1. **ADTS/raw aac 的容器时长是码率估算值，不可信**（某电台源实际可解码 1800s，ffprobe 只报 1765s）。后果：`-c copy` + `-t` 剪切提前截断；`.aac` 产物用 ffprobe 量时长也是假值；audio_to_video 曾因此拖出 43s 无声尾巴。对策：clip_media 音频默认重编码+解码实测校验，audio_to_video 对 .aac 输入解码实测时长。**字幕活在解码时间轴上（转写自解码后的 wav），一切对轨操作按解码时间轴来。**
2. **字幕翻译禁止分段并行派多个 agent**（风格漂移，见第二节）。
3. 分段产物禁止直接 `cat` 拼接（各段末尾换行不齐会把两条粘成一个 block，803 变 801）；必须按空行切 block 合并，脚本校验总数/序号/时间轴。
4. **Git Bash 中不要手写带 Windows 绝对路径的 ffmpeg subtitles 命令**：MSYS 可能在滤镜转义之前再次转换路径，导致盘符被拼接成非法路径。烧录统一使用 `step4_burn_subtitles.py` / `audio_to_video.py`，由 Python `subprocess` 参数列表直接传递路径。确需手动调用 ffmpeg 时，先进入任务目录并对 subtitles 滤镜使用相对路径。`common.escape_subtitles_path` 只负责 FFmpeg 滤镜内部转义，不能阻止 Git Bash 二次转换；不要把 `MSYS_NO_PATHCONV=1` 当作可靠修复。
5. `-t 时长` 取自实测，不用 `-shortest`（MP4 封装下会提前截断音轨）；静态封面不要加 `-tune stillimage`（实测体积反增 20%）；体积优化靠 crf 26 + g 600，CPU 回退时可用 `--preset slow`；封面小于输出尺寸时用 `--size` 降分辨率明显减小体积。视频编码**默认仅 NVENC 自动启用 GPU**——实测本机 QSV 在静态封面场景下比 libx264 还慢，故只有 QSV/AMF 时默认回退 CPU；`--hw` 可强制任意硬件编码，`--cpu` 可强制 libx264。**用户要求匹配源视频码率时，剪辑和烧录必须分别用 `clip_media.py` / `step4_burn_subtitles.py` 的 `--video-bitrate source`，不要手写 ffmpeg 命令**；工具会读取源视频流码率并无损复制音频，码率一致不代表重编码无损。
6. 带透明通道的图转 jpg 会变黑底。
7. **环境变量/conda 不跨 Bash 调用保留**：后台命令漏带 `TOOLBOX_MODELS_DIR` 时，默认 faster-whisper 会经 ModelScope 下载 GB 级模型并可能污染 skill 目录 `models/`；Qwen/Kotoba 不会自动下载，而是报本地模型不完整（见标准调用流程第 2 条）。
8. **本地已有 faster-whisper 模型目录的正确用法**：把 `faster-whisper-<size>/` 目录路径本身当模型名传（step2 内部即如此）；用模型名 + `download_root` 会按 HF snapshot 布局重新下载，且 Windows 无符号链接权限直接 `WinError 1314`。工具箱自身的下载已改走 ModelScope CLI（`common.ensure_model`），不再有 HF snapshot/symlink 问题。
9. **探测第三方 API 返回值先 print 原始结构再解析**：faster-whisper 的 `detect_language()` 返回三元组 `(lang, prob, all_langs)`，凭记忆 unpack 会连错。conda 环境无 soundfile，读 wav 用 stdlib `wave`。
10. **Windows 控制台是 GBK**：任何可能 print 非 GBK 字符（日文、・、☆）的 Python 脚本先 `export PYTHONIOENCODING=utf-8`，否则 print 抛 `UnicodeEncodeError`；控制台中文乱码时把对照内容写 UTF-8 文件再用 Read 读回。
11. **后台任务随应用退出被杀，断网不影响**；出片 timeout 设 1800s（见第一节末尾）。
12. **"语言识别/语音识别"在广播流水线语境下 = 转写出 SRT**（不是 language identification）；任何计算结果都要落成文件交付，只在对话里口头汇报会被用户打回。
13. **Git Bash 路径不能照抄进 PowerShell**：`/d/models/...` 这类 Git Bash 路径在 PowerShell 会被解析为 `C:\d\...`；PowerShell 统一使用 `D:\...`。Kotoba 的固定时长写盘分组还可能切断边界句子，并产生超短/超长条目，定稿前需 reorganize。

## 六、编排备忘

- 每步先确认上一步产物存在再调下一步；工具失败非零退出并打印中文原因。
- **仅激活 skill 而未给出具体任务时，先询问用户要处理的文件和产物**；不要自动选择 `raw/` 第一个媒体，也不要启动音频提取或转写。
- **不要为"确认行为"去读工具源码**：路径解析、模型解析、环境变量等契约本手册已写全，照手册执行即可；手册没覆盖的疑问或手册与实际行为矛盾时，直接向用户报告，不要擅自逆向源码。
- 用户的外部文件（封面图等）可能不在工具箱目录，直接绝对路径传入。
- 出片后要 ffprobe 验证：时长与音频/字幕对齐、编码参数符合预期、体积合理。
- 节目摘要：优先通读用户最新人工校对的 `_bilingual.srt`，没有则读 `_zh.srt`（只读 explore sub agent），输出 `[mm:ss] 主题` 时间线，跳过寒暄/jingle/语气词，保留歌曲报幕与实用通知，并保存为 `<输出根>/<stem>/<stem>_summary.txt`。
- 手动改过的文件（用户自己编辑过的 srt/aac）先确认时间戳，再继续后续工具链。
- reorganize 写回后顺手检查最长条目：节目 jingle/过门段无台词，可能被合并出 20s+ 的超长条目——确认是合理段落而非合并错误。
