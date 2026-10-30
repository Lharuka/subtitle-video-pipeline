#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 硬性核对：翻译/微调后的校验脚本，替代 sub agent 自述"校验通过"。

对比模式（翻译核对，任一不符即非零退出）：
  python verify_srt.py <_zh.srt> [<_src.srt>]
  - 省略 src 时自动取同目录同名 _src.srt
  - 条目数一致；每条序号行、时间轴行逐字符一致；无空译文条目
单文件体检：
  python verify_srt.py <任意.srt> --single
  - 序号 1..N 连续、start<end（违反即失败）
  - 时间重叠/乱序、时长 <0.8s → 警告不中断
两种模式都会做编码检查（UTF-8 无 BOM、LF 换行），并报告时长最长的 5 条
（reorganize 后用来确认超长条目是 jingle 过门段而非合并错误）。
"""

import re
import sys
from pathlib import Path

from reorganize_srt import ms_to_ts, parse

IDX_RE = re.compile(r"^\s*\d+\s*$")
TS_LINE_RE = re.compile(r"^\s*\d+:\d+:\d+,\d+\s*-->\s*\d+:\d+:\d+,\d+")


def raw_skeleton(path):
    """抽取全部序号行和时间轴行（逐字符保留），用于与原文严格比对。"""
    idx_lines, ts_lines = [], []
    for line in open(path, encoding="utf-8").read().split("\n"):
        if TS_LINE_RE.match(line):
            ts_lines.append(line.strip())
        elif IDX_RE.match(line):
            idx_lines.append(line.strip())
    return idx_lines, ts_lines


def check_encoding(path):
    data = open(path, "rb").read()
    ok = True
    if data.startswith(b"\xef\xbb\xbf"):
        print(f"错误: {path.name} 带 BOM，应为 UTF-8 无 BOM")
        ok = False
    if b"\r\n" in data or b"\r" in data:
        print(f"错误: {path.name} 含 CR/CRLF 换行，应为 LF")
        ok = False
    return ok


def report_longest(path):
    entries = parse(path)
    top = sorted(entries, key=lambda e: e["end"] - e["start"], reverse=True)[:5]
    print("时长最长的 5 条:")
    for e in top:
        dur = (e["end"] - e["start"]) / 1000
        text = e["text"].replace("\n", " ")[:20]
        print(f"  {dur:6.1f}s  {ms_to_ts(e['start'])}  {text}")


def compare_mode(zh_path, src_path):
    ok = check_encoding(zh_path) and check_encoding(src_path)

    zh_idx, zh_ts = raw_skeleton(zh_path)
    src_idx, src_ts = raw_skeleton(src_path)

    if len(zh_idx) != len(src_idx):
        print(f"错误: 条目数不一致 zh={len(zh_idx)} src={len(src_idx)}")
        ok = False
    else:
        n = len(zh_idx)
        for i in range(n):
            if zh_idx[i] != src_idx[i]:
                print(f"错误: 第 {i+1} 条序号行不一致: zh={zh_idx[i]!r} src={src_idx[i]!r}")
                ok = False
                break
            if zh_ts[i] != src_ts[i]:
                print(f"错误: 第 {i+1} 条时间轴不一致:\n  zh : {zh_ts[i]}\n  src: {src_ts[i]}")
                ok = False
                break
        else:
            print(f"[比对通过] 条目数 {n}，序号行/时间轴行逐字符一致")

    entries = parse(zh_path)
    empties = [i + 1 for i, e in enumerate(entries) if not e["text"].strip()]
    if empties:
        print(f"错误: {len(empties)} 条译文为空: 第 {empties[:10]} 条{'...' if len(empties) > 10 else ''}")
        ok = False

    report_longest(zh_path)
    if not ok:
        sys.exit(1)
    print("[核对通过]")


def single_mode(path):
    ok = check_encoding(path)
    entries = parse(path)
    warnings = 0
    for i, e in enumerate(entries):
        if e["end"] <= e["start"]:
            print(f"错误: 第 {i+1} 条 start>=end: {ms_to_ts(e['start'])} --> {ms_to_ts(e['end'])}")
            ok = False
        if i + 1 < len(entries):
            if entries[i + 1]["start"] < e["end"]:
                print(f"警告: 第 {i+1}/{i+2} 条时间重叠")
                warnings += 1
            if entries[i + 1]["start"] < e["start"]:
                print(f"警告: 第 {i+2} 条 start 早于第 {i+1} 条（乱序）")
                warnings += 1
        if 0 < e["end"] - e["start"] < 800:
            print(f"警告: 第 {i+1} 条时长仅 {(e['end'] - e['start'])}ms")
            warnings += 1
    print(f"共 {len(entries)} 条，序号连续 1..{len(entries)}（parse 已保证格式合法）")
    report_longest(path)
    if warnings:
        print(f"注意: {warnings} 条警告")
    if not ok:
        sys.exit(1)
    print("[核对通过]")


def main():
    args = [a for a in sys.argv[1:] if a != "--single"]
    single = "--single" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    zh_path = Path(args[0])
    if not zh_path.exists():
        print(f"错误: 文件不存在 {zh_path}")
        sys.exit(1)
    if single:
        single_mode(zh_path)
        return
    if len(args) >= 2:
        src_path = Path(args[1])
    else:
        src_path = zh_path.with_name(zh_path.name.replace("_zh.srt", "_src.srt"))
        if src_path == zh_path or not src_path.exists():
            print("错误: 未指定 src 且未找到同目录同名 _src.srt；单文件体检请加 --single")
            sys.exit(1)
    if not src_path.exists():
        print(f"错误: 文件不存在 {src_path}")
        sys.exit(1)
    compare_mode(zh_path, src_path)


if __name__ == "__main__":
    main()
