#!/usr/bin/env python3
"""
步骤4：将字幕硬编码到视频画面（ffmpeg）
音频文件没有画面，无需烧录，会自动跳过。

用法:
  python step4_burn_subtitles.py raw/sample.mp4
  python step4_burn_subtitles.py raw/sample.mp4 --srt output/sample/sample_bilingual.ass
  python step4_burn_subtitles.py raw/xxx.aac   # 自动提示跳过
  python step4_burn_subtitles.py               # 自动处理 raw/ 下第一个媒体文件

字幕默认取 output/<stem>/<stem>_zh.srt；--srt 可指定任意字幕文件（srt/ass 均可，
libass 渲染）。--srt 指定时产物名跟随字幕后缀（如 <stem>_bilingual.mp4）。
默认仅在检测到 NVIDIA NVENC 时使用 GPU；只有 QSV/AMF 时默认回退 libx264。
--hw 强制使用任意可用硬件编码器，--cpu 强制回退到 libx264。
--video-bitrate source 按源视频流码率烧录，音频流直接复制。
"""

import sys
import subprocess
from pathlib import Path

from common import (resolve_media_path, is_audio, escape_subtitles_path, get_output_dir,
                    build_video_codec_args, get_video_bitrate)


def run(cmd, **kwargs):
    print(f">>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def burn_subtitles(video_path: Path, srt_path: Path, out_path: Path, force_cpu: bool = False,
                   force_hw: bool = False, video_bitrate: str | None = None):
    srt_str = escape_subtitles_path(srt_path)
    vf = f"subtitles='{srt_str}'"
    codec_args = build_video_codec_args(crf=18, preset="fast", force_cpu=force_cpu, force_hw=force_hw,
                                        video_bitrate=video_bitrate)
    run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", vf,
        "-c:a", "copy",
        *codec_args,
        str(out_path)
    ], capture_output=True)
    print(f"[烧录完成] -> {out_path}")


def main():
    argv = list(sys.argv[1:])
    srt_arg = None
    force_cpu = False
    force_hw = False
    match_source_bitrate = False
    if "--cpu" in argv:
        argv.remove("--cpu")
        force_cpu = True
    if "--hw" in argv:
        argv.remove("--hw")
        force_hw = True
    if "--video-bitrate" in argv:
        i = argv.index("--video-bitrate")
        if i + 1 >= len(argv) or argv[i + 1] != "source":
            print("错误: --video-bitrate 目前仅支持 source（匹配源视频流码率）")
            sys.exit(1)
        match_source_bitrate = True
        del argv[i:i + 2]
    if "--srt" in argv:
        i = argv.index("--srt")
        if i + 1 >= len(argv):
            print("错误: --srt 需要跟一个字幕文件路径")
            sys.exit(1)
        srt_arg = argv[i + 1]
        del argv[i:i + 2]
    media_path = resolve_media_path([sys.argv[0]] + argv)

    if is_audio(media_path):
        print(f"输入为音频文件: {media_path}")
        print("音频无画面可烧录，跳过步骤4（字幕见 output/ 下的 SRT 文件）")
        return

    video_bitrate = None
    if match_source_bitrate:
        try:
            video_bitrate = get_video_bitrate(media_path)
        except ValueError as exc:
            print(f"错误: {exc}")
            sys.exit(1)
        print(f"匹配源视频码率: {int(video_bitrate) / 1000:.0f} kb/s")

    work_output = get_output_dir() / media_path.stem
    work_output.mkdir(parents=True, exist_ok=True)
    if srt_arg:
        srt_path = Path(srt_arg)
        if not srt_path.exists():
            print(f"错误: 字幕文件不存在 {srt_path}")
            sys.exit(1)
    else:
        srt_path = work_output / f"{media_path.stem}_zh.srt"
        if not srt_path.exists():
            print(f"错误: 未找到字幕文件 {srt_path}，请先完成翻译生成 _zh.srt")
            sys.exit(1)

    if srt_path.stem.startswith(media_path.stem) and srt_path.stem != media_path.stem:
        label = srt_path.stem[len(media_path.stem):]
    else:
        label = f"_{srt_path.stem}" if srt_arg else "_zh"
    video_out = work_output / f"{media_path.stem}{label}.mp4"

    print(f"烧录字幕: {srt_path} -> {video_out}")
    burn_subtitles(media_path, srt_path, video_out, force_cpu=force_cpu, force_hw=force_hw,
                   video_bitrate=video_bitrate)


if __name__ == "__main__":
    main()
