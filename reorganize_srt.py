#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重组字幕时间轴：合并过短条目、拆分过长条目、消除 <0.8s 条目，并重编号。

规则（默认值可用命令行参数调整）：
- 合并：文本 <= 6 字 且 与下一条间隔 <= 2.0s 且 合并后 <= 38 字 且 合并后时长 <= 15s
  -> 合并，文本空格连接，时间轴 [本条 start, 下条 end]。反复扫描直到无可合并。
- 拆分：文本 >= 26 字 且 时长 >= 5s -> 在标点/短语边界按字数比例拆时间轴
  （毫秒精度，子条间留 40ms 空隙）；切不出合理边界或任一子条 <1.2s 则不拆。反复扫描。
- 硬约束：处理后所有条目 start<end、互不重叠、不越出原首末范围、无空文本；
  时长 <0.8s 的条目通过占用相邻间隙/向邻居借时间消除。

用法:
  python reorganize_srt.py output/xxx/xxx_zh.srt
  python reorganize_srt.py                      # 自动取 raw/ 第一个媒体对应的 _zh.srt
  python reorganize_srt.py <srt> --dry-run      # 只打印统计，不写回

双语模式（merge_bilingual_srt.py 的产物，每条目两行文本）:
  python reorganize_srt.py <双语.srt> --bilingual [--src-first]
  - 默认第 1 行译文、第 2 行原文（与合并默认一致）；--src-first 表示第 1 行原文
  - 字数阈值（合并/拆分/单条上限）只看译文行；合并时两行各自配对连接，
    拆分时另一语言行按译文子条字数比例切分（优先标点/空格边界），配对不会错位
  - 某一侧为单空格 " " 的占位条目可正常参与；单行条目按译文处理并警告
"""

import argparse
import re
import sys
from pathlib import Path

from common import get_output_dir, RAW_DIR
MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v", ".ts",
              ".aac", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".wma"}

TS_RE = re.compile(r"(\d+):(\d+):(\d+),(\d+)")
BREAK_CHARS = set("。，、！？；：…—·,.!?;:\"'）)】」』》〉.…—–")
MIN_SPLIT_CHARS = 4  # 拆分出的子条至少这么多字，避免碎条
SPLIT_GAP_MS = 40    # 拆分后子条之间的空隙


def ts_to_ms(s):
    m = TS_RE.fullmatch(s.strip())
    h, mi, sec, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + sec) * 1000 + ms


def ms_to_ts(ms):
    h, rem = divmod(ms, 3600000)
    mi, rem = divmod(rem, 60000)
    sec, m = divmod(rem, 1000)
    return f"{h:02d}:{mi:02d}:{sec:02d},{m:03d}"


def text_len(t):
    return len(re.sub(r"\s", "", t))


def join_parts(a, b):
    """合并两段文本：一侧为空白占位时不留多余空格；两侧都空则返回单空格占位。"""
    a, b = a.strip(), b.strip()
    if a and b:
        return a + " " + b
    return a or b or " "


def split_extra(text, primary_parts):
    """双语模式：把另一语言行按主行各子条字数比例切成对应份数，优先标点/空格边界。"""
    k = len(primary_parts)
    if not text.strip():
        return [" "] * k
    if k == 1:
        return [text.strip()]
    lens = [text_len(p) for p in primary_parts]
    total = sum(lens) or 1
    cand = split_text_points(text)
    for i, ch in enumerate(text):
        if ch.isspace() and i + 1 < len(text):
            cand.append(i + 1)
    cuts = []
    prev = 0
    for j in range(k - 1):
        target = round(len(text) * sum(lens[:j + 1]) / total)
        choices = [p for p in cand if prev < p < len(text)]
        if choices:
            best = min(choices, key=lambda p: abs(p - target))
        else:
            best = max(min(target, len(text) - 1), prev + 1)
        cuts.append(best)
        prev = best
    parts = []
    last = 0
    for p in cuts + [len(text)]:
        seg = text[last:p].strip()
        parts.append(seg if seg else " ")
        last = p
    return parts


def parse(path):
    raw = open(path, encoding="utf-8").read().strip("\n").split("\n")
    entries = []
    i = 0
    while i < len(raw):
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
        # 只有真正的空行才是条目分隔；单空格 " " 是有意义的占位文本（手改/编辑工具会产出）
        while i < len(raw) and raw[i].rstrip("\r") != "":
            text_lines.append(raw[i].rstrip("\r"))
            i += 1
        i += 1  # 跳过空行
        entries.append({
            "start": ts_to_ms(start_s),
            "end": ts_to_ms(end_s),
            "text": "\n".join(text_lines),
        })
    return entries


def split_text_points(text):
    """候选切分位置（字符索引，在该索引前切开），取标点/短语边界。"""
    points = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch in BREAK_CHARS:
            j = i + 1
            while j < n and (text[j] in BREAK_CHARS or text[j].isspace()):
                j += 1
            if j < n:
                points.append(j)
    out = []
    for p in points:
        if p not in out:
            out.append(p)
    return out


def try_split(entry, cfg, stats):
    text = entry["text"]
    L = text_len(text)
    dur = entry["end"] - entry["start"]
    if L < cfg.split_chars or dur < cfg.split_min_dur_ms:
        return None
    cand = split_text_points(text)
    if not cand:
        return None
    # 期望份数：每份约 20-25 字；同时每份时长尽量 >=1.3s 留余量
    k_ideal = max(2, -(-L // 20))
    k_cap = max(2, dur // 1300)
    for k in range(min(k_ideal, k_cap), 1, -1):
        target = L / k
        chosen = []
        ok = True
        prev = 0
        remaining_parts = k
        for _ in range(k - 1):
            remaining_parts -= 1
            best, best_score = None, None
            for p in cand:
                if p <= prev:
                    continue
                seg_len = text_len(text[prev:p])
                if seg_len < MIN_SPLIT_CHARS:
                    continue
                rest_len = L - text_len(text[:p])
                if remaining_parts > 0 and rest_len < MIN_SPLIT_CHARS * remaining_parts:
                    continue
                score = abs(seg_len - target)
                if best_score is None or score < best_score:
                    best, best_score = p, score
            if best is None:
                ok = False
                break
            chosen.append(best)
            prev = best
        if not ok or text_len(text[prev:]) < MIN_SPLIT_CHARS:
            continue
        parts = []
        last = 0
        for p in chosen + [len(text)]:
            parts.append(text[last:p].strip())
            last = p
        if any(not pt for pt in parts) or len(parts) != k:
            continue
        usable = dur - SPLIT_GAP_MS * (k - 1)
        if usable <= 0:
            continue
        lens = [text_len(pt) for pt in parts]
        durs = [usable * ln / L for ln in lens]
        if any(d < cfg.split_min_part_ms for d in durs):
            continue
        ms_list = [round(d) for d in durs]
        ms_list[-1] += usable - sum(ms_list)
        out = []
        t = entry["start"]
        for j, pt in enumerate(parts):
            out.append({"start": t, "end": t + ms_list[j], "text": pt})
            t += ms_list[j] + SPLIT_GAP_MS
        out[-1]["end"] = entry["end"]
        good = all(o["end"] > o["start"] for o in out)
        for j in range(k - 1):
            if out[j]["end"] > out[j + 1]["start"]:
                good = False
        if not good:
            continue
        if "extra" in entry:
            extras = split_extra(entry["extra"], parts)
            for o, ex in zip(out, extras):
                o["extra"] = ex
        stats["split"] += 1
        return out
    return None


def merge_pass(entries, cfg, stats):
    out = []
    i = 0
    merged = False
    while i < len(entries):
        e = entries[i]
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        # 双语模式：只有两侧都非空占位的条目才允许合并，避免"只有日文"+"只有中文"跨语言拼对
        pairable = ("extra" not in e or nxt is None
                    or (e["text"].strip() and e["extra"].strip()
                        and nxt["text"].strip() and nxt.get("extra", "").strip()))
        if (nxt is not None
                and pairable
                and text_len(e["text"]) <= cfg.merge_chars
                and nxt["start"] - e["end"] <= cfg.merge_gap_ms
                and text_len(e["text"] + nxt["text"]) <= cfg.max_chars
                and nxt["end"] - e["start"] <= cfg.merge_max_dur_ms):
            merged_entry = {
                "start": e["start"],
                "end": nxt["end"],
                "text": join_parts(e["text"], nxt["text"]),
            }
            if "extra" in e or "extra" in nxt:
                merged_entry["extra"] = join_parts(e.get("extra", " "), nxt.get("extra", " "))
            out.append(merged_entry)
            stats["merge"] += 1
            merged = True
            i += 2
        else:
            out.append(e)
            i += 1
    return out, merged


def split_pass(entries, cfg, stats):
    out = []
    changed = False
    for e in entries:
        res = try_split(e, cfg, stats)
        if res:
            out.extend(res)
            changed = True
        else:
            out.append(e)
    return out, changed


def fix_short(entries, cfg, stats):
    """消除时长 <min_dur 的条目：先占用相邻间隙，不足则向邻居借时间。"""
    for _ in range(50):
        changed = False
        for i, e in enumerate(entries):
            if e["end"] - e["start"] >= cfg.min_dur_ms:
                continue
            need = cfg.min_dur_ms - (e["end"] - e["start"])
            prev_end = entries[i - 1]["end"] if i > 0 else None
            next_start = entries[i + 1]["start"] if i + 1 < len(entries) else None
            left_limit = max(prev_end + 1 if prev_end is not None else 0, entries[0]["start"])
            right_limit = min(next_start - 1 if next_start is not None else 10**12,
                              entries[-1]["end"])
            take = min(need, right_limit - e["end"])
            if take > 0:
                e["end"] += take
                need -= take
            take = min(need, e["start"] - left_limit)
            if take > 0:
                e["start"] -= take
                need -= take
            if need > 0:
                for j in (i - 1, i + 1):
                    if need <= 0 or j < 0 or j >= len(entries):
                        continue
                    d = entries[j]["end"] - entries[j]["start"]
                    if d <= cfg.min_dur_ms:
                        continue
                    give = min(need, d - cfg.min_dur_ms)
                    if j < i:
                        entries[j]["end"] -= give
                    else:
                        entries[j]["start"] += give
                    need -= give
            if need > 0:
                print(f"错误: 第 {i+1} 条目相邻条目无法让出 {need}ms，无法修正短条目")
                sys.exit(1)
            stats["shortfix"] += 1
            changed = True
        if not changed:
            return


def validate(entries, cfg, orig_first_start, orig_last_end, allow_overlong=False):
    overlong = 0
    for i, e in enumerate(entries):
        assert e["end"] > e["start"], f"条目 {i} start>=end"
        assert e["start"] >= orig_first_start, f"条目 {i} 越过原首条 start"
        assert e["end"] <= orig_last_end, f"条目 {i} 越过原末条 end"
        assert (e["text"] + e.get("extra", "")).strip(), f"条目 {i} 空文本"
        length = text_len(e["text"])
        if length > cfg.max_chars:
            assert allow_overlong, f"条目 {i} 超过 {cfg.max_chars} 字"
            print(f"警告: 条目 {i+1} 为 {length} 字，超过 {cfg.max_chars} 字（dry-run 继续，正式写回仍会失败）")
            overlong += 1
        assert e["end"] - e["start"] >= cfg.min_dur_ms, f"条目 {i} 时长不足"
        if i + 1 < len(entries):
            assert entries[i + 1]["start"] >= e["end"], f"条目 {i}/{i+1} 重叠"
    return overlong


def reorganize(entries, cfg):
    stats = {"merge": 0, "split": 0, "shortfix": 0}
    # 合并与拆分交替进行直到都稳定（拆分产生的短条可能又可合并）
    for _ in range(20):
        changed = False
        for _ in range(200):
            entries, m = merge_pass(entries, cfg, stats)
            changed = changed or m
            if not m:
                break
        for _ in range(200):
            entries, s = split_pass(entries, cfg, stats)
            changed = changed or s
            if not s:
                break
        if not changed:
            break
    fix_short(entries, cfg, stats)
    return entries, stats


def resolve_srt_path(arg):
    """命令行指定则校验后使用，否则取 raw/ 第一个媒体对应的 _zh.srt。"""
    if arg:
        p = Path(arg)
        if not p.exists():
            print(f"错误: 文件不存在 {p}")
            sys.exit(1)
        return p
    files = sorted(p for ext in MEDIA_EXTS for p in RAW_DIR.glob(f"*{ext}"))
    if not files:
        print("用法: python reorganize_srt.py output/<stem>/<stem>_zh.srt")
        print("或放入媒体文件到 raw/ 后不带参数运行")
        sys.exit(1)
    srt = get_output_dir() / files[0].stem / f"{files[0].stem}_zh.srt"
    if not srt.exists():
        print(f"错误: 未找到字幕文件 {srt}，请先完成翻译生成 _zh.srt")
        sys.exit(1)
    return srt


def main():
    ap = argparse.ArgumentParser(description="重组字幕时间轴：合并过短、拆分过长条目")
    ap.add_argument("srt", nargs="?", help="SRT 路径（默认取 raw/ 第一个媒体对应的 _zh.srt）")
    ap.add_argument("--merge-chars", type=int, default=6, help="合并阈值：文本不超过多少字（默认 6）")
    ap.add_argument("--merge-gap-ms", type=int, default=2000, help="合并阈值：与下一条间隔不超过多少毫秒（默认 2000）")
    ap.add_argument("--merge-max-dur-ms", type=int, default=15000, help="合并后时长上限毫秒，超过则不合并（默认 15000）")
    ap.add_argument("--split-chars", type=int, default=26, help="拆分阈值：文本不少于多少字（默认 26）")
    ap.add_argument("--split-min-dur-ms", type=int, default=5000, help="拆分阈值：时长不少于多少毫秒（默认 5000）")
    ap.add_argument("--split-min-part-ms", type=int, default=1200, help="拆出的子条最小时长毫秒（默认 1200）")
    ap.add_argument("--max-chars", type=int, default=38, help="单条最大字数硬约束（默认 38）")
    ap.add_argument("--min-dur-ms", type=int, default=800, help="单条最小时长毫秒硬约束（默认 800）")
    ap.add_argument("--bilingual", action="store_true",
                    help="双语模式：每条目两行文本，字数判断只看译文行，配对不错位")
    ap.add_argument("--src-first", action="store_true",
                    help="双语模式下第 1 行是原文、第 2 行是译文（默认第 1 行译文）")
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不写回文件")
    cfg = ap.parse_args()

    srt_path = resolve_srt_path(cfg.srt)
    entries = parse(srt_path)
    if cfg.bilingual:
        single = 0
        for e in entries:
            lines = e["text"].split("\n")
            if len(lines) > 2:
                print("错误: 双语模式要求每条目至多两行文本（第 1 行译文、第 2 行原文）；"
                      "超过两行请先在编辑器里整理")
                sys.exit(1)
            if len(lines) == 1:
                lines.append(" ")
                single += 1
            first, second = lines[0], lines[1]
            e["text"], e["extra"] = (second, first) if cfg.src_first else (first, second)
        if single:
            print(f"注意: {single} 条只有一行，已按译文行处理、另一侧补空格占位")
    n0 = len(entries)
    first_start, last_end = entries[0]["start"], entries[-1]["end"]

    entries, stats = reorganize(entries, cfg)
    overlong = validate(entries, cfg, first_start, last_end, allow_overlong=cfg.dry_run)

    if cfg.bilingual:
        for e in entries:
            first, second = (e["extra"], e["text"]) if cfg.src_first else (e["text"], e["extra"])
            e["text"] = first + "\n" + second

    durs = [e["end"] - e["start"] for e in entries]
    print(f"字幕文件: {srt_path}")
    print(f"原始条目数: {n0}")
    print(f"处理后条目数: {len(entries)}")
    print(f"合并次数: {stats['merge']}")
    print(f"拆分次数: {stats['split']}")
    print(f"短条目(<{cfg.min_dur_ms}ms)修正次数: {stats['shortfix']}")
    print(f"最大时长: {max(durs)}ms  最小时长: {min(durs)}ms  平均: {sum(durs)/len(durs):.0f}ms")
    if overlong:
        print(f"校验: 结构、时长与范围通过；{overlong} 条超过字数上限（见上述警告）")
    else:
        print("校验: start<end / 无重叠 / 无空文本 / 字数与时长上限 / 未越原首末范围 — 全部通过")

    if cfg.dry_run:
        print("[dry-run] 未写回文件")
        return

    backup = srt_path.with_name(srt_path.name + ".bak")
    if not backup.exists():
        backup.write_bytes(srt_path.read_bytes())
        print(f"备份 -> {backup}")

    out_lines = []
    for i, e in enumerate(entries, 1):
        out_lines.append(str(i))
        out_lines.append(f"{ms_to_ts(e['start'])} --> {ms_to_ts(e['end'])}")
        out_lines.append(e["text"])
        out_lines.append("")
    with open(srt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines))
    print(f"[重组完成] -> {srt_path}")


if __name__ == "__main__":
    main()
