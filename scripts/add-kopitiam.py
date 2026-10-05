#!/usr/bin/env python3
"""Fold the kopitiam-layer stalls into data/stalls_classified.json.

Steps:
  1. Load the existing classified rows (NEA stalls, already enriched by
     the brave/title/transfer passes). Drop the removed "kopi and teh"
     and "drinks" dishes from them in place (dish fields cleared, the
     stalls themselves stay), per Marcus's 2026-10-05 ruling.
  2. Load the three non-NEA SFA raw pulls, dedupe by licenceNumber
     (preferring a record with a real trade name), skip licences already
     present in the NEA set, and classify each new stall with
     classify.classify() - the same name rules the NEA stalls got.
  3. Append the new rows (same shape as classify.py writes) and merge in
     any new review-queue candidates.

Run after pull-sfa-kopitiam.py, before merge-venues.py. Existing rows
keep their enrichment (dish_source brave_web/google_title/...); only the
two removed drink dishes are touched on them.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(HERE))

import classify as C  # noqa: E402

REMOVED_DISHES = {"kopi and teh", "drinks"}
NEW_RAW_FILES = [
    "sfa_within_coffeeshop_raw.json",
    "sfa_coffeeshop_eating_raw.json",
    "sfa_ma_managed_raw.json",
]


def load_rows(fname):
    rows = json.loads((DATA / fname).read_text(encoding="utf-8"))
    return rows["data"] if isinstance(rows, dict) else rows


def main():
    stalls = json.loads((DATA / "stalls_classified.json").read_text(encoding="utf-8"))
    review = json.loads((DATA / "review_queue.json").read_text(encoding="utf-8"))
    existing_ids = {s["id"] for s in stalls}

    # 1. Strip the removed drink dishes from existing rows.
    stripped = Counter()
    for s in stalls:
        if s.get("dish") in REMOVED_DISHES:
            stripped[s["dish"]] += 1
            s["dish"] = None
            s["dish_confidence"] = None
            s["dish_source"] = None
        if s.get("also"):
            kept = [d for d in s["also"] if d not in REMOVED_DISHES]
            if len(kept) != len(s["also"]):
                stripped["also_entries"] += 1
            s["also"] = kept or None
    print(f"existing rows: stripped dishes {dict(stripped)}")

    # 2. Dedupe new records by licence, preferring real trade names.
    best = {}
    raw_total = 0
    for fname in NEW_RAW_FILES:
        for r in load_rows(fname):
            raw_total += 1
            lic = (r.get("licenceNumber") or "").strip()
            if not lic:
                continue
            name = (r.get("businessName") or "").strip()
            has_name = bool(name) and name.upper() != "NA"
            cur = best.get(lic)
            if cur is None:
                best[lic] = r
            else:
                cur_name = (cur.get("businessName") or "").strip()
                if has_name and (not cur_name or cur_name.upper() == "NA"):
                    best[lic] = r
    new_records = [r for lic, r in sorted(best.items()) if lic not in existing_ids]
    skipped_overlap = len(best) - len(new_records)
    print(f"new raw records: {raw_total}; unique licences: {len(best)}; "
          f"already in NEA set: {skipped_overlap}; to add: {len(new_records)}")

    # 3. Classify the new stalls with the same rules and append.
    added = 0
    new_review = []
    for r in new_records:
        name = (r.get("businessName") or "").strip()
        address = (r.get("establishmentAddress") or "").strip()
        dish, conf, candidates, cuisine, also, source = C.classify(name)
        lic = (r.get("licenceNumber") or "").strip()
        grade = (r.get("grades") or "").strip() or None
        if candidates:
            new_review.append({
                "stall_id": lic,
                "name": name or "Unnamed stall",
                "venue": None,
                "candidate_dishes": candidates,
            })
        if dish is None and name:
            normal = C.normalize(name)
            if C.phrase_in("seafood", normal) or C.phrase_in("hai xian", normal):
                new_review.append({
                    "stall_id": lic,
                    "name": name,
                    "venue": None,
                    "candidate_dishes": ["seafood_untyped"],
                })
        stalls.append({
            "id": lic,
            "name": name if name and name.upper() != "NA" else "Unnamed stall",
            "unit": C.extract_unit(address),
            "address": address,
            "postal": C.extract_postal(address),
            "venue_id": None,
            "dish": dish,
            "dish_confidence": conf,
            "dish_source": source,
            "cuisine": cuisine,
            "also": also or None,
            "rating": None,
            "rating_count": None,
            "rating_source": None,
            "safe_grade": grade,
        })
        added += 1

    review.extend(new_review)
    (DATA / "stalls_classified.json").write_text(
        json.dumps(stalls, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "review_queue.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

    new_rows = stalls[len(stalls) - added:] if added else []
    tagged = sum(1 for s in new_rows if s["dish"])
    print(f"added {added} kopitiam-layer stalls; dish-tagged {tagged} "
          f"({tagged / added:.1%})" if added else "added 0")
    print("new-stall dish counts:",
          Counter(s["dish"] for s in new_rows if s["dish"]).most_common(15))
    print(f"stalls_classified total now: {len(stalls)}; review queue: {len(review)}")


if __name__ == "__main__":
    main()
