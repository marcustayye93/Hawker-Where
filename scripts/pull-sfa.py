#!/usr/bin/env python3
"""Pull the SFA Track Records register for NEA-managed food stalls.

Verified 2026-10-01: GET https://www.sfa.gov.sg/api/TrackRecord/GetTrackRecord
# - All 8 params must be present as query-string params, otherwise the API
#   returns 404 ("No HTTP resource was found that matches the request URI").
# - At least one search field must be non-empty, otherwise 400 "The request
#   is invalid."
# - isShowLicenceSuspended="false" (not empty) also works and matches the UI
#   default. Form-encoded POST -> 404; JSON POST body -> 404.
# Response wraps records: {"data": [...]}.

Polite: ONE bulk pull with typeOfFoodBussiness="NEA Managed Foodstall".
Idempotent: skips the network pull if data/sfa_raw.json already exists
unless --refresh is passed.
"""
import argparse
import json
import sys
from pathlib import Path

import requests

ENDPOINT = "https://www.sfa.gov.sg/api/TrackRecord/GetTrackRecord"
RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "sfa_raw.json"

PARAMS = {
    "postalCode": "",
    "establishmentAddress": "",
    "licenceNumber": "",
    "businessName": "",
    "licenseeName": "",
    "typeOfFoodBussiness": "NEA Managed Foodstall",  # note the double s
    "isShowLicenceSuspended": "false",  # required non-empty with the others
    "grades": "",
}


def pull():
    headers = {
        "User-Agent": "HawkerWhere/1.0 (research data pull; contact: gethowmuch.net)",
        "Accept": "application/json",
    }
    resp = requests.get(ENDPOINT, params=PARAMS, headers=headers, timeout=90)
    if resp.status_code != 200:
        print(f"query-string GET failed: {resp.status_code}", file=sys.stderr)
        print("falling back to form-encoded POST", file=sys.stderr)
        resp = requests.post(ENDPOINT, data=PARAMS, headers=headers, timeout=90)
    if resp.status_code != 200:
        print(f"form POST failed: {resp.status_code}", file=sys.stderr)
        print("falling back to JSON POST", file=sys.stderr)
        resp = requests.post(ENDPOINT, json=PARAMS, headers=headers, timeout=90)
    resp.raise_for_status()
    return resp.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if RAW_PATH.exists() and not args.refresh:
        payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        data = payload["data"] if isinstance(payload, dict) else payload
        print(f"cached: {RAW_PATH} already exists, skipping pull "
              f"({len(data) if isinstance(data, list) else '?'} records). "
              f"Use --refresh to re-pull.")
    else:
        payload = pull()
        data = payload["data"] if isinstance(payload, dict) else payload
        RAW_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"saved {len(data)} records to {RAW_PATH}")

    if isinstance(data, list):
        print(f"total records: {len(data)}")
        for row in data[:5]:
            print(json.dumps(row, ensure_ascii=False)[:220])
    else:
        print("unexpected payload shape:", type(data), list(data)[:10] if isinstance(data, dict) else "")


if __name__ == "__main__":
    main()
