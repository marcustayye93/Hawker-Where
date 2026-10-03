# HawkerWhere

One dish, every stall, rated.

Pick a dish and see every hawker stall in Singapore that sells it, each
pin carrying its Google star rating. Built for the long tail: every NEA
hawker centre, food court and coffee shop stall in the public register,
not just the famous names.

## Run it

Serve the folder over HTTP (the app fetches its data file, so opening
index.html from disk will fall back to a small sample):

```
python3 -m http.server 8901
```

Then open http://localhost:8901 on a phone or browser.

## How it works

- Stall list: the Singapore Food Agency public Track Records register
  (5,621 NEA managed stalls with unit numbers and SAFE grades).
- Venues: NEA open data (hawker centre locations and closure dates).
- Dish per stall: a name parser against a 93 dish taxonomy, plus
  evidence passes over listing titles and the web. 2,950 of 5,621
  stalls are classified so far (52.5 percent). The rest are waiting on
  the in-app tagging loop: tap a stall, tell us its one specialty.
- Ratings: Google Places ratings cached into data/stalls.json at build
  time. The app itself makes no live Places calls, so it costs nothing
  to run and works offline after the first load.
- Map: MapLibre with OpenFreeMap tiles (free, no API key), rendered in
  neutral greys so the rating pins carry the screen. Pins cluster
  Airbnb style: count badges zoomed out, single rated stalls close in.

## Layout

- index.html, app.js, styles.css: the PWA.
- data/stalls.json: the full stall, venue and rating dataset.
- scripts/: the data pipeline (SFA pull, classifier, venue and
  ratings merges). API access goes through local vault backed CLIs;
  no keys live in this repo.
- BATCH-SUMMARY.md: build notes, honest coverage numbers, and the
  dated addenda for every change since v1.

Data sources: SFA Track Records, NEA open data on data.gov.sg, and
Google Places (ratings cached under the Places terms).
