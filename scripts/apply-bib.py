#!/usr/bin/env python3
"""Apply the Michelin Bib Gourmand flags to data/stalls.json.

Reads data/bib_gourmand.json (michelin name -> stall id, hand-matched:
see data/bib_gourmand.json for the basis of each match) and writes:
  stall["bib"]        True on matched stalls (field removed elsewhere)
  stall["bib_name"]   the Michelin's name for the establishment, so the
                      tab can show it even when the SFA trade name is
                      missing or spelled differently.
Run after merge-places.py when the payload is regenerated.
"""
import json

ROOT = "data"


def main():
    bib = json.load(open(f"{ROOT}/bib_gourmand.json"))
    payload = json.load(open(f"{ROOT}/stalls.json"))
    by_id = {s["id"]: s for s in payload["stalls"]}

    wanted = {}
    for e in bib["entries"]:
        wanted.setdefault(e["stall_id"], e["michelin"])
    entry_by_id = {e["stall_id"]: e for e in bib["entries"]}

    missing = [sid for sid in wanted if sid not in by_id]
    if missing:
        raise SystemExit(f"stall ids not in payload: {missing}")

    n = 0
    for s in payload["stalls"]:
        if s["id"] in wanted:
            s["bib"] = True
            s["bib_name"] = wanted[s["id"]]
            # Where Michelin's stated specialty is a taxonomy dish and the
            # stall has no dish yet, set it from the Bib evidence.
            e = entry_by_id[s["id"]]
            if e.get("dish") and not s.get("dish"):
                s["dish"] = e["dish"]
                s["dish_source"] = "bib_gourmand"
            n += 1
        else:
            s.pop("bib", None)
            s.pop("bib_name", None)

    json.dump(payload, open(f"{ROOT}/stalls.json", "w"), ensure_ascii=False, separators=(",", ":"))
    establishments = len({e["michelin"] for e in bib["entries"]})
    print(f"bib flagged: {n} stall records across {establishments} establishments")


if __name__ == "__main__":
    main()
