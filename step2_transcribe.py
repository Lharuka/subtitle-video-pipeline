#!/usr/bin/env python3
"""
步骤2：语音转文字
默认使用本地 faster-whisper（免费，带时间戳 SRT），默认模型 large-v3-turbo。
也可切回硅基流动（纯文本，本地近似时间轴兜底）。

用法:
  python step2_transcribe.py raw/sample.mp4
  python step2_transcribe.py raw/xxx.aac
  python step2_transcribe.py              # 自动处理 raw/ 下第一个媒体文件

环境变量:
  ASR_BACKEND=local   # 默认，本地 faster-whisper
  ASR_BACKEND=cloud   # 使用硅基流动
  WHISPER_MODEL_SIZE      # local 时有效，默认 large-v3-turbo；
                          # 若 models/faster-whisper-<size> 目录存在则直接使用，否则自动下载
  WHISPER_DEVICE          # 默认 auto（cuda / cpu / auto）
  WHISPER_COMPUTE_TYPE    # 默认 int8（GPU 可用 float16 提速）
  WHISPER_BEAM_SIZE       # 默认 5
"""

import os
import sys
import json
import subprocess
from pathlib import Path

from common import resolve_media_path, get_output_dir, get_temp_dir, MODELS_DIR, ensure_model



ASR_BACKEND = os.getenv("ASR_BACKEND", "local")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "large-v3-turbo")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))

# 硅基流动配置（cloud 模式用）
CLOUD_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
CLOUD_BASE_URL = "https://api.siliconflow.cn/v1"
CLOUD_MODEL = os.getenv("WHISPER_MODEL", "FunAudioLLM/SenseVoiceSmall")


def resolve_model_id(model_size: str) -> str:
    """本地模型目录路径；缺失时经 ModelScope 自动下载（见 common.ensure_model）。"""
    return str(ensure_model(model_size))


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(audio_path)],
        capture_output=True, text=True, check=True
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def format_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def text_to_srt(text: str, duration_sec: float, srt_path: Path):
    """纯文本无时间戳时，按句子近似均分生成 SRT（兜底方案）。"""
    import re
    sentences = [s.strip() for s in re.split(r'(?<=[。！？.!?])\s+', text) if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    step = duration_sec / len(sentences)
    lines = []
    for i, sent in enumerate(sentences, 1):
        start = (i - 1) * step
        end = i * step
        lines.append(f"{i}")
        lines.append(f"{format_time(start)} --> {format_time(end)}")
        lines.append(sent)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def transcribe_local(audio_path: Path, srt_path: Path):
    """本地 faster-whisper，直接输出带时间戳的 SRT。"""
    from faster_whisper import WhisperModel

    model_id = resolve_model_id(WHISPER_MODEL_SIZE)
    print(f"模型: {model_id}")

    model = WhisperModel(
        model_id,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
        download_root=str(MODELS_DIR),
        local_files_only=False,
    )
    segments, info = model.transcribe(str(audio_path), beam_size=WHISPER_BEAM_SIZE, language=None)
    print(f"[检测到语言] {info.language} (概率: {info.language_probability:.2f})")

    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_time(seg.start)
        end = format_time(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")

    srt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[转写完成] -> {srt_path}")


def transcribe_cloud(audio_path: Path, srt_path: Path):
    """硅基流动云端 ASR（纯文本兜底）。"""
    from openai import OpenAI
    client = OpenAI(api_key=CLOUD_API_KEY, base_url=CLOUD_BASE_URL)

    with open(audio_path, "rb") as f:
        try:
            transcript = client.audio.transcriptions.create(
                model=CLOUD_MODEL, file=f, response_format="srt",
            )
            text = transcript if isinstance(transcript, str) else transcript.text
            srt_path.write_text(text, encoding="utf-8")
            print(f"[转写完成] -> {srt_path}")
            return
        except Exception as e:
            print(f"[!] SRT 格式不支持: {e}")
            print("[!] fallback -> 纯文本 + 本地近似时间轴")

    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(model=CLOUD_MODEL, file=f)
    text = transcript.text if hasattr(transcript, "text") else str(transcript)
    duration = get_audio_duration(audio_path)
    text_to_srt(text, duration, srt_path)
    print(f"[转写完成(纯文本兜底)] -> {srt_path}")


def main():
    media_path = resolve_media_path(sys.argv)

    work_temp = get_temp_dir() / media_path.stem
    audio_path = work_temp / "audio.wav"
    if not audio_path.exists():
        print(f"错误: 未找到音频 {audio_path}，请先运行 step1_extract_audio.py")
        sys.exit(1)

    work_output = get_output_dir() / media_path.stem
    work_output.mkdir(parents=True, exist_ok=True)
    srt_path = work_output / f"{media_path.stem}_src.srt"

    print(f"处理音频: {audio_path}")
    print(f"ASR 后端: {ASR_BACKEND}")

    if ASR_BACKEND == "cloud":
        if not CLOUD_API_KEY:
            print("错误: cloud 模式需设置 SILICONFLOW_API_KEY")
            sys.exit(1)
        transcribe_cloud(audio_path, srt_path)
    else:
        transcribe_local(audio_path, srt_path)


if __name__ == "__main__":
    main()
