#!/usr/bin/env python3
"""Apply data/corrections.json onto data/stalls.json.

Hand corrections with cited evidence (name fixes, field reports).
Mirrors apply-bib.py: idempotent, run after merge-places.py and
apply-bib.py on any payload regeneration, before make-taxonomy.py
and gen-dish-pages.py, or the corrections silently wash out.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORRECTIONS = os.path.join(ROOT, "data", "corrections.json")
STALLS = os.path.join(ROOT, "data", "stalls.json")

FIELDS = ("dish", "dish_confidence", "dish_evidence", "dish_source",
          "name", "also")


def main():
    payload = json.load(open(STALLS))
    corr = json.load(open(CORRECTIONS))
    by_id = {s["id"]: s for s in payload["stalls"]}
    applied = 0
    for entry in corr["corrections"]:
        stall = by_id.get(entry["id"])
        if stall is None:
            print("MISSING STALL:", entry["id"])
            continue
        for field in FIELDS:
            if field in entry:
                stall[field] = entry[field]
        applied += 1
    with open(STALLS, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print("corrections applied:", applied, "of", len(corr["corrections"]))


if __name__ == "__main__":
    main()
