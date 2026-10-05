#!/usr/bin/env python3
"""Pull the non-NEA SFA Track Records categories for the kopitiam layer.

Same API contract as pull-sfa.py (verified 2026-10-01): GET
https://www.sfa.gov.sg/api/TrackRecord/GetTrackRecord with all 8 params
present, one search field non-empty, isShowLicenceSuspended="false".
Response wraps records: {"data": [...]}.

Writes one raw file per category (never touches data/sfa_raw.json):
  WITHIN A COFFEESHOP/CANTEEN/FOODCOURT          -> sfa_within_coffeeshop_raw.json
  Coffeeshop/Eating house/Canteen/Foodcourt/...  -> sfa_coffeeshop_eating_raw.json
  MA Managed Foodstall                           -> sfa_ma_managed_raw.json

Idempotent: skips a category whose raw file already exists unless
--refresh is passed. Polite: one bulk pull per category.
"""
import argparse
import json
import sys
from pathlib import Path

import requests

ENDPOINT = "https://www.sfa.gov.sg/api/TrackRecord/GetTrackRecord"
DATA = Path(__file__).resolve().parent.parent / "data"

CATEGORIES = [
    ("WITHIN A COFFEESHOP/CANTEEN/FOODCOURT",
     "sfa_within_coffeeshop_raw.json"),
    ("Coffeeshop/Eating house/Canteen/Foodcourt/Canteen within tertiary institution",
     "sfa_coffeeshop_eating_raw.json"),
    ("MA Managed Foodstall",
     "sfa_ma_managed_raw.json"),
]

HEADERS = {
    "User-Agent": "HawkerWhere/1.0 (research data pull; contact: gethowmuch.net)",
    "Accept": "application/json",
}


def pull(food_type):
    params = {
        "postalCode": "",
        "establishmentAddress": "",
        "licenceNumber": "",
        "businessName": "",
        "licenseeName": "",
        "typeOfFoodBussiness": food_type,  # note the double s
        "isShowLicenceSuspended": "false",
        "grades": "",
    }
    resp = requests.get(ENDPOINT, params=params, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    return payload["data"] if isinstance(payload, dict) else payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    total = 0
    for food_type, fname in CATEGORIES:
        path = DATA / fname
        if path.exists() and not args.refresh:
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"cached: {fname} exists ({len(data)} records), skipping")
            total += len(data)
            continue
        data = pull(food_type)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"saved {len(data)} records -> {fname}  [{food_type}]")
        total += len(data)
    print(f"total records across categories: {total}")


if __name__ == "__main__":
    main()
