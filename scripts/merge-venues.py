#!/usr/bin/env python3
"""Merge SFA stalls with NEA hawker-centre venues.

Reads:
  data/stalls_classified.json  (from classify.py)
  data/nea_geojson.json         (NEA Hawker Centres, via data.gov.sg poll-download)
  data/nea_closures.csv     (NEA closure CSV, via data.gov.sg poll-download)

Writes data/stalls_raw.json with the exact v1 schema, and rewrites
data/review_queue.json with venue names attached, ordered by venue stall
count (venue size proxy).

Join strategy: 6-digit postal code first, then token-overlap fuzzy match of
the venue name against the stall address, then a manual override table for
stall postals that differ from the venue postal by one digit.
"""
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
TODAY = date(2026, 10, 1)
GENERATED = "2026-10-01"

TAXONOMY = [
    "chicken rice", "char kway teow", "hokkien mee", "laksa", "bak chor mee",
    "wanton mee", "prawn mee", "mee siam", "mee rebus", "lor mee",
    "bak kut teh", "fish soup", "ban mian", "yong tau foo", "roti prata",
    "nasi lemak", "nasi padang", "nasi briyani", "murtabak", "thosai",
    "satay", "oyster omelette", "carrot cake", "popiah", "kueh pie tee",
    "western food",
    "chee cheong fun", "porridge and congee", "duck rice", "kway chap",
    "chwee kueh", "tutu kueh", "putu piring", "rojak", "tau huay",
    "cheng tng", "ice kacang", "cendol", "sugarcane juice",
    "mixed vegetable rice", "zhi char", "claypot rice", "thunder tea rice",
    "fishball noodles", "ngoh hiang",
    "dumplings", "dim sum", "you tiao", "fried snacks", "pancake",
    "dessert", "roast meats", "mutton soup", "pig organ soup",
    "herbal soup", "mala", "kueh", "curry puff", "otah", "cuttlefish",
    "steamboat", "hor fun", "la mian", "kolo mee",
    "beer", "juice", "fruit stall", "bakery", "goreng pisang",
    "indian snacks", "spring roll", "curry chicken", "ayam penyet",
    "beef noodle", "turtle soup", "spinach soup", "seafood soup",
    "steamed fish", "bee hoon", "claypot", "fried rice", "mee goreng",
    "kacang pool", "kebab", "pho", "salad", "lu wei", "pao fan",
    "pork rib", "sup tulang", "bakso", "ramen",
]

# Stall postals that do not match the venue postal exactly
# (one-digit differences found 2026-10-01) -> venue slug.
OVERRIDES = {
    "430014": "haig-road-blk-13-14-haig-road-market-and-cooked-food-centre",
    "560162": "ang-mo-kio-ave-4-blk-160-162-mayflower-market",
    "371079": "circuit-road-blk-79-79a",
    "500003": "changi-village-blk-2-and-3",
    "162022": "havelock-road-blk-22a-b-havelock-road-cooked-food-centre",
    "730021": "marsiling-lane-blk-20-21",
    # 642221 = Boon Lay Shopping Centre: not an NEA venue, stays null.
}


def slug(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unnamed-venue"


def toks(s):
    stop = {"and", "the", "of", "blk", "block", "a", "b"}
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in stop and len(w) > 1}


def parse_date(s):
    s = (s or "").strip()
    if not s or s.upper() == "NA":
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def load_venues():
    g = json.loads((DATA / "nea_geojson.json").read_text(encoding="utf-8"))
    venues = []
    for f in g["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        postal = (p.get("ADDRESSPOSTALCODE") or "").strip()
        name = (p.get("NAME") or "").strip()
        street = (p.get("ADDRESSSTREETNAME") or "").strip()
        venues.append({
            "id": slug(name),
            "name": name,
            "address": f"{street}, Singapore {postal}".strip(", "),
            "lat": lat, "lng": lon,
            "rating": None, "rating_count": None,
            "closed": False, "closure_note": None,
            "_postal": postal,
            "_tokens": toks(name),
        })
    return venues


NEW_RAW_FILES = [
    "sfa_within_coffeeshop_raw.json",
    "sfa_coffeeshop_eating_raw.json",
    "sfa_ma_managed_raw.json",
]


def load_kopitiam_venues():
    """Kopitiam/food-court venues geocoded by postal (geocode-kopitiam-venues.py)."""
    path = DATA / "kopitiam_venues.json"
    if not path.exists():
        return []
    out = []
    for v in json.loads(path.read_text(encoding="utf-8"))["venues"]:
        out.append({
            "id": v["id"], "name": v["name"], "address": v["address"],
            "lat": v["lat"], "lng": v["lng"],
            "rating": None, "rating_count": None,
            "closed": False, "closure_note": None,
            "_postal": v["postal"], "_tokens": toks(v["name"]),
        })
    return out


def load_new_stall_ids():
    """Licence ids from the non-NEA pulls; these stalls match venues by
    postal only (never the NEA fuzzy matcher, which was tuned for NEA
    centre-name token overlap)."""
    ids = set()
    for fname in NEW_RAW_FILES:
        path = DATA / fname
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        rows = rows["data"] if isinstance(rows, dict) else rows
        for r in rows:
            lic = (r.get("licenceNumber") or "").strip()
            if lic:
                ids.add(lic)
    return ids


def load_closures():
    """Return {venue-name-key: (closed_today, note)} matched loosely by name."""
    rows = list(csv.DictReader(open(DATA / "nea_closures.csv", encoding="utf-8-sig")))
    out = {}
    for r in rows:
        notes = []
        closed = False
        for q in ("q1", "q2", "q3", "q4", "other_works"):
            s, e = parse_date(r.get(f"{q}_cleaningstartdate" if q != "other_works" else "other_works_startdate")), \
                   parse_date(r.get(f"{q}_cleaningenddate" if q != "other_works" else "other_works_enddate"))
            note = (r.get(f"remarks_{q}") or "").strip()
            if s and e and s <= TODAY <= e:
                closed = True
                label = q.replace("_", " ").upper()
                notes.append(f"{label}: {s:%d %b %Y} to {e:%d %b %Y}" + (f" ({note})" if note and note.upper() != "NA" else ""))
        out[(r.get("name") or "").strip()] = (closed, "; ".join(notes) or None)
    return out


def match_closure(venue, closures):
    vt = toks(venue["name"])
    best, bestscore = None, 0
    for cname, val in closures.items():
        ct = toks(cname)
        score = len(vt & ct)
        # require the venue's distinctive tokens to appear in the closure name
        if score > bestscore and score >= 2:
            best, bestscore = val, score
    return best or (False, None)


def main():
    stalls = json.loads((DATA / "stalls_classified.json").read_text(encoding="utf-8"))
    review = json.loads((DATA / "review_queue.json").read_text(encoding="utf-8"))
    venues = load_venues()
    kvenues = load_kopitiam_venues()
    new_ids = load_new_stall_ids()
    closures = load_closures()

    by_postal = {}
    for v in venues:
        by_postal.setdefault(v["_postal"], v)
    # Kopitiam venues fill postals the NEA register does not claim.
    for v in kvenues:
        by_postal.setdefault(v["_postal"], v)

    # Apply closures to venues.
    n_closed = 0
    for v in venues:
        closed, note = match_closure(v, closures)
        v["closed"], v["closure_note"] = closed, note
        n_closed += closed

    by_id = {v["id"]: v for v in venues + kvenues}
    venue_of = {}

    def fuzzy(address):
        # Shopping centres and coffee shops are not NEA venues: never fuzzy
        # them into a similarly named hawker centre.
        if re.search(r"shopping centre|shopping mall|coffee ?shop|food ?court", address, re.I):
            return None
        at = toks(address)
        best, bestscore = None, 0
        for v in venues:
            score = len(v["_tokens"] & at)
            if score > bestscore:
                best, bestscore = v, score
        return best["id"] if best and bestscore >= 3 else None

    for s in stalls:
        vid = None
        if s["postal"] in OVERRIDES:
            vid = OVERRIDES[s["postal"]]
        elif s["postal"] in by_postal:
            vid = by_postal[s["postal"]]["id"]
        elif s["id"] not in new_ids:
            vid = fuzzy(s["address"])
        s["venue_id"] = vid
        venue_of[s["id"]] = vid

    # Public venue records (internal keys stripped), stable order. NEA
    # venues all ship (some legitimately have zero stalls); kopitiam
    # venues ship only once a stall actually lands in them.
    used_kvenues = {vid for vid in venue_of.values() if vid}
    pub_venues = []
    for v in sorted(venues + [k for k in kvenues if k["id"] in used_kvenues],
                    key=lambda x: x["name"]):
        pub_venues.append({k: v[k] for k in
                           ("id", "name", "address", "lat", "lng", "rating",
                            "rating_count", "closed", "closure_note")})

    # Review queue: attach venue names, order by venue stall count desc.
    size = Counter(venue_of.values())
    for r in review:
        vid = venue_of.get(r["stall_id"])
        r["venue"] = by_id[vid]["name"] if vid and vid in by_id else None
    review.sort(key=lambda r: (-size.get(venue_of.get(r["stall_id"]), 0), r["name"]))
    (DATA / "review_queue.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

    payload = {
        "generated": GENERATED,
        "brand": "HawkerWhere",
        "taxonomy": TAXONOMY,
        "venues": pub_venues,
        "stalls": stalls,
    }
    (DATA / "stalls_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    matched = sum(1 for s in stalls if s["venue_id"])
    print(f"venues: {len(pub_venues)} (closed today: {n_closed})")
    print(f"stalls: {len(stalls)}, matched to venue: {matched} "
          f"({matched/len(stalls):.1%}), unmatched: {len(stalls)-matched}")
    hi = sum(1 for s in stalls if s["dish_confidence"] == "high")
    med = sum(1 for s in stalls if s["dish_confidence"] == "medium")
    un = sum(1 for s in stalls if not s["dish"])
    print(f"dish high {hi} | medium {med} | unclassified {un} | review queue {len(review)}")
    from collections import Counter as C
    print("top unclassified:", C(s["name"] for s in stalls if not s["dish"]).most_common(10))


if __name__ == "__main__":
    main()
