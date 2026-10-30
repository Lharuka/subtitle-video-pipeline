#!/usr/bin/env python3
"""
步骤1：提取/转换音频为 16kHz 单声道 wav（视频、音频文件均可）

用法:
  python step1_extract_audio.py raw/sample.mp4
  python step1_extract_audio.py raw/xxx.aac
  python step1_extract_audio.py        # 自动处理 raw/ 下第一个媒体文件
"""

import sys
import subprocess
from pathlib import Path

from common import resolve_media_path, get_temp_dir




def run(cmd, **kwargs):
    print(f">>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def extract_audio(media_path: Path, audio_path: Path):
    run([
        "ffmpeg", "-y", "-i", str(media_path),
        "-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
        str(audio_path)
    ], capture_output=True)
    print(f"[音频提取完成] -> {audio_path}")


def main():
    media_path = resolve_media_path(sys.argv)

    work_temp = get_temp_dir() / media_path.stem
    work_temp.mkdir(parents=True, exist_ok=True)
    audio_path = work_temp / "audio.wav"

    print(f"处理: {media_path}")
    extract_audio(media_path, audio_path)


if __name__ == "__main__":
    main()
