#!/usr/bin/env python3
"""公共工具：输入媒体文件解析（同时支持视频和音频）、产物输出根目录。"""

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLBOX_ROOT = Path(__file__).resolve().parent  # 工具脚本所在目录（skill 目录或工具箱仓库根）
RAW_DIR = TOOLBOX_ROOT / "raw"
TEMP_DIR = TOOLBOX_ROOT / "temp"
# 模型体积大（GB 级），允许用环境变量指向已有模型库避免重复下载
MODELS_DIR = Path(os.environ.get("TOOLBOX_MODELS_DIR", TOOLBOX_ROOT / "models"))

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v", ".ts"}
AUDIO_EXTS = {".aac", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".wma"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def resolve_media_path(argv) -> Path:
    """命令行指定则校验后使用，否则取 raw/ 下第一个媒体文件（视频或音频）。"""
    if len(argv) >= 2:
        media_path = Path(argv[1])
        if not media_path.exists():
            print(f"错误: 文件不存在 {media_path}")
            sys.exit(1)
        if not (is_video(media_path) or is_audio(media_path)):
            print(f"错误: 不支持的文件类型 {media_path.suffix}（支持: {sorted(MEDIA_EXTS)}）")
            sys.exit(1)
        return media_path

    files = sorted(p for ext in MEDIA_EXTS for p in RAW_DIR.glob(f"*{ext}"))
    if not files:
        print("用法: python <脚本> raw/xxx.mp4|xxx.aac")
        print(f"或放入媒体文件到 {RAW_DIR}/ 后不带参数运行")
        sys.exit(1)
    return files[0]


def escape_subtitles_path(srt_path: Path) -> str:
    """生成 ffmpeg subtitles 滤镜可用的路径字面量（正斜杠 + 转义盘符冒号，空格由调用方用单引号包裹）。"""
    return str(srt_path).replace("\\", "/").replace(":", "\\:")


def get_output_dir() -> Path:
    """产物输出根目录：环境变量 TOOLBOX_OUTPUT_DIR（通常设为用户的任务工作目录）优先，
    未设置时默认脚本目录下的 output/。所有写产物的工具必须用它而不是硬编码 Path("output")。"""
    root = os.environ.get("TOOLBOX_OUTPUT_DIR")
    return Path(root) if root else TOOLBOX_ROOT / "output"


def get_temp_dir() -> Path:
    """临时文件根目录：环境变量 TOOLBOX_OUTPUT_DIR 优先（与产物同目录，避免不同任务污染 skill 目录），
    未设置时默认脚本目录下的 temp/。"""
    root = os.environ.get("TOOLBOX_OUTPUT_DIR")
    return Path(root) / "temp" if root else TEMP_DIR


_HW_ENCODERS_CACHE: list[str] | bool = False  # False 表示尚未检测


def _test_hw_encoder(name: str) -> bool:
    """用极短空白视频实际测试硬件编码器是否可用（仅列出不代表有对应 GPU）。"""
    try:
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
            "-c:v", name, "-f", "null", "-"
        ], capture_output=True, check=True, timeout=15)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def detect_hw_encoders() -> list[str]:
    """检测所有可用的硬件 H.264 编码器，按 NVENC > QSV > AMF 排序，结果缓存到进程结束。"""
    global _HW_ENCODERS_CACHE
    if _HW_ENCODERS_CACHE is not False:
        return _HW_ENCODERS_CACHE  # type: ignore[return-value]
    available = []
    for name in ("h264_nvenc", "h264_qsv", "h264_amf"):
        if _test_hw_encoder(name):
            available.append(name)
    _HW_ENCODERS_CACHE = available
    return available


def get_video_bitrate(media_path: Path) -> str:
    """读取首个视频流的码率（bps）；容器未提供码率时给出明确错误。"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=bit_rate", "-of", "default=nw=1:nk=1", str(media_path)
        ], capture_output=True, text=True, check=True)
        bitrate = result.stdout.strip()
        if not bitrate.isdigit() or int(bitrate) <= 0:
            raise ValueError
        return bitrate
    except (subprocess.CalledProcessError, ValueError):
        raise ValueError(f"无法读取源视频码率: {media_path}（容器可能未记录视频流码率）") from None


def build_video_codec_args(crf: int, preset: str, force_cpu: bool = False, force_hw: bool = False,
                           video_bitrate: str | None = None) -> list[str]:
    """返回视频编码参数；指定 video_bitrate 时用码率模式替代质量模式。

    默认只有 NVIDIA NVENC 才启用 GPU（QSV/AMF 在部分场景下比 libx264 还慢）；
    force_hw=True 时强制使用任意可用的硬件编码器；force_cpu=True 时强制 libx264。
    """
    if force_cpu:
        encoder = None
    else:
        available = detect_hw_encoders()
        if force_hw:
            encoder = available[0] if available else None
        else:
            encoder = "h264_nvenc" if "h264_nvenc" in available else None
    if encoder == "h264_nvenc":
        if video_bitrate:
            return ["-c:v", encoder, "-preset", "p4", "-rc", "cbr",
                    "-b:v", video_bitrate, "-minrate", video_bitrate, "-maxrate", video_bitrate,
                    "-bufsize", str(int(video_bitrate) * 2)]
        return ["-c:v", encoder, "-preset", "p4", "-rc", "vbr", "-cq", str(crf)]
    if encoder == "h264_qsv":
        if video_bitrate:
            return ["-c:v", encoder, "-preset", "medium", "-b:v", video_bitrate]
        return ["-c:v", encoder, "-preset", "medium", "-global_quality", str(crf)]
    if encoder == "h264_amf":
        if video_bitrate:
            return ["-c:v", encoder, "-quality", "balanced", "-b:v", video_bitrate]
        return ["-c:v", encoder, "-quality", "balanced", "-qp_i", str(crf), "-qp_p", str(crf)]
    if video_bitrate:
        return ["-c:v", "libx264", "-b:v", video_bitrate, "-preset", preset]
    return ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]


def ensure_model(model_size: str) -> Path:
    """返回 faster-whisper 本地模型目录；缺失时经 ModelScope 自动下载（国内友好，断点续传）。
    候选 id：官方镜像 mobiuslabsgmbh（只镜像了部分尺寸）→ pengzhendong（全尺寸）。"""
    local_dir = MODELS_DIR / f"faster-whisper-{model_size}"
    if (local_dir / "model.bin").exists():
        return local_dir
    for ms_id in (f"mobiuslabsgmbh/faster-whisper-{model_size}",
                  f"pengzhendong/faster-whisper-{model_size}"):
        print(f"本地未找到模型，尝试下载: {ms_id} -> {local_dir}")
        cmd = ["modelscope", "download", "--model", ms_id, "--local_dir", str(local_dir)]
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            print("错误: 未找到 modelscope 命令，请先 conda activate video-trans（或 pip install modelscope）")
            sys.exit(1)
        except subprocess.CalledProcessError:
            continue  # 该候选不存在或下载失败，试下一个
        if (local_dir / "model.bin").exists():
            return local_dir
        print(f"候选 {ms_id} 下载不完整，尝试下一个")
    print(f"错误: 模型 {model_size} 自动下载失败")
    print(f"请手动运行 python download_model.py {model_size}，或设 TOOLBOX_MODELS_DIR 指向已有模型库")
    sys.exit(1)


def get_media_duration(media_path: Path) -> float:
    """ffprobe 获取媒体时长（秒）。"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(media_path)],
        capture_output=True, text=True, check=True
    )
    return float(json.loads(result.stdout)["format"]["duration"])
