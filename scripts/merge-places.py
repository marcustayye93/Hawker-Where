#!/usr/bin/env python3
"""HawkerWhere v1: merge Google Places ratings into stalls_raw.json.

Phases (in priority order, stopping when the search budget is exhausted):
  1. One "<venue name> Singapore" search per venue -> venue rating fallback.
  2. High-confidence classified stalls with real trade names: "<stall> <venue>".
  3. Medium-confidence stalls, same query pattern.
  4. Unclassified stalls with real trade names.

Searches go through ~/workspace/skills/google-places/bin/gplaces (Text Search).
Details calls are rating-fields-only (never reviews/hours) and only when an
accepted search hit has no rating.

Matching: accepted hit iff (a) normalised names match (case-insensitive
substring either way, corporate suffixes stripped) AND (b) hit is within
~500 m of the venue. Otherwise rating stays null and rating_source="venue"
(UI shows the venue rating labeled "venue rating"); if the venue has no
rating either, rating_source=null ("No rating yet").

Budget: at most 2800 text searches per run. 0.4 s between calls; backs off
on 429 (30 s, then 120 s) and stops cleanly if rate limiting persists.

Progress is checkpointed to data/places_progress.json so the run is
resumable. Final outputs: data/stalls.json, data/places_log.json.
"""
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "stalls_raw.json")
OUT = os.path.join(DATA, "stalls.json")
LOG = os.path.join(DATA, "places_log.json")
PROGRESS = os.path.join(DATA, "places_progress.json")
GCLI = os.path.expanduser("~/workspace/skills/google-places/bin/gplaces")

MAX_SEARCHES = int(os.environ.get("MERGE_MAX_SEARCHES", 2800))
SLEEP_BETWEEN = 0.4
MAX_DIST_M = 500.0
HOST = "places.googleapis.com"
DETAILS_MASK = "id,displayName,rating,userRatingCount"

SUFFIX_TOKENS = {
    "pte", "ltd", "sdn", "bhd", "trading", "enterprise", "enterprises",
    "co", "inc", "llc", "holding", "holdings", "company", "pl", "corp",
}


def norm_name(name):
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t]
    while toks and toks[-1] in SUFFIX_TOKENS:
        toks.pop()
    return " ".join(toks)


def names_match(a, b):
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def run_search(query, lat=None, lng=None):
    """Run one Text Search via the gplaces CLI. Returns list of hits."""
    cmd = [GCLI, "search", query]
    if lat is not None and lng is not None:
        cmd += [str(lat), str(lng)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[:300]
        raise RuntimeError(f"gplaces search failed: {err}")
    return json.loads(proc.stdout or "[]")


def run_details_rating_only(place_id):
    """Rating-fields-only details call (no reviews, no hours)."""
    req = urllib.request.Request(f"https://{HOST}/v1/places/{place_id}", method="GET")
    req.add_header("X-Goog-FieldMask", DETAILS_MASK)
    add_surrogate_to_request(req, "custom.google-places", allowed_hosts=[HOST])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
        except Exception:
            err = {"error": str(e)}
        raise RuntimeError(f"details HTTP {e.code}: {json.dumps(err)[:300]}")


def is_rate_limited(exc):
    msg = str(exc).lower()
    return ("429" in msg or "resource_exhausted" in msg or "rate" in msg
            or "quota" in msg or "deadline" in msg)


def short_venue_name(name):
    return (name or "").split("(")[0].strip()


def main():
    raw = json.load(open(RAW))
    venues = {v["id"]: v for v in raw["venues"]}
    stalls = raw["stalls"]

    prog = {
        "text_searches": 0, "details_calls": 0,
        "stall_hits": 0, "venue_hits": 0,
        "venue_results": {},          # venue_id -> {rating, rating_count}
        "stall_results": {},          # stall_id -> {rating, rating_count, rating_source}
        "done_venues": [], "done_stalls": [],
        "stopped_early": False, "reason": "",
    }
    if os.path.exists(PROGRESS):
        try:
            prog.update(json.load(open(PROGRESS)))
            print(f"resuming: {prog['text_searches']} searches already done")
        except Exception as e:
            print(f"could not read progress, starting fresh: {e}")

    done_venues = set(prog["done_venues"])
    done_stalls = set(prog["done_stalls"])
    venue_ratings = prog["venue_results"]
    stall_results = prog["stall_results"]

    def save_progress():
        prog["done_venues"] = sorted(done_venues)
        prog["done_stalls"] = sorted(done_stalls)
        prog["venue_results"] = venue_ratings
        prog["stall_results"] = stall_results
        with open(PROGRESS, "w") as f:
            json.dump(prog, f)
        # print a one-line heartbeat for the run log
        print(f"  progress: searches={prog['text_searches']} "
              f"details={prog['details_calls']} stall_hits={prog['stall_hits']} "
              f"venue_hits={prog['venue_hits']}", flush=True)

    def call_with_backoff(fn, *args):
        for wait in (30, 120):
            try:
                return fn(*args)
            except Exception as e:
                if not is_rate_limited(e):
                    raise
                print(f"  rate limited ({e}), sleeping {wait}s", flush=True)
                time.sleep(wait)
        raise RuntimeError("rate limit persisted after backoffs; stopping")

    def venue_rating_of(vid):
        rec = venue_ratings.get(vid)
        if rec and rec.get("rating") is not None:
            return True
        return False

    # ---- phase 1: venue searches ----
    for v in raw["venues"]:
        vid = v["id"]
        if prog["text_searches"] >= MAX_SEARCHES:
            break
        if vid in done_venues:
            continue
        query = f"{v['name']} Singapore"
        try:
            hits = call_with_backoff(run_search, query, v["lat"], v["lng"])
            prog["text_searches"] += 1
        except RuntimeError as e:
            prog["stopped_early"] = True
            prog["reason"] = str(e)
            save_progress()
            break
        best = None
        for h in hits:
            if (h.get("businessStatus") == "CLOSED_PERMANENTLY"
                    or not names_match(v["name"], (h.get("displayName") or {}).get("text", ""))):
                continue
            loc = h.get("location") or {}
            if haversine_m(v["lat"], v["lng"], loc.get("latitude", 0), loc.get("longitude", 0)) > MAX_DIST_M:
                continue
            best = h
            break
        if best is not None:
            prog["venue_hits"] += 1
            venue_ratings[vid] = {
                "rating": best.get("rating"),
                "rating_count": best.get("userRatingCount"),
            }
        done_venues.add(vid)
        if prog["text_searches"] % 25 == 0:
            save_progress()
        time.sleep(SLEEP_BETWEEN)
    save_progress()

    # ---- phases 2-4: stall searches ----
    def stall_plan(s):
        if s["name"] == "Unnamed stall":
            return None
        dc = s["dish_confidence"]
        if dc == "high":
            return 2
        if dc == "medium":
            return 3
        if dc is None:
            return 4
        return None

    plan = [(stall_plan(s), i, s) for i, s in enumerate(stalls)]
    plan = [p for p in plan if p[0] is not None]
    plan.sort(key=lambda p: (p[0], p[1]))

    for phase, _, s in plan:
        sid = s["id"]
        if prog["text_searches"] >= MAX_SEARCHES:
            break
        if sid in done_stalls:
            continue
        vid = s.get("venue_id")
        v = venues.get(vid) if vid else None
        if v:
            query = f"{s['name']} {short_venue_name(v['name'])}"
            blat, blng = v["lat"], v["lng"]
        else:
            query = f"{s['name']} Singapore"
            blat = blng = None
        try:
            hits = call_with_backoff(run_search, query, blat, blng)
            prog["text_searches"] += 1
        except RuntimeError as e:
            prog["stopped_early"] = True
            prog["reason"] = str(e)
            save_progress()
            break
        best = None
        for h in hits:
            if h.get("businessStatus") == "CLOSED_PERMANENTLY":
                continue
            if not names_match(s["name"], (h.get("displayName") or {}).get("text", "")):
                continue
            if blat is not None:
                loc = h.get("location") or {}
                if haversine_m(blat, blng, loc.get("latitude", 0), loc.get("longitude", 0)) > MAX_DIST_M:
                    continue
            best = h
            break
        rating = best.get("rating") if best else None
        rcount = best.get("userRatingCount") if best else None
        if best is not None and rating is None:
            # accepted hit but no rating: one rating-only details call
            try:
                d = run_details_rating_only(best["id"])
                prog["details_calls"] += 1
                rating = d.get("rating")
                rcount = d.get("userRatingCount")
            except Exception as e:
                if is_rate_limited(e):
                    prog["stopped_early"] = True
                    prog["reason"] = f"rate limited on details: {e}"
                    save_progress()
                    break
                print(f"  details failed for {sid}: {e}", flush=True)
        if rating is not None:
            prog["stall_hits"] += 1
            stall_results[sid] = {"rating": rating, "rating_count": rcount,
                                  "rating_source": "stall"}
        else:
            stall_results[sid] = {"rating": None, "rating_count": None,
                                  "rating_source": "venue" if (vid and venue_rating_of(vid)) else None}
        done_stalls.add(sid)
        if prog["text_searches"] % 25 == 0:
            save_progress()
        time.sleep(SLEEP_BETWEEN)
    else:
        if prog["text_searches"] >= MAX_SEARCHES:
            prog["stopped_early"] = True
            prog["reason"] = f"budget exhausted ({MAX_SEARCHES} text searches)"

    save_progress()

    # ---- apply results, write outputs ----
    for s in stalls:
        sid = s["id"]
        if sid in stall_results:
            r = stall_results[sid]
            s["rating"] = r["rating"]
            s["rating_count"] = r["rating_count"]
            s["rating_source"] = r["rating_source"]
        # venue fallback: inherit the venue's rating, labeled as a venue rating
        if s["rating"] is None and s.get("venue_id"):
            vr = venue_ratings.get(s["venue_id"]) or {}
            if vr.get("rating") is not None:
                s["rating"] = vr["rating"]
                s["rating_count"] = vr.get("rating_count")
                s["rating_source"] = "venue"

    # write venue ratings into the venue records
    for v in raw["venues"]:
        vr = venue_ratings.get(v["id"]) or {}
        if vr.get("rating") is not None:
            v["rating"] = vr["rating"]
            v["rating_count"] = vr.get("rating_count")

    with open(OUT, "w") as f:
        json.dump(raw, f, ensure_ascii=False)

    # validate
    json.load(open(OUT))

    log = {
        "text_searches": prog["text_searches"],
        "details_calls": prog["details_calls"],
        "stall_hits": prog["stall_hits"],
        "venue_hits": prog["venue_hits"],
        "stopped_early": prog["stopped_early"],
        "reason": prog["reason"],
    }
    with open(LOG, "w") as f:
        json.dump(log, f, indent=2)

    n_stall = sum(1 for s in stalls if s["rating_source"] == "stall")
    n_venue = sum(1 for s in stalls if s["rating_source"] == "venue")
    n_none = sum(1 for s in stalls if s["rating_source"] is None)
    n_ven_rated = sum(1 for vid in venue_ratings if venue_ratings[vid].get("rating") is not None)

    print("\n==== SUMMARY ====")
    print(f"text searches: {prog['text_searches']} / {MAX_SEARCHES}")
    print(f"details calls: {prog['details_calls']}")
    print(f"stalls with stall-level ratings: {n_stall}")
    print(f"stalls on venue fallback: {n_venue}")
    print(f"stalls with no rating: {n_none}")
    print(f"venues with ratings: {n_ven_rated} / {len(raw['venues'])}")
    print(f"stopped_early: {prog['stopped_early']} ({prog['reason']})")
    print(f"wrote {OUT} and {LOG}")


if __name__ == "__main__":
    main()
