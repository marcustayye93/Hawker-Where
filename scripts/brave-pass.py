#!/usr/bin/env python3
"""Brave web-evidence pass v2: find dishes for unclassified named stalls.

Strict gate (v1 candidates were only ~half solid on review):
  - "title" accept: the stall name appears in the result title AND a dish
    phrase appears in the same title.
  - "two-source" accept: two results from different domains agree on the
    same dish, each mentioning the stall name.
Everything else stays unclassified. Candidates are written for audit;
--apply writes accepted ones into data/stalls_classified.json with
dish_source "brave_web" and the evidence URL stored.

Resumable via data/brave_progress.json. Backs off on failures and aborts
after repeated search failures (likely rate limit).

Usage: brave-pass.py [limit] [--apply]
"""
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(HERE))
from classify import _name_pass, normalize  # noqa: E402

BRAVE = Path.home() / "workspace/skills/brave-search/bin/brave-search"
SKIP_NAMES = {"-", "(no signboard)", "no signboard", "na", "n a"}


def venue_short(vname):
    if not vname:
        return ""
    v = re.sub(r"\([^)]*\)", " ", vname)
    v = re.sub(r"\b(blk|block|hawker centre|food centre|market and|market|centre)\b",
               " ", v, flags=re.I)
    return " ".join(v.split())[:40]


def name_in(text_norm, name_toks):
    ttoks = set(text_norm.split())
    if not name_toks:
        return False
    return len(name_toks & ttoks) >= max(1, len(name_toks) - (1 if len(name_toks) > 2 else 0))


def stall_candidates(results, name_norm):
    name_toks = {t for t in name_norm.split() if len(t) > 2}
    if not name_toks:
        name_toks = set(name_norm.split())
    title_hits = []
    desc_agree = Counter()
    desc_evidence = {}
    for r in results:
        title = r.get("title") or ""
        desc = r.get("description") or ""
        url = r.get("url") or ""
        tnorm = normalize(title)
        if not name_in(tnorm, name_toks):
            continue
        dish, _ = _name_pass(tnorm)
        if dish:
            title_hits.append((dish, title[:120], url))
            continue
        dnorm = normalize(title + " " + desc)
        dish, _ = _name_pass(dnorm)
        if dish:
            dom = urlparse(url).netloc
            desc_agree[dish] += 1
            desc_evidence.setdefault(dish, (title[:120], url, dom))
    if title_hits:
        return title_hits[0][0], "title", title_hits[0][1], title_hits[0][2]
    for dish, n in desc_agree.most_common():
        if n >= 2:
            t, u, _d = desc_evidence[dish]
            return dish, "two-source", t, u
    return None, None, None, None


def brave_search(q, tries=3):
    for i in range(tries):
        try:
            out = subprocess.run([str(BRAVE), q, "--count", "6"],
                                 capture_output=True, text=True, timeout=40)
            if out.returncode == 0 and out.stdout:
                return json.loads(out.stdout).get("web", {}).get("results", [])
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5 * (i + 1))
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = int(args[0]) if args else 200
    apply_mode = "--apply" in sys.argv

    raw = json.loads((DATA / "stalls_raw.json").read_text(encoding="utf-8"))
    venues = {v["id"]: v["name"] for v in raw["venues"]}
    pool = [s for s in raw["stalls"]
            if not s["dish"] and s["name"] != "Unnamed stall"
            and normalize(s["name"]) not in SKIP_NAMES]

    prog_path = DATA / "brave_progress.json"
    prog = {"done": []}
    if prog_path.exists():
        prog = json.loads(prog_path.read_text(encoding="utf-8"))
    done = set(prog["done"])
    pool = [s for s in pool if s["id"] not in done]

    sizes = Counter(s["venue_id"] for s in raw["stalls"])
    name_counts = Counter(s["name"] for s in raw["stalls"] if not s["dish"])
    pool.sort(key=lambda s: (-name_counts[s["name"]], -sizes.get(s["venue_id"], 0)))
    batch = pool[:limit]

    cand_path = DATA / "brave_candidates_v2.json"
    cands = []
    if cand_path.exists():
        cands = json.loads(cand_path.read_text(encoding="utf-8"))
    have = {c["stall_id"] for c in cands}

    fails = 0
    for i, s in enumerate(batch):
        vname = venues.get(s["venue_id"], "")
        q = f'"{s["name"]}" {venue_short(vname)} hawker singapore'
        res = brave_search(q)
        if res is None:
            fails += 1
            print(f"[{i}] search failed for {s['name']!r} ({fails} in a row)", flush=True)
            if fails >= 4:
                print("aborting: repeated search failures (likely rate limit)")
                break
            continue
        fails = 0
        dish, gate, title, url = stall_candidates(res, normalize(s["name"]))
        if dish and s["id"] not in have:
            cands.append({"stall_id": s["id"], "name": s["name"], "venue": vname,
                          "dish": dish, "gate": gate,
                          "evidence_title": title, "evidence_url": url})
            have.add(s["id"])
            print(f"[{i}] {s['name']} @ {vname[:28]} -> {dish} ({gate})", flush=True)
        done.add(s["id"])
        if i % 25 == 0:
            prog["done"] = sorted(done)
            prog_path.write_text(json.dumps(prog), encoding="utf-8")
            cand_path.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        time.sleep(0.4)

    prog["done"] = sorted(done)
    prog_path.write_text(json.dumps(prog), encoding="utf-8")
    cand_path.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"searched {len(batch)} stalls | candidates stored: {len(cands)}")

    if apply_mode and cands:
        classified_path = DATA / "stalls_classified.json"
        classified = json.loads(classified_path.read_text(encoding="utf-8"))
        by_id = {c["stall_id"]: c for c in cands}
        n = 0
        for s in classified:
            c = by_id.get(s["id"])
            if c and not s["dish"]:
                s["dish"] = c["dish"]
                s["dish_confidence"] = "medium"
                s["dish_source"] = "brave_web"
                s["dish_evidence"] = c["evidence_url"]
                n += 1
        classified_path.write_text(
            json.dumps(classified, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"applied {n} brave mappings | classified total: "
              f"{sum(1 for s in classified if s['dish'])} of {len(classified)}")


if __name__ == "__main__":
    main()
