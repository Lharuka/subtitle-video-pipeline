# 个人翻译工具箱 · 命令行速查

媒体文件 → 转写 → 翻译 → 字幕微调 → 封面视频/烧字幕视频，全流程 15 个脚本。
**除"翻译"外每一步都可以直接在命令行跑**，不依赖 agent。

脚本路径自定位（以脚本所在目录为基准），在任意目录用绝对路径调用即可，不用 cd。
下文用 `$TB` 代指工具箱目录（**唯一权威副本**）：

```bash
TB="$HOME/.kimi-code/skills/subtitle-video-pipeline"   # 按实际安装位置修改
```

已有模型库可用 `TOOLBOX_MODELS_DIR` 指向，避免重复下载；脚本只使用本目录，不要混用其他旧副本。

## 0. 一次性准备

```bash
conda create -n video-trans python=3.12
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate video-trans
pip install -r "$TB/requirements.txt"     # faster-whisper / openai / modelscope
ffmpeg -version                           # ffmpeg、ffprobe 要在 PATH（系统依赖，单独装）
python "$TB/download_model.py"            # 经 ModelScope 下载默认模型 large-v3-turbo（国内友好，已有则跳过）
```

机器上已有模型库就不用下载，用 `TOOLBOX_MODELS_DIR` 指过去（见下表）。

Qwen3-ASR 是可选后端，官方要求独立环境，不要装进 `video-trans`：

```bash
conda create -n qwen3-asr python=3.12 -y
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate qwen3-asr
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r "$TB/requirements-qwen.txt"
# 使用已有 video-trans 环境的 ModelScope CLI 下载两个必需模型
conda run -n video-trans modelscope download --model Qwen/Qwen3-ASR-1.7B --local_dir "D:\models\Qwen3-ASR-1.7B"
conda run -n video-trans modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir "D:\models\speech_fsmn_vad_zh-cn-16k-common-pytorch"
```

Kotoba-Whisper 也使用独立环境；PowerShell 下载模型时请使用 Windows 路径：

```bash
conda create -n kotoba-whisper python=3.11 -y
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate kotoba-whisper
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r "$TB/requirements-kotoba.txt"
hf download kotoba-tech/kotoba-whisper-v2.2 --local-dir "D:\models\kotoba-whisper-v2.2"
```

## 1. 环境变量（每次新开终端都要设）

| 变量 | 什么时候需要 | 示例 |
|---|---|---|
| `TOOLBOX_OUTPUT_DIR` | 想让产物落到当前项目目录而不是工具箱 `output/` | `export TOOLBOX_OUTPUT_DIR="$PWD"` |
| `TOOLBOX_MODELS_DIR` | 机器上已有 ASR 模型库，避免重复下载 GB 级模型 | `export TOOLBOX_MODELS_DIR="D:\models"` |
| `WHISPER_MODEL_SIZE` | 换 faster-whisper 模型大小 | `export WHISPER_MODEL_SIZE=small` |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | 指定 cuda/cpu、GPU 提速 | `export WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16` |
| `QWEN_MODEL_DIR` / `QWEN_VAD_DIR` | 覆盖 Qwen ASR / FSMN-VAD 本地目录 | 默认在 `TOOLBOX_MODELS_DIR` 下 |
| `QWEN_LANGUAGE` / `QWEN_CONTEXT` | Qwen 语言及可选专名上下文 | 默认 `Japanese`，上下文为空 |
| `QWEN_VAD_MERGE_SECONDS` | VAD 合并及最大分块秒数 | 默认 `15`，范围 1～60 |
| `KOTOBA_MODEL_DIR` / `KOTOBA_DEVICE` | Kotoba 模型目录及 cuda/cpu/auto | 默认模型在 `TOOLBOX_MODELS_DIR` 下，自动优先 GPU |
| `KOTOBA_CHUNK_SECONDS` / `KOTOBA_GROUP_SECONDS` | 内部块长 / 写盘分组秒数 | 默认 `15` / `60` |
| `KOTOBA_BATCH_SIZE` | Kotoba 批大小 | 默认 `4` |
| `ASR_BACKEND=cloud` + `SILICONFLOW_API_KEY` | 用云端 ASR 而不是本地 | 一般不用的 |

**注意**：每条命令都是全新 shell，环境变量不跨命令保留——后台跑长任务时，先使用
`source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate <环境>`，再在同一命令中设置这些 `export`。

## 2. 典型流程（复制即用）

### A. 广播/播客音频 → 封面视频（中文字幕）

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate video-trans
export TOOLBOX_OUTPUT_DIR="$PWD"
export TOOLBOX_MODELS_DIR="D:\models"

python "$TB/step1_extract_audio.py" 节目.aac
python "$TB/step2_transcribe.py"   节目.aac
# → 得到 output根目录/节目/节目_src.srt（原文听写）

# ---- 翻译：把 _src.srt 逐条译成中文，存为同目录 _zh.srt（agent 或人工）----

python "$TB/verify_srt.py"     节目/节目_zh.srt            # 硬性核对，不过别往下走
python "$TB/reorganize_srt.py" 节目/节目_zh.srt --dry-run  # 先看统计
python "$TB/reorganize_srt.py" 节目/节目_zh.srt            # 合并过短/拆分过长
python "$TB/audio_to_video.py" 节目.aac --cover 封面.jpg   # 出片
```

### B. 视频 → 烧字幕视频

同上跑到 `reorganize_srt.py`，最后一步换成：

```bash
python "$TB/step4_burn_subtitles.py" 视频.mp4          # 默认烧 _zh.srt
python "$TB/step4_burn_subtitles.py" 视频.mp4 --srt 其它字幕.ass   # 或指定任意 srt/ass
python "$TB/step4_burn_subtitles.py" 视频.mp4 --srt 其它字幕.ass --video-bitrate source  # 匹配源视频码率
```

### C. 双语字幕（中文在上、外文在下）

在流程 A/B 的字幕定稿（reorganize/renumber 全部完成）之后：

```bash
python "$TB/merge_bilingual_srt.py" 节目/节目_zh.srt
# → 节目_bilingual.srt（每条目两行：上中文下原文），人工审核
#   审核时某一侧不需要的条目留单个空格 " " 占位，不要整行删除
python "$TB/renumber_srt.py" 节目/节目_bilingual.srt    # 审核改完重排编号
python "$TB/srt_to_ass.py"     节目/节目_bilingual.srt  # 转双样式 ASS（可选）
# 出片时把双语文件传给 --srt：
python "$TB/audio_to_video.py" 节目.aac --cover 封面.jpg --srt 节目/节目_bilingual.ass
```

### D. 只要剪一段

```bash
python "$TB/clip_media.py" 节目.aac 0:59 1:06        # 剪 0:59~1:06
python "$TB/clip_media.py" 视频.mp4 1:30             # 从 1:30 剪到末尾
python "$TB/clip_media.py" 视频.mp4 4:05 33:50 --video-bitrate source  # 匹配源视频码率
```

## 3. 工具逐个看

### 转写

| 工具 | 用法 | 说明 |
|---|---|---|
| `step1_extract_audio.py [媒体]` | 视频/音频均可 | 提取 16kHz 单声道 wav → `<输出根>/temp/<stem>/audio.wav`。**ASR 专用，音质有损，别拿它出片** |
| `step2_transcribe.py [媒体]` | 需先跑 step1 | **默认后端**：本地 faster-whisper large-v3-turbo 转写 → `<stem>_src.srt`。30 分钟节目约 1 分钟 |
| `step2_transcribe_qwen.py [媒体]` | 独立 `qwen3-asr` 环境，需先跑 step1 | 可选后端：本地 Qwen3-ASR + FSMN-VAD，BF16 优先 GPU；VAD 提供时间轴，相邻短段合并后逐块识别并更新 `<stem>_src.srt`；不再需要 ForcedAligner |
| `step2_transcribe_kotoba.py [媒体]` | 独立 `kotoba-whisper` 环境，需先跑 step1 | 可选后端：本地 Kotoba-Whisper v2.2，FP16 优先 GPU；标准 Whisper 时间戳，默认 15 秒内部块、60 秒分组更新 `<stem>_src.srt`；不启用说话人分离 |
| `download_model.py [大小]` | 默认 large-v3-turbo | 仅预下载默认 faster-whisper 模型（ModelScope、断点续传）；不下载 Qwen/Kotoba 模型 |

三个本地 ASR 后端都写入 `<stem>_src.srt`，切换后端会覆盖同文件，需先备份。使用 Qwen/Kotoba 时仍先用 `video-trans` 环境跑 step1，再激活各自环境跑对应的 step2 脚本。Kotoba 按固定时长分组，边界可能断句，也可能产生超短或超长条目；定稿前用 `reorganize_srt.py` 调整。

### 字幕加工

| 工具 | 用法 | 说明 |
|---|---|---|
| `verify_srt.py <_zh.srt> [<_src.srt>]` | 翻译后必跑 | 硬核对：条目数 + 序号/时间轴逐字符比对 + 无空译文，不过则非零退出。`--single` 单文件体检；两种模式都会列出时长最长的 5 条 |
| `reorganize_srt.py <srt> [--dry-run] [--bilingual] [--src-first]` | 改善烧字幕观感 | 合并过短（≤6 字）、拆分过长（≥26 字）、消除 <0.8s 条目。先 `--dry-run` 看统计再写回（单条超过 `--max-chars` 时仅警告并继续统计，正式写回仍会硬校验失败）；首次自动备份 `.bak`；阈值可用 `--merge-chars`/`--split-chars`/`--max-chars`/`--min-dur-ms` 等调。**双语文件必须加 `--bilingual`**：阈值只看译文行，合并/拆分保持两行配对不错位；普通模式处理双语会打散配对 |
| `renumber_srt.py <srt>` | 手动改过 SRT 之后 | 序号重排 1..N、规范 LF。只动序号，内容/时间轴原样保留（单空格占位行也保留）；start≥end 报错，重叠/乱序只警告 |
| `merge_bilingual_srt.py <_zh.srt> [<_src.srt>] [--src-first]` | 双语合成 | 内嵌对齐硬校验后合并出 `_bilingual.srt`（默认上中文下原文）。推荐单语定稿后再合并；产物如需再重组用 `reorganize_srt.py --bilingual` |
| `srt_to_ass.py <双语.srt> [--src-first] [--zh-size 64] [--src-size 48] [--zh-font F] [--src-color &H..] [--zh-bold 0\|1] ...` | 要分语言样式时 | 转双样式 ASS：中文微软雅黑 64 加粗在上，原文 Yu Gothic 48 加粗贴底边，双色默认白色。单行条目按中文样式处理并警告（用空格占位避免） |

### 出片与媒体处理

| 工具 | 用法 | 说明 |
|---|---|---|
| `audio_to_video.py <音频> --cover <图> [--srt 字幕 \| --no-srt] [--size WxH] [--fps N] [--crf N] [--preset P] [--cpu\|--hw]` | 音频 → 封面视频 | 字幕缺省取 `_zh.srt`、无则 `_src.srt`；aac/m4a 音轨无损复制；默认 1920x1080 crf26，静态封面小体积；**默认仅 NVENC 自动启用 GPU**，`--hw` 强制任意硬件编码，`--cpu` 强制 libx264 |
| `step4_burn_subtitles.py [视频] [--srt 字幕] [--video-bitrate source] [--cpu\|--hw]` | 字幕硬烧进原视频 | 默认烧 `_zh.srt` → `<stem>_zh.mp4`；`--srt` 可指定任意 srt/ass，产物名跟随字幕后缀；`--video-bitrate source` 匹配源视频流码率且音频无损复制，缺省仍为 CRF 18；**默认仅 NVENC 自动启用 GPU**，`--hw` 强制任意硬件编码，`--cpu` 强制 libx264 |
| `clip_media.py <媒体> <起> [止] [输出] [--copy] [--video-bitrate source] [--cpu\|--hw] [-ab 96k]` | 剪片段 | 时间支持 `90.5`/`1:30`/`00:01:30,500`；默认重编码（切口精确、可对轨）且**仅 NVENC 自动启用 GPU**；视频用 `--video-bitrate source` 匹配源视频流码率且音频无损复制，不能与 `--copy` 同用；`--copy` 快但切口不可靠；`--hw` 强制任意硬件编码，`--cpu` 强制 libx264 |
| `convert_image.py <图> <格式或路径> [-q 2]` | 图片互转 | webp/png/jpg/bmp/tiff；jpg 质量 2(高)~31(低)。透明图转 jpg 会变黑底 |

## 4. 命名约定（工具间靠它衔接，别改）

`<stem>` = 文件名去掉扩展名。设了 `TOOLBOX_OUTPUT_DIR` 时"输出根目录"就是它本身（**不会再套一层 `output/`**）：

| 路径 | 是什么 |
|---|---|
| `<输出根>/temp/<stem>/audio.wav` | step1 产物，ASR 专用；设了 `TOOLBOX_OUTPUT_DIR` 时落在该目录下，避免污染 skill 目录 |
| `<输出根>/<stem>/<stem>_src.srt` | step2 产物：原文听写 |
| `<输出根>/<stem>/<stem>_zh.srt` | 中文字幕（"已翻译"标记，工具优先用它） |
| `<输出根>/<stem>/<stem>_bilingual.srt` / `.ass` | 双语产物 |
| `<输出根>/<stem>/<stem>_video.mp4` | audio_to_video 产物 |
| `<输出根>/<stem>/<stem>_zh.mp4` | step4 产物 |

## 5. 常见坑速查

- **新开终端/后台命令**：激活对应环境并重新设置 `export`；漏 `TOOLBOX_MODELS_DIR` 时，默认 faster-whisper 会经 ModelScope 下载模型，Qwen/Kotoba 会报本地模型不完整
- **命令行路径**：本文示例按 Git Bash 编写；PowerShell 中使用 `D:\...`，不要把 `/d/...` 当成 Windows 路径，否则会落到 `C:\d\...`
- **Git Bash 字幕路径**：烧录优先使用工具脚本；手调 FFmpeg 时对 subtitles 滤镜使用任务目录下的相对路径，不要把 `MSYS_NO_PATHCONV=1` 当作可靠修复
- **Windows 控制台 GBK**：脚本打印日文/中文乱码或报 `UnicodeEncodeError` 时 `export PYTHONIOENCODING=utf-8`（PowerShell 用 `$env:PYTHONIOENCODING="utf-8"`）
- **后台任务随应用退出被杀**（断网不影响）；出片类命令 timeout 建议 1800s
- **.aac（ADTS）时长不可信**：剪切、对轨都按解码后时间轴来，工具已内置实测校验
- 详细血泪史见 skill 手册 `SKILL.md` 第五节
