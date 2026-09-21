"""Timing exports: JSON timing map + SRT captions from sentence timings."""
import json
from typing import List, Dict


def _fmt_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_timing_map(timings: List[Dict], out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2, ensure_ascii=False)
    return out_path


def export_srt(timings: List[Dict], out_path: str) -> str:
    lines = []
    for t in timings:
        lines.append(str(t["index"] + 1))
        lines.append(f"{_fmt_srt(t['start'])} --> {_fmt_srt(t['end'])}")
        lines.append(t["text"])
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path
