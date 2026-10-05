#!/usr/bin/env python3
"""Geocode kopitiam/food-court venue postals via the OneMap search API.

Reads the three non-NEA SFA raw pulls (data/sfa_within_coffeeshop_raw.json,
data/sfa_coffeeshop_eating_raw.json, data/sfa_ma_managed_raw.json), takes
the unique 6-digit postals, and resolves each to lat/lng + building name
via https://www.onemap.gov.sg/api/common/elastic/search.

Outputs:
  data/onemap_geocode_cache.json  postal -> {ok, lat, lng, building, address} | {ok: False, error}
  data/kopitiam_venues.json       {"venues": [{id, name, address, lat, lng, postal}]}

Idempotent: postals already in the cache are not re-queried. Venue name
is the OneMap BUILDING when real, else "<blk> <road>". Venue ids are
slug(name + postal) so they stay unique and stable.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
CACHE_PATH = DATA / "onemap_geocode_cache.json"
OUT_PATH = DATA / "kopitiam_venues.json"

RAW_FILES = [
    "sfa_within_coffeeshop_raw.json",
    "sfa_coffeeshop_eating_raw.json",
    "sfa_ma_managed_raw.json",
]
API = "https://www.onemap.gov.sg/api/common/elastic/search"
POSTAL_RE = re.compile(r"\b(\d{6})\b")
HEADERS = {"User-Agent": "HawkerWhere/1.0 (research data pull; contact: gethowmuch.net)"}


def slug(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed-venue"


def title(s):
    return re.sub(r"\s+", " ", (s or "").strip()).title()


def extract_postal(address):
    ms = POSTAL_RE.findall(address or "")
    return ms[-1] if ms else None


def geocode(postal):
    params = {"searchVal": postal, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
    resp = requests.get(API, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results") or []
    if not results:
        return {"ok": False, "error": "no results"}
    r = results[0]
    return {
        "ok": True,
        "lat": float(r["LATITUDE"]),
        "lng": float(r["LONGITUDE"]),
        "building": (r.get("BUILDING") or "").strip(),
        "blk": (r.get("BLK_NO") or "").strip(),
        "road": (r.get("ROAD_NAME") or "").strip(),
        "address": (r.get("ADDRESS") or "").strip(),
    }


def geocode_safe(postal):
    try:
        return geocode(postal)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}


def main():
    postals = set()
    for fname in RAW_FILES:
        rows = json.loads((DATA / fname).read_text(encoding="utf-8"))
        rows = rows["data"] if isinstance(rows, dict) else rows
        for r in rows:
            p = extract_postal(r.get("establishmentAddress"))
            if p:
                postals.add(p)
    print(f"unique postals to geocode: {len(postals)}")

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    todo = sorted(p for p in postals if p not in cache)
    print(f"already cached: {len(postals) - len(todo)}; to fetch: {len(todo)}")

    failures = []
    done_count = 0
    # Modest parallelism: sequential fetching ran at ~35 postals/min.
    with ThreadPoolExecutor(max_workers=6) as pool:
        for postal, result in zip(todo, pool.map(geocode_safe, todo)):
            cache[postal] = result
            if not result.get("ok"):
                failures.append(postal)
            done_count += 1
            if done_count % 25 == 0:
                CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  {done_count}/{len(todo)} fetched, failures so far: {len(failures)}", flush=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    venues = []
    failed_all = []
    for postal in sorted(postals):
        c = cache.get(postal) or {}
        if not c.get("ok"):
            failed_all.append(postal)
            continue
        building = c["building"]
        if building and building.upper() != "NIL":
            name = title(building)
        else:
            name = title(f"{c['blk']} {c['road']}".strip())
        addr_base = title(re.sub(r"\s+SINGAPORE\s+\d{6}$", "", c["address"]))
        venues.append({
            "id": slug(f"{name} {postal}"),
            "name": name,
            "address": f"{addr_base}, Singapore {postal}",
            "lat": c["lat"],
            "lng": c["lng"],
            "postal": postal,
        })
    OUT_PATH.write_text(json.dumps({"venues": venues}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"venues written: {len(venues)} -> {OUT_PATH.name}")
    print(f"geocode failures: {len(failed_all)} {failed_all[:20]}")


if __name__ == "__main__":
    main()
