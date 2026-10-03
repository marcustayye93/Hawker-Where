#!/usr/bin/env python3
"""List every unclassified (dish == null) stall name for Marcus's eyeball pass.

Reads data/stalls_raw.json (post venue-merge), writes
data/unclassified-names-2026-10-02.md. Grouped: repeat names first
(a rule there covers many stalls), then the full alphabetical list.
Unnamed stalls (SFA businessName "NA") are counted separately: they
cannot be classified by name at all.
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

d = json.loads((DATA / "stalls_raw.json").read_text(encoding="utf-8"))
venues = {v["id"]: v["name"] for v in d["venues"]}
un = [s for s in d["stalls"] if not s["dish"]]
unnamed = [s for s in un if s["name"] == "Unnamed stall"]
named = [s for s in un if s["name"] != "Unnamed stall"]

cnt = Counter(s["name"] for s in named)
example = {}
for s in named:
    example.setdefault(s["name"], venues.get(s["venue_id"], "venue not matched"))

repeats = sorted(((n, c) for n, c in cnt.items() if c >= 2),
                 key=lambda kv: (-kv[1], kv[0].lower()))
singles = sorted((n for n, c in cnt.items() if c == 1), key=lambda n: n.lower())

lines = []
lines.append("# HawkerWhere: unclassified stall names for eyeball review")
lines.append("")
lines.append("Date: 2 Oct 2026. Source: SFA register (5,621 stalls), after the")
lines.append("45+1 dish name-parser pass (western food added 2 Oct).")
lines.append("")
lines.append(f"- Unclassified stalls: {len(un)} of 5,621.")
lines.append(f"- Unnamed (SFA name is NA, no name to parse): {len(unnamed)}. "
             "Tagging loop only.")
lines.append(f"- Named but unclassified: {len(named)} stalls, "
             f"{len(cnt)} distinct names.")
lines.append(f"- Repeat names (2+ stalls): {len(repeats)} names covering "
             f"{sum(c for _, c in repeats)} stalls.")
lines.append("")
lines.append("How to use: skim for patterns. If you see a name family that")
lines.append("clearly means one dish or category (or spot names where the")
lines.append("dish is implied but not literally in the name), tell me the")
lines.append("rule and I will fold it into the classifier. One rule can")
lines.append("cover many stalls at once.")
lines.append("")
lines.append("## Repeat names (2+ stalls each)")
lines.append("")
for name, c in repeats:
    lines.append(f"- {name} x{c} (e.g. {example[name]})")
lines.append("")
lines.append("## Every distinct name, alphabetical")
lines.append("")
for name in sorted(cnt, key=lambda n: n.lower()):
    c = cnt[name]
    lines.append(f"- {name}" + (f" x{c}" if c > 1 else "") +
                 f" ({example[name]})")

out = DATA / "unclassified-names-2026-10-02.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {out}: {len(un)} unclassified | {len(unnamed)} unnamed | "
      f"{len(named)} named | {len(cnt)} distinct | {len(repeats)} repeats")
