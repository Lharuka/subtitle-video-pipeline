#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 重新编号：用户直接手改 SRT（增删条目、合并/拆分、改文本/时间轴），
改完后用这个脚本把序号重排为 1..N 并规范化为标准格式（LF 换行）。

只动序号和格式，条目内容、顺序、时间轴原样保留。
校验（有问题打印警告但不中断，写回前请自行确认）：
- 时间轴必须是 HH:MM:SS,mmm 且 start<end（格式错误直接报错退出）
- 相邻条目时间重叠 / 乱序 → 警告

用法:
  python renumber_srt.py output/xxx/xxx_zh.srt
  python renumber_srt.py            # 自动取 raw/ 第一个媒体对应的 _zh.srt
"""

import sys

from reorganize_srt import ms_to_ts, resolve_srt_path, ts_to_ms


def parse_lenient(path):
    """解析人工编辑的 SRT，容忍条目间的多余空行并保留单空格占位文本。"""
    raw = open(path, encoding="utf-8").read().strip("\n").split("\n")
    entries = []
    i = 0
    while i < len(raw):
        while i < len(raw) and raw[i].rstrip("\r") == "":
            i += 1
        if i >= len(raw):
            break
        idx = raw[i].strip()
        if not idx.isdigit():
            print(f"错误: 行 {i+1} 期望序号，得到 {raw[i]!r}（不是标准 SRT？）")
            sys.exit(1)
        try:
            start_s, end_s = [x.strip() for x in raw[i + 1].split("-->")]
        except (IndexError, ValueError):
            print(f"错误: 行 {i+2} 时间轴格式不正确")
            sys.exit(1)
        text_lines = []
        i += 2
        while i < len(raw) and raw[i].rstrip("\r") != "":
            text_lines.append(raw[i].rstrip("\r"))
            i += 1
        i += 1
        entries.append({
            "start": ts_to_ms(start_s),
            "end": ts_to_ms(end_s),
            "text": "\n".join(text_lines),
        })
    return entries


def main():
    arg = sys.argv[1] if len(sys.argv) >= 2 else None
    srt_path = resolve_srt_path(arg)

    entries = parse_lenient(srt_path)
    n0 = len(entries)

    warnings = 0
    for i, e in enumerate(entries):
        if e["end"] <= e["start"]:
            print(f"错误: 第 {i+1} 条 start>=end: {ms_to_ts(e['start'])} --> {ms_to_ts(e['end'])}")
            sys.exit(1)
        if i + 1 < len(entries) and entries[i + 1]["start"] < e["end"]:
            print(f"警告: 第 {i+1}/{i+2} 条时间重叠: "
                  f"{ms_to_ts(e['end'])} > {ms_to_ts(entries[i+1]['start'])}")
            warnings += 1
        if i + 1 < len(entries) and entries[i + 1]["start"] < e["start"]:
            print(f"警告: 第 {i+2} 条 start 早于第 {i+1} 条（乱序，编号按现有顺序）")
            warnings += 1

    out_lines = []
    for i, e in enumerate(entries, 1):
        out_lines.append(str(i))
        out_lines.append(f"{ms_to_ts(e['start'])} --> {ms_to_ts(e['end'])}")
        out_lines.append(e["text"])
        out_lines.append("")
    with open(srt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines))

    print(f"[重编号完成] -> {srt_path}（{n0} 条，序号 1..{n0}）")
    if warnings:
        print(f"注意: 有 {warnings} 条时间轴警告，请确认上面的输出")


if __name__ == "__main__":
    main()
