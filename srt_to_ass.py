#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双语 SRT 转双样式 ASS：在双语 SRT 审核、renumber 重排完成后执行。

输入约定（merge_bilingual_srt.py 的产物）：每个条目两行文本，
默认第 1 行 = 译文（样式 ZH），第 2 行 = 原文（样式 SRC）；--src-first 交换。
某一侧不需要时用单个空格 " " 占位（不要整行删除，否则该行会被按 ZH 样式渲染并警告）；
空格占位行样式归属正确、烧录时不显示任何内容。
单行条目按 ZH 处理并警告；超过 2 行的条目，第 1 行按译文、其余行并入原文。

输出 ASS：SRC/ZH 两个命名样式，烧录时两种语言都在画面底部，
中文在上、外文在下（ZH MarginV 80 靠上，SRC MarginV 20 贴近底边；
80 是 64/48 字号下不触发 libass 行盒重叠的最小边距，实测 78 撞线 70 必重叠），
字体/字号/颜色可调。产物传给 audio_to_video.py --srt / step4_burn_subtitles.py --srt 烧录。

用法:
  python srt_to_ass.py <双语.srt> [-o 输出.ass] [--src-first]
                       [--src-font F] [--zh-font F] [--src-size N] [--zh-size N]
                       [--src-color &HAABBGGRR] [--zh-color &HAABBGGRR]
                       [--src-bold 0|1] [--zh-bold 0|1]
"""

import argparse
import sys
from pathlib import Path

from renumber_srt import parse_lenient


def ms_to_ass_ts(ms):
    # ASS 时间格式 H:MM:SS.cc（厘秒，截断不四舍五入，避免进位后与 SRT 对不上）
    cs = ms // 10
    h, rem = divmod(cs, 360000)
    mi, rem = divmod(rem, 6000)
    sec, c = divmod(rem, 100)
    return f"{h}:{mi:02d}:{sec:02d}.{c:02d}"


def ass_style(name, font, size, color, margin_v, bold):
    # Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,
    # Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,
    # Alignment,MarginL,MarginR,MarginV,Encoding
    return (f"Style: {name},{font},{size},{color},&H000000FF,&H00000000,&H64000000,"
            f"{bold},0,0,0,100,100,0,0,1,2,1,2,20,20,{margin_v},1")


def main():
    ap = argparse.ArgumentParser(description="双语 SRT 转双样式 ASS（审核+renumber 后执行）")
    ap.add_argument("srt", help="双语 SRT（每个条目两行：默认上原文下译文）")
    ap.add_argument("-o", "--out", help="输出路径（缺省同名 .ass）")
    ap.add_argument("--src-first", action="store_true",
                    help="条目第 1 行是原文、第 2 行是译文（与合并时的 --src-first 对应）")
    ap.add_argument("--src-font", default="Yu Gothic", help="原文样式字体（默认 Yu Gothic）")
    ap.add_argument("--zh-font", default="Microsoft YaHei", help="译文样式字体（默认 Microsoft YaHei）")
    ap.add_argument("--src-size", type=int, default=48, help="原文样式字号（默认 48）")
    ap.add_argument("--zh-size", type=int, default=64, help="译文样式字号（默认 64）")
    ap.add_argument("--src-color", default="&H00FFFFFF", help="原文颜色 &HAABBGGRR（默认白）")
    ap.add_argument("--zh-color", default="&H00FFFFFF", help="译文颜色 &HAABBGGRR（默认白）")
    ap.add_argument("--src-bold", type=int, choices=[0, 1], default=1, help="原文加粗（默认 1）")
    ap.add_argument("--zh-bold", type=int, choices=[0, 1], default=1, help="译文加粗（默认 1）")
    args = ap.parse_args()

    srt_path = Path(args.srt)
    if not srt_path.exists():
        print(f"错误: 文件不存在 {srt_path}")
        sys.exit(1)
    out_path = Path(args.out) if args.out else srt_path.with_suffix(".ass")

    entries = parse_lenient(srt_path)
    first_style, second_style = ("SRC", "ZH") if args.src_first else ("ZH", "SRC")

    events = []
    warnings = 0
    for i, e in enumerate(entries, 1):
        lines = e["text"].split("\n")
        if len(lines) == 1:
            print(f"警告: 第 {i} 条只有一行，按 ZH（译文）处理")
            warnings += 1
            parts = [("ZH", lines[0])]
        else:
            parts = [(first_style, lines[0]), (second_style, "\\N".join(lines[1:]))]
            if len(lines) > 2:
                print(f"警告: 第 {i} 条有 {len(lines)} 行，第 1 行按 {first_style}、"
                      f"其余 {len(lines)-1} 行并入 {second_style}")
                warnings += 1
        start, end = ms_to_ass_ts(e["start"]), ms_to_ass_ts(e["end"])
        for style, text in parts:
            events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{text}")

    header = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
        "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
        "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        ass_style("SRC", args.src_font, args.src_size, args.src_color, 20, -1 if args.src_bold else 0),
        ass_style("ZH", args.zh_font, args.zh_size, args.zh_color, 80, -1 if args.zh_bold else 0),
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ])
    out_path.write_text(header + "\n" + "\n".join(events) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"[转换完成] -> {out_path}（{len(entries)} 条 x2 事件，样式 SRC/ZH，"
          f"{'原文在上' if args.src_first else '译文在上'}，底部布局：中文在上、外文在下，"
          f"PlayRes 1920x1080）")
    if warnings:
        print(f"注意: {warnings} 条行数异常警告，请确认上面的输出")
    print("下一步: audio_to_video.py --srt 或 step4_burn_subtitles.py --srt 烧录")


if __name__ == "__main__":
    main()
