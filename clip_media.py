#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剪切媒体：把音频/视频指定 [start, end) 区间剪成新文件。

时间格式灵活（均可）：纯秒数 "90.5"、"1:30"、"01:30.500"、"00:01:30,500"。
省略 end 表示剪到文件末尾。

默认输出到产物根目录（`TOOLBOX_OUTPUT_DIR`，缺省工具箱 output/）：`<stem>_clip_<起始>_<结束><原扩展名>`；
视频重编码默认仅在 NVENC 可用时使用 GPU（crf 18，切口精确到帧），只有 QSV/AMF 时回退 libx264；
`--hw` 强制使用任意硬件编码器，`--cpu` 强制回退 libx264；
`--video-bitrate source` 按源视频流码率重编码，音频流直接复制；
音频重编码 AAC（默认 auto=对齐源码率并上取整到 48/64/.../192k 档位，可用 -ab 手动指定）。
加 `--copy` 则整段流复制（快且无损，但切口可能对齐关键帧/包时间轴，
**要与字幕对轨时不要用**——见 AGENTS.md 已知坑）。

用法:
  python clip_media.py raw/xxx.aac 0:59 1:06
  python clip_media.py raw/xxx.mp4 90.5 120 --copy
  python clip_media.py raw/xxx.mp4 1:30          # 剪到末尾
  python clip_media.py raw/xxx.aac 0:59 1:06 output/clip.aac   # 指定输出路径
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from common import (resolve_media_path, is_video, get_media_duration, get_output_dir,
                    build_video_codec_args, get_video_bitrate)

TS_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")
PLAIN_RE = re.compile(r"(\d+(?:\.\d+)?)$")


def parse_time(s):
    """解析时间为毫秒。支持 秒数 / MM:SS[.ms] / HH:MM:SS[,ms]。"""
    s = s.strip()
    m = PLAIN_RE.fullmatch(s)
    if m:
        return int(float(m.group(1)) * 1000)
    m = TS_RE.fullmatch(s)
    if m:
        h = int(m.group(1) or 0)
        mi, sec = int(m.group(2)), int(m.group(3))
        ms = int((m.group(4) or "0").ljust(3, "0"))
        return ((h * 60 + mi) * 60 + sec) * 1000 + ms
    print(f"错误: 无法解析时间 {s!r}（支持: 90.5 / 1:30 / 01:30.5 / 00:01:30,500）")
    sys.exit(1)


def decode_duration_ms(path):
    """解码实测媒体时长（毫秒）。

    ADTS/raw aac 的容器时长是码率估算值，可能比实际可解码长度短/长几十秒
    （本项目的电台 aac 就偏短 35s），ffprobe 不可信，必须解码到底。
    """
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-map", "0:a", "-f", "null", "-"],
                       capture_output=True, text=True)
    times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not times:
        print(f"错误: 无法解码测量产物时长 {path}")
        sys.exit(1)
    h, mi, sec = times[-1]
    return int((int(h) * 3600 + int(mi) * 60 + float(sec)) * 1000)


def fmt_ms(ms):
    h, rem = divmod(ms, 3600000)
    mi, rem = divmod(rem, 60000)
    sec, m = divmod(rem, 1000)
    return f"{h:02d}{mi:02d}{sec:02d}{m:03d}"


BITRATE_LADDER = [48, 64, 80, 96, 112, 128, 160, 192]  # 对齐源码率的上取整档位


def align_audio_bitrate(media):
    """取源音频码率（kbps），向上对齐到 BITRATE_LADDER 档位；探测失败回退 128k。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=bit_rate", "-of", "default=nw=1:nk=1", str(media)],
            capture_output=True, text=True, check=True)
        kbps = int(r.stdout.strip()) / 1000
        for step in BITRATE_LADDER:
            if kbps <= step:
                return f"{step}k"
        return "192k"
    except (subprocess.CalledProcessError, ValueError):
        return "128k"


def main():
    ap = argparse.ArgumentParser(description="剪切音频/视频的指定区间")
    ap.add_argument("media", nargs="?", help="媒体路径（默认取 raw/ 第一个媒体）")
    ap.add_argument("start", help="起始时间（如 0:59 / 90.5 / 00:01:30,500）")
    ap.add_argument("end", nargs="?", help="结束时间（省略则剪到末尾）")
    ap.add_argument("out", nargs="?", help="输出路径（默认在源文件旁边，带 _clip_ 后缀）")
    ap.add_argument("--copy", action="store_true", help="整段流复制（快且无损，但切口可能对齐关键帧/包时间轴，对轨不要用）")
    ap.add_argument("--cpu", action="store_true", help="强制使用 libx264 CPU 编码")
    ap.add_argument("--hw", action="store_true", help="强制使用任意可用 GPU 硬件编码器（默认仅 NVENC 自动启用）")
    ap.add_argument("--video-bitrate", choices=["source"], help="视频码率：source=匹配源视频流码率（默认使用 CRF 18）")
    ap.add_argument("-ab", "--audio-bitrate", default="auto",
                    help="音频重编码码率（默认 auto=对齐源码率并上取整到 48/64/.../192k 档位）")
    cfg = ap.parse_args()

    media = resolve_media_path([sys.argv[0], cfg.media] if cfg.media else [sys.argv[0]])
    if cfg.video_bitrate and cfg.copy:
        print("错误: --copy 不重编码，不能与 --video-bitrate 同用")
        sys.exit(1)
    if cfg.video_bitrate and not is_video(media):
        print("错误: --video-bitrate 仅适用于视频输入")
        sys.exit(1)
    start_ms = parse_time(cfg.start)

    duration_ms = int(get_media_duration(media) * 1000)
    if cfg.end:
        end_ms = parse_time(cfg.end)
        if end_ms > duration_ms:
            print(f"错误: end 超出媒体时长（{cfg.end} > {duration_ms/1000:.3f}s）")
            sys.exit(1)
    else:
        end_ms = duration_ms
    if start_ms >= end_ms:
        print(f"错误: start ({cfg.start}) 必须小于 end ({cfg.end or '末尾'})")
        sys.exit(1)

    video_bitrate = None
    if cfg.video_bitrate == "source":
        try:
            video_bitrate = get_video_bitrate(media)
        except ValueError as exc:
            print(f"错误: {exc}")
            sys.exit(1)
        print(f"匹配源视频码率: {int(video_bitrate) / 1000:.0f} kb/s")

    if cfg.out:
        out_path = Path(cfg.out)
    else:
        tag = f"{fmt_ms(start_ms)}_{fmt_ms(end_ms)}"
        out_path = get_output_dir() / f"{media.stem}_clip_{tag}{media.suffix}"
    if out_path.resolve() == media.resolve():
        print("错误: 输出路径与源文件相同")
        sys.exit(1)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-ss", f"{start_ms / 1000:.3f}", "-i", str(media),
           "-t", f"{(end_ms - start_ms) / 1000:.3f}"]
    if cfg.copy:
        cmd += ["-c", "copy"]
    elif is_video(media):
        codec_args = build_video_codec_args(crf=18, preset="fast", force_cpu=cfg.cpu, force_hw=cfg.hw,
                                            video_bitrate=video_bitrate)
        cmd += codec_args + ["-c:a", "copy"]
    else:
        ab = cfg.audio_bitrate if cfg.audio_bitrate != "auto" else align_audio_bitrate(media)
        cmd += ["-c:a", "aac", "-b:a", ab]
    cmd.append(str(out_path))

    print(f">>> {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("错误: ffmpeg 剪切失败（输入损坏或磁盘不足？）")
        sys.exit(1)

    actual_ms = decode_duration_ms(out_path)
    expected_ms = end_ms - start_ms
    if not cfg.copy and abs(actual_ms - expected_ms) > 1000:
        print(f"错误: 产物时长 {actual_ms/1000:.3f}s 与请求 {expected_ms/1000:.3f}s 偏差超过 1s，"
              f"源文件时间戳可能不可靠（见 AGENTS.md 已知坑），请检查后再用")
        sys.exit(1)
    print(f"[剪切完成] -> {out_path}")
    print(f"区间: {start_ms/1000:.3f}s ~ {end_ms/1000:.3f}s（{expected_ms/1000:.3f}s）"
          f"  实际产物时长: {actual_ms/1000:.3f}s")


if __name__ == "__main__":
    main()
