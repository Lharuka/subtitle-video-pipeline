# 字幕视频流水线 Skill

让 Kimi Code agent 完成音视频转写、翻译、字幕调整、字幕烧录、片段剪辑和节目摘要。使用时只需要描述想要的产物，不需要了解内部脚本或命令。

> **Kimi Code 只是使用示例，其他 agent 也可以读取并使用这个 skill。**如果懒得手动安装，可以直接把整个目录交给 agent，让它自行阅读文档、完成安装，并结合本机环境调整。尤其要让 agent **先下载所需模型，再核对模型库及各类文件路径**，避免重复下载或因路径错误无法运行。
>
> **文档中的路径都要换成你自己的。**`<skill目录>`、`C:\Users\<你的用户名>`、`D:\models`、`D:\audio` 等只是占位符或示例。建议直接让 agent 根据你的 Windows 用户目录、媒体位置和模型库位置完成替换并逐项核对，不要原样照抄。

## 安装

### 1. 放置 skill

将整个 `subtitle-video-pipeline` 文件夹复制到 Windows 用户 skills 目录：

```text
C:\Users\<你的用户名>\.kimi-code\skills\subtitle-video-pipeline
```

复制后应存在：

```text
C:\Users\<你的用户名>\.kimi-code\skills\subtitle-video-pipeline\SKILL.md
```

请保留整个文件夹，不要只复制 `SKILL.md`；agent 需要的工具脚本和依赖清单也在其中。

### 2. 准备运行环境

默认在 Windows 下运行，需要：

- Conda
- FFmpeg 和 ffprobe，并已加入 `PATH`
- PowerShell 或 Git Bash，任选一种即可

使用 **PowerShell** 安装基础 Python 依赖：

```powershell
conda create -n video-trans python=3.12
conda activate video-trans
pip install -r "C:\Users\<你的用户名>\.kimi-code\skills\subtitle-video-pipeline\requirements.txt"
```

如果 PowerShell 中无法激活环境，先执行 `conda init powershell`，再重新打开终端。

也可以使用 **Git Bash**：

```bash
conda create -n video-trans python=3.12
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate video-trans
pip install -r "C:\Users\<你的用户名>\.kimi-code\skills\subtitle-video-pipeline\requirements.txt"
```

### 3. 先下载模型

建议在安装完成后、首次使用 skill 前，预先下载默认识别模型，不要等到实际转写时才开始下载。保持 `video-trans` 环境激活，在 PowerShell 或 Git Bash 中执行：

```text
python "C:\Users\<你的用户名>\.kimi-code\skills\subtitle-video-pipeline\download_model.py"
```

模型体积较大，请保持网络可用并预留足够磁盘空间。如果电脑上已有模型库，无需重复下载，但要先把模型目录告诉 agent，并让它核对路径。

除默认的 faster-whisper 外，skill 还适配了其他识别模型：

- **Qwen3-ASR**：`step2_transcribe_qwen.py`，依赖见 `requirements-qwen.txt`
- **Kotoba-Whisper**：`step2_transcribe_kotoba.py`，依赖见 `requirements-kotoba.txt`

这些后端使用独立环境。需要切换模型时，可以让 agent 安装对应环境、下载匹配模型并核对路径，不需要手动研究脚本参数。

## 使用

通常不需要手动激活，agent 可能会根据任务自动调用 skill。也可以用自然语言明确告诉 agent：

```text
请使用 subtitle-video-pipeline skill 处理这个任务。
```

如果希望手动加载，也可以执行 `/subtitle-video-pipeline`，然后再描述任务。

然后直接说明任务，例如：

```text
把 D:\audio\program.mp4 转写成日文字幕，再翻译成中文字幕。
```

```text
截取 D:\audio\program.mp4 的 04:05–33:50，匹配源视频码率，生成双语字幕并烧录。
```

```text
用 D:\audio\cover.jpg 作为封面，把 D:\audio\program.aac 做成带中文字幕的视频。
```

```text
根据 D:\audio\program\program_bilingual.srt 生成时间轴内容摘要。
```

描述任务时最好提供：

- 媒体或字幕文件的完整路径
- 想要的产物，例如原文 SRT、中文字幕、双语字幕或烧录视频
- 可选的封面、剪辑时间段、官方人名和作品名译法

agent 会自动选择工具、处理中间文件并校验结果，完成后告知产物位置。双语字幕在正式出片前通常需要你人工审核；长时间任务运行期间请保持 Kimi Code 打开。

## 其他文档

- `SKILL.md`：供 agent 使用的内部执行手册。
- `COMMANDLINE.md`：供需要绕过 agent、手动执行命令的用户使用。

## 工作方式不是固定流水线

上面的示例只是常见用法，不是写死的工作流。agent 可以根据实际任务自由选择、组合或跳过步骤，例如只转写、只校对、只剪辑，或更换识别模型后再继续处理。

这个 skill 也需要根据真实任务轨迹不断迭代：把执行中暴露的问题、更好的处理方式和新的环境差异沉淀回文档与脚本，而不是把现有示例当成永远不变的规则。
