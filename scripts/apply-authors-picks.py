#!/usr/bin/env python3
"""Apply data/authors_picks.json onto data/stalls.json.

Author's Pick is a curated list, not a register import. Existing SFA
stalls get author_pick flags (and a dish only where the pick itself is
the evidence for a real hawker stall). Places that are not in the SFA
register are added as manual venue + stall records marked
author_manual, so the headline register counts and the generated dish
pages can stay register-based.

Run after apply-corrections.py on any payload regeneration, before
make-taxonomy.py and gen-dish-pages.py. Idempotent: manual records and
author fields are removed and rewritten from the config each run.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "authors_picks.json")
STALLS = os.path.join(ROOT, "data", "stalls.json")

AUTHOR_FIELDS = ("author_pick", "author_name", "author_cuisine",
                 "author_order", "author_evidence", "author_manual")
MANUAL_PREFIX = "authors-pick-"


def main():
    payload = json.load(open(STALLS))
    cfg = json.load(open(CONFIG))

    # Drop the previous run's manual records and author fields, so a
    # changed config does not leave stale picks behind.
    payload["venues"] = [v for v in payload["venues"]
                         if not v["id"].startswith(MANUAL_PREFIX)]
    stalls = []
    for s in payload["stalls"]:
        if s.get("author_manual") or s["id"].startswith(MANUAL_PREFIX):
            continue
        for field in AUTHOR_FIELDS:
            s.pop(field, None)
        stalls.append(s)
    payload["stalls"] = stalls
    by_id = {s["id"]: s for s in payload["stalls"]}

    applied = 0
    for entry in cfg.get("existing", []):
        stall = by_id.get(entry["stall_id"])
        if stall is None:
            raise SystemExit(f"author pick stall id not in payload: {entry['stall_id']}")
        if entry.get("name"):
            stall["name"] = entry["name"]
        stall["author_pick"] = True
        stall["author_name"] = entry.get("name") or stall.get("name")
        stall["author_cuisine"] = entry["cuisine_label"]
        stall["author_order"] = entry.get("order", 99)
        stall["author_evidence"] = entry.get("evidence")
        dish = entry.get("dish")
        if dish and stall.get("dish") != dish:
            stall["dish"] = dish
            stall["dish_confidence"] = "high"
            stall["dish_source"] = "author_pick"
        applied += 1

    venues_by_id = {v["id"]: v for v in payload["venues"]}
    for entry in cfg.get("manual", []):
        s = entry["stall"]
        # A manual stall may sit inside a venue the payload already has
        # (reference it, create nothing) or bring its own manual venue.
        ref = s.get("venue_ref")
        if ref:
            venue = venues_by_id.get(ref)
            if venue is None:
                raise SystemExit(f"manual author venue_ref not in payload: {ref}")
        else:
            v = entry["venue"]
            if v["id"] in venues_by_id:
                raise SystemExit(f"manual author venue id already exists: {v['id']}")
            venue = {
                "id": v["id"],
                "name": v["name"],
                "address": v["address"],
                "lat": v["lat"],
                "lng": v["lng"],
                "rating": None,
                "rating_count": None,
                "closed": False,
                "closure_note": None,
            }
            payload["venues"].append(venue)
            venues_by_id[venue["id"]] = venue
        stall = {
            "id": s["id"],
            "name": s["name"],
            "unit": s.get("unit"),
            "address": s["address"],
            "postal": s.get("postal"),
            "venue_id": venue["id"],
            "dish": s.get("dish"),
            "dish_confidence": "high" if s.get("dish") else None,
            "dish_source": "author_pick" if s.get("dish") else None,
            "cuisine": s.get("cuisine"),
            "also": None,
            "rating": None,
            "rating_count": None,
            "rating_source": None,
            "safe_grade": "NA",
            "author_pick": True,
            "author_manual": True,
            "author_name": s["name"],
            "author_cuisine": s["cuisine_label"],
            "author_order": entry.get("order", 99),
            "author_evidence": s.get("evidence"),
        }
        payload["stalls"].append(stall)
        applied += 1

    with open(STALLS, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print("author picks applied:", applied)


if __name__ == "__main__":
    main()
