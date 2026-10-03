#!/usr/bin/env python3
"""Google-title harvest: pin dishes on unclassified stalls from their
Google listing titles (SFA names often carry no dish word; Google titles do).

Searches "<stall name> <venue>" per unclassified named stall via the
gplaces CLI, matches the listing title against the SFA name, then runs the
dish classifier over the title. Resumable via data/titles_progress.json.

Budget guard: stops after HARVEST_MAX searches this run (default 826, the
October free-tier remainder). Applying results to
data/stalls_classified.json happens in this script too (dish_source
"google_title", evidence stored on the stall row). Run after
classify.py/transfer-evidence.py, then re-run merge-venues.py.
"""
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(HERE))
from classify import classify  # noqa: E402

_spec = importlib.util.spec_from_file_location("merge_places", HERE / "merge-places.py")
_mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mp)

MAX_RUN = int(os.environ.get("HARVEST_MAX", "826"))
PROGRESS = DATA / "titles_progress.json"


def load_progress():
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"done": {}, "searches": 0}


def save_progress(p):
    PROGRESS.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    raw = json.loads((DATA / "stalls_raw.json").read_text(encoding="utf-8"))
    venues = {v["id"]: v for v in raw["venues"]}
    rated = {}
    sj = DATA / "stalls.json"
    if sj.exists():
        for s in json.loads(sj.read_text(encoding="utf-8"))["stalls"]:
            if s["rating_source"] in ("stall", "google"):
                rated[s["id"]] = True
    classified = json.loads((DATA / "stalls_classified.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in classified}

    prog = load_progress()
    done = prog["done"]
    sizes = Counter(s["venue_id"] for s in raw["stalls"])

    pool = [s for s in raw["stalls"]
            if not by_id.get(s["id"], {}).get("dish")
            and s["name"] != "Unnamed stall" and s["id"] not in done]
    # Group by (name, venue): one search covers duplicate licences.
    groups = {}
    for s in pool:
        groups.setdefault((s["name"], s["venue_id"]), []).append(s)
    ordered = sorted(groups.items(),
                     key=lambda kv: (0 if any(rated.get(x["id"]) for x in kv[1]) else 1,
                                     -sizes.get(kv[0][1], 0), -len(kv[1])))

    searches0 = prog["searches"]
    applied = 0
    for (name, vid), members in ordered:
        if prog["searches"] - searches0 >= MAX_RUN:
            print(f"budget stop: {prog['searches'] - searches0} searches this run")
            break
        v = venues.get(vid) or {}
        q = f"{name} {_mp.short_venue_name(v.get('name', ''))}".strip()
        try:
            hits = _mp.run_search(q, v.get("lat"), v.get("lng"))
        except Exception as e:  # noqa: BLE001
            print(f"search failed for {name!r}: {str(e)[:120]}", flush=True)
            if _mp.is_rate_limited(e):
                prog["stopped"] = "rate_limited"
                break
            hits = []
        prog["searches"] += 1
        time.sleep(0.4)

        result = {"google_name": None, "dish": None}
        for h in hits[:5]:
            gname = (h.get("displayName") or {}).get("text", "")
            if gname and _mp.names_match(name, gname):
                dish, _c, _cand, _cuisine, _also, _src = classify(gname)
                result = {"google_name": gname, "dish": dish}
                break
        for m in members:
            done[m["id"]] = result
        if result["dish"]:
            applied += len(members)
        if prog["searches"] % 50 == 0:
            save_progress(prog)
            print(f"  ...{prog['searches'] - searches0} searches, "
                  f"{applied} stalls mapped so far", flush=True)

    save_progress(prog)

    # Apply to stalls_classified.json (stalls still dishless only).
    n = 0
    for s in classified:
        r = done.get(s["id"])
        if r and r.get("dish") and not s["dish"]:
            s["dish"] = r["dish"]
            s["dish_confidence"] = "medium"
            s["dish_source"] = "google_title"
            s["dish_evidence"] = r["google_name"]
            n += 1
    (DATA / "stalls_classified.json").write_text(
        json.dumps(classified, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"applied {n} | total classified: "
          f"{sum(1 for s in classified if s['dish'])} of {len(classified)} | "
          f"searches this run: {prog['searches'] - searches0} (cumulative {prog['searches']})")


if __name__ == "__main__":
    main()
