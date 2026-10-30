#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片格式转换（webp/png/jpg/bmp/tiff 互转），直接调用 ffmpeg。

用法:
  python convert_image.py raw/cover.webp png        # 同目录输出 raw/cover.png
  python convert_image.py raw/cover.webp jpg        # jpg 默认质量 -q:v 2（高）
  python convert_image.py in.webp out.png           # 显式指定输出路径
  python convert_image.py in.webp jpg -q 5          # jpg 质量 2(高)~31(低)，默认 2

注意: 带透明通道的图转 jpg/bmp 时透明部分会变黑，需要白底请先转 png 自行处理。
"""

import argparse
import subprocess
import sys
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


def main():
    ap = argparse.ArgumentParser(description="图片格式转换")
    ap.add_argument("src", help="源图片路径")
    ap.add_argument("dst", help="目标格式（png/jpg/...）或输出文件路径")
    ap.add_argument("-q", type=int, default=2, help="jpg 质量 2(高)~31(低)，默认 2；对其他格式无效")
    cfg = ap.parse_args()

    src = Path(cfg.src)
    if not src.exists():
        print(f"错误: 文件不存在 {src}")
        sys.exit(1)
    if src.suffix.lower() not in IMG_EXTS:
        print(f"错误: 不支持的源格式 {src.suffix}（支持: {sorted(IMG_EXTS)}）")
        sys.exit(1)

    dst_arg = cfg.dst.lower().lstrip(".")
    if "." not in cfg.dst and dst_arg in {e.lstrip(".") for e in IMG_EXTS}:
        out = src.with_suffix("." + ("jpg" if dst_arg == "jpeg" else dst_arg))
    else:
        out = Path(cfg.dst)
        if out.suffix.lower() not in IMG_EXTS:
            print(f"错误: 不支持的输出格式 {out.suffix}（支持: {sorted(IMG_EXTS)}）")
            sys.exit(1)
    if out.resolve() == src.resolve():
        print("错误: 输出路径与源文件相同")
        sys.exit(1)

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if out.suffix.lower() in {".jpg", ".jpeg"}:
        cmd += ["-q:v", str(cfg.q)]
    cmd.append(str(out))

    print(f">>> {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print(f"错误: ffmpeg 转换失败（源文件损坏或格式不受支持？）")
        sys.exit(1)
    print(f"[转换完成] -> {out}（{out.stat().st_size} 字节）")


if __name__ == "__main__":
    main()
