#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并双语字幕：把 _src.srt（原文）和 _zh.srt（译文）按条目对齐合并为双语 SRT。

合并前先做硬校验（条目数一致、每条时间轴毫秒级一致、译文无空条目），
不过则非零退出。产物供用户人工审核；审核改完后用 renumber_srt.py 重排编号，
需要分语言样式时再交给 srt_to_ass.py 转双样式 ASS。

注意：字数阈值（合并/拆分/单条上限）按单语调教，推荐在单语阶段定稿后再合并；
合并产物如需再自动重组，必须用 reorganize_srt.py --bilingual（普通模式会打散两行配对）。

用法:
  python merge_bilingual_srt.py <_zh.srt> [<_src.srt>] [-o 输出]
  - src 缺省取同目录同名 _src.srt
  - 输出缺省与 zh 同目录的 <stem>_bilingual.srt
  - 默认译文在上、原文在下（与烧录时"中文在上、外文在下"一致）；--src-first 交换
"""

import argparse
import sys
from pathlib import Path

from reorganize_srt import ms_to_ts, parse


def align_check(zh_path, src_path):
    zh = parse(zh_path)
    src = parse(src_path)
    if len(zh) != len(src):
        print(f"错误: 条目数不一致 zh={len(zh)} src={len(src)}")
        sys.exit(1)
    for i, (z, s) in enumerate(zip(zh, src)):
        if z["start"] != s["start"] or z["end"] != s["end"]:
            print(f"错误: 第 {i+1} 条时间轴不一致:\n"
                  f"  zh : {ms_to_ts(z['start'])} --> {ms_to_ts(z['end'])}\n"
                  f"  src: {ms_to_ts(s['start'])} --> {ms_to_ts(s['end'])}")
            sys.exit(1)
    empties = [i + 1 for i, e in enumerate(zh) if not e["text"].strip()]
    if empties:
        print(f"错误: {len(empties)} 条译文为空: 第 {empties[:10]} 条"
              f"{'...' if len(empties) > 10 else ''}")
        sys.exit(1)
    print(f"[对齐校验通过] {len(zh)} 条，时间轴逐条一致")
    return zh, src


def main():
    ap = argparse.ArgumentParser(description="合并双语字幕（原文+译文 -> 双语 SRT，供审核）")
    ap.add_argument("zh", help="译文字幕 _zh.srt")
    ap.add_argument("src", nargs="?", help="原文字幕 _src.srt（缺省取同目录同名 _src.srt）")
    ap.add_argument("-o", "--out", help="输出路径（缺省与 zh 同目录 <stem>_bilingual.srt）")
    ap.add_argument("--src-first", action="store_true", help="原文在上、译文在下（默认译文在上）")
    args = ap.parse_args()

    zh_path = Path(args.zh)
    if not zh_path.exists():
        print(f"错误: 文件不存在 {zh_path}")
        sys.exit(1)
    if args.src:
        src_path = Path(args.src)
    else:
        src_path = zh_path.with_name(zh_path.name.replace("_zh.srt", "_src.srt"))
    if not src_path.exists():
        print(f"错误: 未找到原文字幕 {src_path}（可用第二个参数显式指定）")
        sys.exit(1)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = zh_path.with_name(zh_path.name.replace("_zh.srt", "_bilingual.srt"))
        if out_path == zh_path:
            out_path = zh_path.with_name(zh_path.stem + "_bilingual.srt")

    zh, src = align_check(zh_path, src_path)

    lines = []
    for i, (z, s) in enumerate(zip(zh, src), 1):
        first, second = (s, z) if args.src_first else (z, s)
        lines.append(str(i))
        lines.append(f"{ms_to_ts(z['start'])} --> {ms_to_ts(z['end'])}")
        lines.append(first["text"])
        lines.append(second["text"])
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"[合并完成] -> {out_path}（{len(zh)} 条，{'原文在上' if args.src_first else '译文在上'}）")
    print("下一步: 人工审核 -> renumber_srt.py 重排编号 -> "
          "需要分语言样式时 srt_to_ass.py 转 ASS -> 出片")


if __name__ == "__main__":
    main()
