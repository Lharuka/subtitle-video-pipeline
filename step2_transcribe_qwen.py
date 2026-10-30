#!/usr/bin/env python3
"""
步骤2备选：使用本地 Qwen3-ASR + FSMN-VAD 转写字幕。

VAD 提供人声时间轴并合并碎片，Qwen 逐块识别；每块完成后更新 SRT。
需在独立 qwen3-asr 环境运行，并先执行 step1_extract_audio.py。

用法:
  conda activate qwen3-asr
  python step2_transcribe_qwen.py raw/sample.mp4

环境变量:
  QWEN_MODEL_DIR          # 默认 models/Qwen3-ASR-1.7B
  QWEN_VAD_DIR            # 默认 models/speech_fsmn_vad_zh-cn-16k-common-pytorch
  QWEN_DEVICE             # 默认 auto（cuda / cpu / auto）
  QWEN_LANGUAGE           # 默认 Japanese，可设 Chinese / English 等
  QWEN_CONTEXT            # 可选上下文或专名提示
  QWEN_VAD_MERGE_SECONDS  # VAD 合并及最大分块秒数，默认 15
"""

import os
import sys
import time
import wave
from pathlib import Path

from common import MODELS_DIR, get_output_dir, get_temp_dir, resolve_media_path


QWEN_MODEL_DIR = Path(os.getenv("QWEN_MODEL_DIR", str(MODELS_DIR / "Qwen3-ASR-1.7B")))
QWEN_VAD_DIR = Path(os.getenv(
    "QWEN_VAD_DIR", str(MODELS_DIR / "speech_fsmn_vad_zh-cn-16k-common-pytorch")
))
QWEN_DEVICE = os.getenv("QWEN_DEVICE", "auto").lower()
QWEN_LANGUAGE = os.getenv("QWEN_LANGUAGE", "Japanese")
QWEN_CONTEXT = os.getenv("QWEN_CONTEXT", "")
QWEN_VAD_MERGE_SECONDS = int(os.getenv("QWEN_VAD_MERGE_SECONDS", "15"))


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
        print("警告: SRT 正被其他程序占用，本次更新未写入；后续分块会继续重试", flush=True)
        return False


def get_vad_segments(result: list[dict]) -> list[list[int]]:
    if not result:
        return []
    return [
        [int(start), int(end)]
        for start, end in result[0].get("value", [])
        if int(end) > int(start)
    ]


def split_long_segments(segments: list[list[int]], max_ms: int) -> list[list[int]]:
    blocks = []
    for start, end in segments:
        block_start = start
        while end - block_start > max_ms:
            blocks.append([block_start, block_start + max_ms])
            block_start += max_ms
        if end > block_start:
            blocks.append([block_start, end])
    return blocks


def transcribe_qwen(audio_path: Path, srt_path: Path):
    try:
        import numpy as np
        import torch
        from funasr import AutoModel
        from funasr.utils.vad_utils import merge_vad
        from qwen_asr import Qwen3ASRModel
    except ImportError:
        print("错误: 缺少 qwen-asr、funasr、torch 或 numpy，请使用独立 qwen3-asr 环境")
        sys.exit(1)

    if QWEN_DEVICE not in {"auto", "cuda", "cpu"}:
        print(f"错误: QWEN_DEVICE 仅支持 auto/cuda/cpu，当前为 {QWEN_DEVICE}")
        sys.exit(1)
    if not 1 <= QWEN_VAD_MERGE_SECONDS <= 60:
        print("错误: QWEN_VAD_MERGE_SECONDS 必须在 1～60 之间")
        sys.exit(1)
    if QWEN_DEVICE == "cuda" and not torch.cuda.is_available():
        print("错误: 已指定 CUDA，但当前 PyTorch 无法使用 GPU")
        sys.exit(1)
    use_cuda = QWEN_DEVICE == "cuda" or (QWEN_DEVICE == "auto" and torch.cuda.is_available())
    device = "cuda:0" if use_cuda else "cpu"
    dtype = torch.bfloat16 if use_cuda else torch.float32
    for name, model_dir, file_name in (
        ("Qwen3-ASR", QWEN_MODEL_DIR, "config.json"),
        ("FSMN-VAD", QWEN_VAD_DIR, "model.pt"),
    ):
        if not (model_dir / file_name).is_file():
            print(f"错误: {name} 模型不完整，未找到 {model_dir / file_name}")
            sys.exit(1)

    print(f"ASR 模型: {QWEN_MODEL_DIR}")
    print(f"VAD 模型: {QWEN_VAD_DIR}")
    print(f"设备: {device}，精度: {'BF16' if use_cuda else 'FP32'}")
    print(f"语言: {QWEN_LANGUAGE}，VAD 分块: {QWEN_VAD_MERGE_SECONDS} 秒")
    vad_model = AutoModel(model=str(QWEN_VAD_DIR), device=device, disable_update=True)
    model = Qwen3ASRModel.from_pretrained(
        str(QWEN_MODEL_DIR),
        dtype=dtype,
        device_map=device,
        max_inference_batch_size=1,
        max_new_tokens=1024,
    )

    print("[VAD] 正在检测人声分段", flush=True)
    vad_result = vad_model.generate(input=str(audio_path))
    vad_segments = get_vad_segments(vad_result)
    max_ms = QWEN_VAD_MERGE_SECONDS * 1000
    blocks = split_long_segments(merge_vad(vad_segments, max_ms), max_ms)
    print(f"[VAD] 合并后共 {len(blocks)} 个识别块", flush=True)

    entries = []
    write_srt(entries, srt_path)
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            print("错误: 输入必须是 step1 生成的 16 kHz、单声道、16-bit PCM WAV")
            sys.exit(1)
        sample_rate = wav.getframerate()
        total_frames = wav.getnframes()

        for index, (start_ms, end_ms) in enumerate(blocks, 1):
            start_frame = min(total_frames, start_ms * sample_rate // 1000)
            end_frame = min(total_frames, end_ms * sample_rate // 1000)
            if end_frame <= start_frame:
                continue
            wav.setpos(start_frame)
            pcm = wav.readframes(end_frame - start_frame)
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            if len(samples) < sample_rate // 2:
                samples = np.pad(samples, (0, sample_rate // 2 - len(samples)))
            kwargs = dict(
                audio=(samples, sample_rate),
                language=QWEN_LANGUAGE,
                return_time_stamps=False,
            )
            if QWEN_CONTEXT:
                kwargs["context"] = QWEN_CONTEXT
            result = model.transcribe(**kwargs)[0]
            text = result.text.strip()
            if text:
                entries.append({
                    "start": start_ms / 1000,
                    "end": end_ms / 1000,
                    "text": text,
                })
                write_srt(entries, srt_path)
            print(
                f"[分块 {index}/{len(blocks)}] "
                f"{format_time(start_ms / 1000)} --> {format_time(end_ms / 1000)} {text}",
                flush=True,
            )

    if not write_srt(entries, srt_path):
        print("错误: SRT 仍被其他程序占用，请关闭占用程序后重试")
        sys.exit(1)
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
    print("ASR 后端: Qwen3-ASR + FSMN-VAD")
    transcribe_qwen(audio_path, srt_path)


if __name__ == "__main__":
    main()
