#!/usr/bin/env python3
"""
步骤2备选：使用本地 Kotoba-Whisper v2.2 转写日文字幕。

使用标准 Transformers ASR 管线，不启用说话人分离或标点后处理。
每组音频完成后更新 SRT，需先执行 step1_extract_audio.py。

用法:
  conda activate kotoba-whisper
  python step2_transcribe_kotoba.py raw/sample.aac

环境变量:
  KOTOBA_MODEL_DIR      # 默认 models/kotoba-whisper-v2.2
  KOTOBA_DEVICE         # 默认 auto（cuda / cpu / auto）
  KOTOBA_CHUNK_SECONDS  # Whisper 内部块长，默认 15 秒
  KOTOBA_GROUP_SECONDS  # 每批写入 SRT 的音频长度，默认 60 秒
  KOTOBA_BATCH_SIZE     # 批大小，默认 4
"""

import os
import sys
import time
import wave
from pathlib import Path

from common import MODELS_DIR, get_output_dir, get_temp_dir, resolve_media_path


KOTOBA_MODEL_DIR = Path(os.getenv(
    "KOTOBA_MODEL_DIR", str(MODELS_DIR / "kotoba-whisper-v2.2")
))
KOTOBA_DEVICE = os.getenv("KOTOBA_DEVICE", "auto").lower()
KOTOBA_CHUNK_SECONDS = int(os.getenv("KOTOBA_CHUNK_SECONDS", "15"))
KOTOBA_GROUP_SECONDS = int(os.getenv("KOTOBA_GROUP_SECONDS", "60"))
KOTOBA_BATCH_SIZE = int(os.getenv("KOTOBA_BATCH_SIZE", "4"))


def format_time(sec: float) -> str:
    total_ms = max(0, round(sec * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_srt(entries: list[dict], srt_path: Path) -> bool:
    lines = []
    for index, segment in enumerate(entries, 1):
        lines.append(str(index))
        lines.append(f"{format_time(segment['start'])} --> {format_time(segment['end'])}")
        lines.append(segment["text"])
        lines.append("")
    content = "\n".join(lines)
    temp_path = srt_path.with_suffix(srt_path.suffix + ".tmp")
    for attempt in range(3):
        try:
            temp_path.write_text(content, encoding="utf-8", newline="\n")
            temp_path.replace(srt_path)
            return True
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    try:
        srt_path.write_text(content, encoding="utf-8", newline="\n")
        temp_path.unlink(missing_ok=True)
        return True
    except PermissionError:
        print("警告: SRT 正被其他程序占用，本次更新未写入；后续分组会继续重试", flush=True)
        return False


def load_audio(audio_path: Path):
    import numpy as np

    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            print("错误: 输入必须是 step1 生成的 16 kHz、单声道、16-bit PCM WAV")
            sys.exit(1)
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_kotoba(audio_path: Path, srt_path: Path):
    try:
        import torch
        from transformers import pipeline
    except ImportError:
        print("错误: 缺少 torch 或 transformers，请使用独立 kotoba-whisper 环境")
        sys.exit(1)

    if KOTOBA_DEVICE not in {"auto", "cuda", "cpu"}:
        print(f"错误: KOTOBA_DEVICE 仅支持 auto/cuda/cpu，当前为 {KOTOBA_DEVICE}")
        sys.exit(1)
    if not 1 <= KOTOBA_CHUNK_SECONDS <= 30:
        print("错误: KOTOBA_CHUNK_SECONDS 必须在 1～30 之间")
        sys.exit(1)
    if KOTOBA_GROUP_SECONDS < KOTOBA_CHUNK_SECONDS:
        print("错误: KOTOBA_GROUP_SECONDS 不能小于 KOTOBA_CHUNK_SECONDS")
        sys.exit(1)
    if KOTOBA_BATCH_SIZE < 1:
        print("错误: KOTOBA_BATCH_SIZE 必须大于 0")
        sys.exit(1)
    if KOTOBA_DEVICE == "cuda" and not torch.cuda.is_available():
        print("错误: 已指定 CUDA，但当前 PyTorch 无法使用 GPU")
        sys.exit(1)
    for file_name in ("config.json", "model.safetensors", "preprocessor_config.json", "tokenizer.json"):
        if not (KOTOBA_MODEL_DIR / file_name).is_file():
            print(f"错误: Kotoba-Whisper 模型不完整，未找到 {KOTOBA_MODEL_DIR / file_name}")
            sys.exit(1)

    use_cuda = KOTOBA_DEVICE == "cuda" or (KOTOBA_DEVICE == "auto" and torch.cuda.is_available())
    device = "cuda:0" if use_cuda else "cpu"
    dtype = torch.float16 if use_cuda else torch.float32
    print(f"ASR 模型: {KOTOBA_MODEL_DIR}")
    print(f"设备: {device}，精度: {'FP16' if use_cuda else 'FP32'}")
    print(
        f"内部块长: {KOTOBA_CHUNK_SECONDS} 秒，写盘分组: {KOTOBA_GROUP_SECONDS} 秒，"
        f"批大小: {KOTOBA_BATCH_SIZE}"
    )
    model_kwargs = {"attn_implementation": "sdpa"} if use_cuda else {}
    asr = pipeline(
        task="automatic-speech-recognition",
        model=str(KOTOBA_MODEL_DIR),
        dtype=dtype,
        device=device,
        batch_size=KOTOBA_BATCH_SIZE,
        trust_remote_code=False,
        model_kwargs=model_kwargs,
    )

    samples = load_audio(audio_path)
    sample_rate = 16000
    group_size = KOTOBA_GROUP_SECONDS * sample_rate
    group_count = (len(samples) + group_size - 1) // group_size
    entries = []
    write_srt(entries, srt_path)
    started_at = time.perf_counter()

    for group_index in range(group_count):
        group_start = group_index * group_size
        group_end = min(len(samples), group_start + group_size)
        group_samples = samples[group_start:group_end]
        offset = group_start / sample_rate
        result = asr(
            {"array": group_samples, "sampling_rate": sample_rate},
            chunk_length_s=KOTOBA_CHUNK_SECONDS,
            stride_length_s=(KOTOBA_CHUNK_SECONDS / 6, KOTOBA_CHUNK_SECONDS / 6),
            return_timestamps=True,
            generate_kwargs={"language": "ja", "task": "transcribe"},
        )
        group_entries = []
        for chunk in result.get("chunks", []):
            text = chunk["text"].strip()
            start, end = chunk["timestamp"]
            start = offset + (start or 0)
            end = offset + (end if end is not None else len(group_samples) / sample_rate)
            if text and end > start:
                group_entries.append({"start": start, "end": end, "text": text})
        entries.extend(group_entries)
        if not write_srt(entries, srt_path):
            print("错误: SRT 仍被其他程序占用，请关闭占用程序后重试")
            sys.exit(1)
        print(
            f"[分组 {group_index + 1}/{group_count}] 新增 {len(group_entries)} 条，"
            f"累计 {len(entries)} 条，耗时 {time.perf_counter() - started_at:.1f} 秒",
            flush=True,
        )

    if use_cuda:
        print(f"峰值显存: {torch.cuda.max_memory_allocated() / 1024**3:.2f} GiB")
    print(f"[转写完成] 共 {len(entries)} 条 -> {srt_path}")


def main():
    media_path = resolve_media_path(sys.argv)
    audio_path = get_temp_dir() / media_path.stem / "audio.wav"
    if not audio_path.exists():
        print(f"错误: 未找到音频 {audio_path}，请先运行 step1_extract_audio.py")
        sys.exit(1)

    work_output = get_output_dir() / media_path.stem
    work_output.mkdir(parents=True, exist_ok=True)
    srt_path = work_output / f"{media_path.stem}_src.srt"
    print(f"处理音频: {audio_path}")
    print("ASR 后端: Kotoba-Whisper v2.2")
    transcribe_kotoba(audio_path, srt_path)


if __name__ == "__main__":
    main()
