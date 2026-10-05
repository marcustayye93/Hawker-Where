#!/usr/bin/env python3
"""Regenerate data/taxonomy.json from data/stalls.json.

The app fetches this light file first so the landing page and dish
suggestions work while the full payload loads. Run after any payload
regeneration (merge-places.py), before pushing.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def main():
    with open(os.path.join(DATA, "stalls.json")) as f:
        d = json.load(f)
    t = {
        "dishes": d["taxonomy"],
        "stall_count": len(d["stalls"]),
        "venue_count": len(d["venues"]),
        "generated": d.get("generated"),
    }
    out = os.path.join(DATA, "taxonomy.json")
    with open(out, "w") as f:
        json.dump(t, f, separators=(",", ":"))
    print("wrote", out, len(t["dishes"]), "dishes")


if __name__ == "__main__":
    main()
