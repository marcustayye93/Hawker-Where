#!/usr/bin/env python3
"""Evidence transfer: pin dishes on unclassified stalls using internal proof.

Two free, high-precision transfers, applied only when the evidence is
unambiguous:
  1. same trade name (spacing-insensitive) classified at another venue
  2. same SFA licensee whose classified stalls all agree on one dish

Reads data/stalls_classified.json + data/sfa_raw.json, rewrites
data/stalls_classified.json with dish_source "name_transfer" /
"licensee_transfer". Run after classify.py, before merge-venues.py.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def key(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def main():
    raw = json.loads((DATA / "sfa_raw.json").read_text(encoding="utf-8"))
    lic = {(r.get("licenceNumber") or "").strip():
           (r.get("licenseeName") or "").strip() for r in raw}
    stalls = json.loads((DATA / "stalls_classified.json").read_text(encoding="utf-8"))

    bykey = defaultdict(set)
    bylic = defaultdict(set)
    for s in stalls:
        if not s["dish"]:
            continue
        if s["name"] != "Unnamed stall":
            bykey[key(s["name"])].add(s["dish"])
        L = lic.get(s["id"], "")
        if L and L.upper() != "NA":
            bylic[L].add(s["dish"])

    n_name = n_lic = 0
    for s in stalls:
        if s["dish"] or s["name"] == "Unnamed stall":
            continue
        hits = bykey.get(key(s["name"]), set())
        if len(hits) == 1:
            s["dish"] = next(iter(hits))
            s["dish_confidence"] = "medium"
            s["dish_source"] = "name_transfer"
            n_name += 1
            continue
        L = lic.get(s["id"], "")
        hits = bylic.get(L, set())
        if L and L.upper() != "NA" and len(hits) == 1:
            s["dish"] = next(iter(hits))
            s["dish_confidence"] = "medium"
            s["dish_source"] = "licensee_transfer"
            n_lic += 1

    (DATA / "stalls_classified.json").write_text(
        json.dumps(stalls, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(1 for s in stalls if s["dish"])
    print(f"name transfers: {n_name} | licensee transfers: {n_lic} | "
          f"classified total: {total} of {len(stalls)}")


if __name__ == "__main__":
    main()
