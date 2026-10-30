#!/usr/bin/env python3
"""
工具：音频 + 封面图片 + 字幕 -> MP4 视频
画面为用户指定封面图（适配 1920x1080，黑边填充），字幕硬编码，时长跟随音频。

用法:
  python audio_to_video.py raw/xxx.aac --cover cover.jpg
  python audio_to_video.py raw/xxx.aac --cover cover.jpg --srt output/xxx/xxx_zh.srt
  python audio_to_video.py raw/xxx.aac --cover cover.jpg --no-srt
  python audio_to_video.py raw/xxx.aac --cover cover.jpg --size 1080x1920 --fps 24
  python audio_to_video.py --cover cover.jpg        # raw/ 下第一个音频

字幕默认取 output/<stem>/<stem>_zh.srt，无则取 _src.srt。
输出: output/<stem>/<stem>_video.mp4

音质与体积:
  - aac/m4a 音轨直接复制（无损）；wav/flac 等转 AAC 192k（高质量）
  - 默认仅在检测到 NVIDIA NVENC 时使用 GPU；只有 QSV/AMF 时默认回退 libx264
  - --hw 可强制使用任意可用硬件编码器，--cpu 可强制回退 libx264
  - 画面为静态封面，默认 -crf 26 -g 600，
    体积远小于常规转码；不满意可用 --crf/--preset 调整（crf 越大体积越小）
"""

import argparse
import subprocess
from pathlib import Path

from common import (
    AUDIO_EXTS,
    RAW_DIR,
    build_video_codec_args,
    escape_subtitles_path,
    get_media_duration,
    get_output_dir,
    is_audio,
)
from clip_media import decode_duration_ms

COPY_AUDIO_EXTS = {".aac", ".m4a"}  # 已兼容 MP4 封装，直接复用音轨
AUDIO_BITRATE = "192k"


def resolve_audio_path(arg: str | None) -> Path:
    if arg:
        audio_path = Path(arg)
        if not audio_path.exists():
            raise SystemExit(f"错误: 文件不存在 {audio_path}")
        if not is_audio(audio_path):
            raise SystemExit(f"错误: 不是音频文件 {audio_path}（支持: {sorted(AUDIO_EXTS)}）")
        return audio_path
    files = sorted(f for ext in AUDIO_EXTS for f in RAW_DIR.glob(f"*{ext}"))
    if not files:
        raise SystemExit(f"错误: {RAW_DIR}/ 下没有音频文件，请显式指定路径")
    return files[0]


def resolve_srt(stem: str, srt_arg: str | None, no_srt: bool) -> Path | None:
    if no_srt:
        return None
    if srt_arg:
        srt_path = Path(srt_arg)
        if not srt_path.exists():
            raise SystemExit(f"错误: 字幕文件不存在 {srt_path}")
        return srt_path
    work_output = get_output_dir() / stem
    for name in (f"{stem}_zh.srt", f"{stem}_src.srt"):
        srt_path = work_output / name
        if srt_path.exists():
            return srt_path
    raise SystemExit(f"错误: 未找到字幕（{work_output}/{stem}_zh.srt 或 _src.srt），请用 --srt 指定或 --no-srt")


def build_vf(width: int, height: int, fps: int, srt_path: Path | None) -> str:
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        f"fps={fps}",
    ]
    if srt_path:
        filters.append(f"subtitles='{escape_subtitles_path(srt_path)}'")
    return ",".join(filters)


def parse_size(size: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in size.lower().split("x"))
    except ValueError:
        raise SystemExit(f"错误: --size 格式应为 WxH，如 1920x1080，收到: {size}")
    if w <= 0 or h <= 0 or w % 2 or h % 2:
        raise SystemExit(f"错误: --size 宽高必须为正偶数，收到: {size}")
    return w, h


def main():
    parser = argparse.ArgumentParser(description="音频 + 封面图片 + 字幕 -> MP4")
    parser.add_argument("audio", nargs="?", help="音频文件路径（默认 raw/ 下第一个音频）")
    parser.add_argument("--cover", required=True, help="封面图片路径")
    parser.add_argument("--srt", help="字幕文件路径（默认优先 _zh.srt，其次 _src.srt）")
    parser.add_argument("--no-srt", action="store_true", help="不烧录字幕")
    parser.add_argument("--size", default="1920x1080", help="输出分辨率 WxH（默认 1920x1080，封面等比缩放黑边填充）")
    parser.add_argument("--fps", type=int, default=30, help="输出帧率（默认 30）")
    parser.add_argument("--crf", type=int, default=26, help="视频 CRF（默认 26；静态封面专用取值，越大体积越小）")
    parser.add_argument("--preset", default="slow", help="x264 预设（默认 slow，压缩率更高；可换 veryslow/medium/fast）")
    parser.add_argument("--cpu", action="store_true", help="强制使用 libx264 CPU 编码")
    parser.add_argument("--hw", action="store_true", help="强制使用任意可用 GPU 硬件编码器（默认仅 NVENC 自动启用）")
    args = parser.parse_args()

    width, height = parse_size(args.size)

    audio_path = resolve_audio_path(args.audio)
    cover_path = Path(args.cover)
    if not cover_path.exists():
        raise SystemExit(f"错误: 封面图片不存在 {cover_path}")
    srt_path = resolve_srt(audio_path.stem, args.srt, args.no_srt)

    work_output = get_output_dir() / audio_path.stem
    work_output.mkdir(parents=True, exist_ok=True)
    video_out = work_output / f"{audio_path.stem}_video.mp4"

    if audio_path.suffix.lower() == ".aac":
        # ADTS/raw aac 容器时长是码率估算值，可能比实际可解码长度差几十秒
        # （见 AGENTS.md 已知坑），必须解码实测
        duration = decode_duration_ms(audio_path) / 1000
    else:
        duration = get_media_duration(audio_path)
    if audio_path.suffix.lower() in COPY_AUDIO_EXTS:
        audio_codec = ["-c:a", "copy"]
    else:
        audio_codec = ["-c:a", "aac", "-b:a", AUDIO_BITRATE]

    codec_args = build_video_codec_args(crf=args.crf, preset=args.preset, force_cpu=args.cpu, force_hw=args.hw)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(cover_path),
        "-i", str(audio_path),
        "-vf", build_vf(width, height, args.fps, srt_path),
        "-t", f"{duration:.3f}",
        *codec_args,
        "-g", "600",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        *audio_codec,
        str(video_out),
    ]
    print(f"音频: {audio_path}")
    print(f"封面: {cover_path}")
    print(f"字幕: {srt_path if srt_path else '（无）'}")
    print(f">>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[生成完成] -> {video_out}")


if __name__ == "__main__":
    main()
