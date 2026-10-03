# HawkerWhere v1 — Overnight Build Batch Summary

Date: 1–2 Oct 2026 (overnight). Status: BUILT, locally verified. **NOT PUSHED.** No git operations were performed; nothing was deployed. Awaiting Marcus's morning review before anything goes to the `marcustayye93/Hawker-Where` repo.

## What was built

**PWA** (`index.html`, `styles.css`, `app.js`, `manifest.json`, `sw.js`, `favicon.svg`; Leaflet 1.9.4 vendored locally under `vendor/`):
- Dish picker: search input plus chip grid over the approved 45-dish taxonomy.
- Map: Leaflet + OSM tiles, Singapore-centered. Stall pins are **rating badges on the pin itself** (Marcus's direction): the star number on a circle, green for 4.5+, amber for 4.0–4.4, grey below 4.0. Venue-rating fallbacks render hollow/outline; unrated stalls render a small neutral dot. The dish picker drives which pins render; a Stalls/Venues toggle and a "Near me" button are included.
- Stall card (bottom sheet): name, dish, star rating + review count (or a clearly labeled "venue rating" fallback, or "No rating yet"), venue name and address, SAFE hygiene grade, closure status, Google Maps directions link.
- Tagging UI: "Know this stall's specialty? Tell us." opens the taxonomy chips; tags queue in localStorage, capped at 20/day per device. No backend in v1.
- Offline: service worker caches the app shell and `data/stalls.json`. Note: the SW could not be live-tested in this sandbox (this Chrome build blocks localhost navigation), so it needs one live check on the deployed host.

**Data pipeline** (`scripts/`): `pull-sfa.py` (SFA Track Records bulk pull; the 8-field query-param gotcha and the `isShowLicenceSuspended=false` requirement are documented in the script), `classify.py` (name parser against the 45-dish taxonomy + alias map; high/medium confidence; review queue), `merge-venues.py` (NEA GEOJSON + closure dataset join), `merge-places.py` (Google Places rating merge, resumable via checkpoint).

**Data** (`data/`): `sfa_raw.json` (5,621 SFA records), `stalls.json` (final, 5,621 stalls + 129 venues, schema-validated), `review_queue.json` (72 ambiguous names for the human pass), `places_log.json` (exact API counts), NEA GEOJSON + closures.

## Defect investigation (Marcus's "2 stalls" report)

**Root cause: verification-environment artifact, not a rendering bug and not a mid-pipeline partial write.** The app fetches `data/stalls.json` and falls back to `data/sample-stalls.json` (12 stalls, 2 chicken rice) when the fetch fails. The earlier screenshot was captured over `file://`, where Chrome blocks `fetch()` of local JSON, so the fallback silently served sample data. `app.js` renders all filtered matches correctly; nothing was wrong with the filter.

**Fix:** re-captured over HTTP-equivalent conditions against the final merged `stalls.json` (see Repro/verification below). The app behaves identically on GitHub Pages, where `fetch()` works normally. No app code change was needed for this defect.

**Two real pipeline bugs were found and fixed during the re-verification:**
1. `merge-places.py` collected 78 venue ratings but never wrote them into the venue records in `stalls.json` (0/129 venues had ratings). Fixed in the script and backfilled in the data: 78/129 venues now carry ratings.
2. The venue-fallback path set `rating_source="venue"` but left the stall's `rating` null, so fallback stalls rendered as unrated dots and the hollow pin style was unreachable. Fixed in the script and backfilled: 2,464 stalls now inherit their venue's rating, labeled "venue rating". The `rating_source` naming was also normalized (`"google"` → `"stall"`) to match the spec.

## Verification (evidence)

- `verify/10-map-final.png` — **the proof shot**, captured against the final merged data: header "Chicken Rice", **"136 stalls"**, pins showing 4.5/4.6 (green), 4.2/4.4 (amber), hollow venue-fallback pins and grey dots. DOM audit: `live list of 5621 stalls`, 135 pins rendered (136 minus 1 stall with no venue), 93 solid + 17 hollow + 25 dots, zero console errors. (Map tiles did not load in this capture; pins and data are unaffected.)
- `verify/03-map-pins.png` — pin design verification on sample data (solid vs hollow vs dot).
- `verify/01-picker.png`, `02-map.png`, `03-sheet.png`, `04-tag-open.png`, `05-tag-done.png`, `06-venues.png`, `07-rated-sheet.png`, `08-closed-sheet.png`, `09-empty.png` — picker, sheets, tagging flow, venue mode, closed-venue and empty states.
- `verify/VERIFY.md` — full verification notes, including issues found and fixed during the build (`invalidateSize` race, null-rating sort order).
- Console: clean on every captured screen. No em dashes in any user-facing copy.

## Honest classifier coverage (do not oversell)

Of 5,621 stalls, **1,714 (30.5%)** got a dish from name-parsing (1,594 high confidence, 120 medium). **3,907 (69.5%) are unclassified** — their trade names carry no dish signal ("NA" 1,576, "Cooked Food", "Cafe", surnames, Western/BBQ). 41 of 45 taxonomy dishes have at least one stall; **mee siam, murtabak, kueh pie tee, tutu kueh and ice kacang have zero**.

Per-dish counts: kopi and teh 248, drinks 240, mixed vegetable rice 137, chicken rice 136, porridge and congee 106, prawn mee 79, fishball noodles 78, nasi lemak 66, wanton mee 62, fish soup 60, satay 50, carrot cake 50, duck rice 43, yong tau foo 37, bak chor mee 36, tau huay 31, lor mee 23, hokkien mee 21, char kway teow 21, oyster omelette 20, rojak 18, kway chap 17, ban mian 16, nasi briyani 16, bak kut teh 15, laksa 15, chwee kueh 14, nasi padang 10, roti prata 9, popiah 6, sugarcane juice 6, cendol 4, cheng tng 4, zhi char 4, chee cheong fun 3, ngoh hiang 3, claypot rice 3, thunder tea rice 2, thosai 2, putu piring 2, mee rebus 1.

**What this means:** the dish filter is real and useful for the covered dishes, but ~70% of stalls need the tagging loop (or a second signal like tender trade-type data) before they become dish-searchable. The 72-entry `review_queue.json` is the human curation starting point, ordered by venue size. This is the known v1 gap, not a surprise.

## Rating coverage

- 1,555 stalls (27.7%) have stall-level Google ratings.
- 2,464 stalls (43.8%) show their venue's rating, labeled "venue rating".
- 1,602 stalls (28.5%) show "No rating yet".
- 78 of 129 venues have Google ratings.

## Exact Google API consumption

- Build batch: **2,800 Text Searches + 31 Details calls** (cap hit exactly, never exceeded; 2 transient network drops recovered via checkpoint resume).
- Tonight's earlier research: 20 Text Searches.
- October total: ~2,820 / 5,000 Text Searches, 31 / 5,000 Details. Fully inside the free tier. **$0 spent.**
- SFA, NEA and data.gov.sg pulls: free, no quota impact. SFA was queried politely (single bulk pull + the pipeline's refresh design).

## Addendum (2 Oct 2026, Marcus's morning direction)

Two changes since the overnight build:

1. **"Western food" added as a standalone dish category** (taxonomy now 46). Re-classification found 32 western food stalls (e.g. Paris Western Grill, Chef Hainanese Western Food, Vincent Western Food). The ratings merge was re-run so the new category carries Google ratings too.
2. **Unclassified names list generated for Marcus's eyeball pass**: `data/unclassified-names-2026-10-02.md` lists all 2,154 distinct named-but-unclassified stall names (2,300 stalls) with an example venue each, repeat names first. The 1,576 unnamed stalls (SFA "NA") cannot be classified by name and remain tagging-loop work. Marcus will supply categorization rules from the list; each rule folds back into the classifier.

Updated counts after re-classification: 1,745 of 5,621 stalls classified (31.1%), 3,876 unclassified.

## Addendum 2 (2 Oct 2026, Marcus's name-pass rule doc)

Marcus supplied a 95-rule categorization of the whole unclassified list (high = dish in the name, medium = cuisine bucket, low = cooked-food only). Folded into `scripts/classify.py` as an ordered name-pass stage plus a `cuisine` field:

- High rules import as dish tags: 2,561 of 5,621 stalls classified (45.6%), taxonomy now 93 dishes. New dishes include bee hoon, claypot, beef noodle, fried rice, mee goreng, bakery, fruit stall, curry chicken, ayam penyet, kebab, pho, salad, lu wei, bakso, ramen. Secondary hits from a name are stored per stall.
- Medium rules import as a `cuisine` bucket on 1,284 stalls (Thai, Malay / Muslim, Indian, Seafood, Cafe, etc.). The app does not display cuisine yet; the data is in place for a filter decision.
- Low is not imported; the 809 no-signal names stay unclassified.
- Ratings merge re-ran with zero new Places searches (all named stalls were already searched): 2,330 stall-level ratings, 1,997 venue fallback, 1,294 unrated. October usage unchanged at 4,174 of 5,000.
- Regression check: 74 stalls gained a dish, 0 lost one; 16 dish changes, all toward Marcus's assignments.
- Deviations awaiting his veto: xiao long bao stays dumplings (not dim sum), kueh stays separate from dessert, bak kut teh stays its own dish, mala stays its own dish, char siew / BBQ pork noodle is labelled wanton mee, mee soto and lontong sit under mee rebus.
- Remaining unclassified: 1,397 distinct names (mostly person names with no dish word) plus the 1,576 unnamed stalls. List refreshed at `data/unclassified-names-2026-10-02.md`.

## Addendum 3 (2 Oct 2026, investigation into the unclassified residue)

Three more evidence passes over the named unclassified stalls:

- Internal transfers: same trade name classified elsewhere (1) and same SFA licensee with a single-dish record (47).
- Google title harvest: 826 Places searches (October free tier now exactly 5,000). 126 stalls pinned from listing titles. Total October Places: 5,000 of 5,000, $0 spent.
- Brave web pass (strict gate: stall name and dish in the same result title, or two agreeing sources): searched 1,298 stalls, 187 mappings applied.
- Grok batch (Marcus ran it): 22 of the 555 listed stalls researched. Spot checks verified live (Singapore Foodie carrot cake, Miss Tam Chiak mee rebus). Applied 13 dishes and 3 cuisine tags; one unit-only match held back as provisional (`data/grok_provisional.json`).

Coverage now: 2,935 of 5,621 stalls classified (52.2%); ratings unchanged (2,330 stall-level, 1,997 venue fallback). Remaining: 1,110 named stalls + 1,576 unnamed. A run-once cron (hawkerwhere-titles-nov1, 1 Nov 09:15 SGT) holds the remaining title searches for the November quota reset. Nothing pushed.

## Addendum 4 (2 Oct 2026, Grok batch 2)

Batch 2 came back with 23 new researched rows plus Google Maps updates to five earlier ones. Same treatment: IDs checked, two more sources verified live (DanielFoodDiary on Tian Nan Xing bak chor mee; Miss Tam Chiak on Happiness fish soup). Applied 15 dishes (kolo mee x2, herbal soup x2, mixed vegetable rice x2, fried snacks, bakery, duck rice, western, mee siam, bak chor mee, thunder tea rice, fish soup, zhi char) and 2 new cuisine tags. Grok refused to force Hakka Noodle (Ipoh Zai) into bak chor mee; left unmapped, correct call. Grandma Mee Sua mapped to mee siam on a same-unit OpenRice listing despite the name difference; flagged for Marcus's veto.

Coverage: 2,950 of 5,621 (52.5%). Marcus stopped the classification push here on 2 Oct: 52.5% is enough for v1. Remaining: 1,095 named stalls + 1,576 unnamed, left to the 1 Nov Places title run and the app tagging loop. Nothing pushed.

## Addendum 6 (2 Oct 2026, Airbnb restyle + clustering)

Per Marcus: islands of rating circles were illegible, so the map now works like Airbnb. Zoomed out, stalls collapse into black count badges (red when 100 or more); tapping a badge flies in and splits it, and close-in the badges resolve into white rating pills (red star plus the Google number). Same venues jitter apart so individual stalls are tappable at street level. Full visual restyle to his red and white: white surfaces, near-black text, Airbnb red #ff385c accent, pill search, quiet cards. The yellow is gone from CSS, manifest, theme color and favicon; tagline updated to "One dish, every stall, rated." Basemap is stock OpenStreetMap (a pale CARTO test in the sandbox served API-key watermark tiles, so it was dropped). Marcus then asked for a much simpler map: the street detail is now washed to faint grey lines under the pins (same OSM tiles, muted via CSS), so the map reads as a plain 2D backdrop and ratings carry the screen. Verified live in a browser with real tiles: 150 chicken rice stalls open as 4 clusters, split stage by stage to 35 single rated pins downtown, and the stall sheet opens clean. The map is fully legible now; nothing pushed.

## Addendum 7 (3 Oct 2026, simple Google-style map)

Marcus sent a Google Maps screenshot as the target look. The washed OSM raster was not it, so the map engine swapped from Leaflet raster tiles to MapLibre GL with OpenFreeMap vector tiles (free, no API key), styled to the clean phone-map look: pale land, soft green parks, blue water, plain roads. Detail layers stripped at load (POI icons, shields, one-way arrows, 3D buildings). Two porting bugs found and fixed on the way: MapLibre takes one event type per listener (the Leaflet-style "zoomend moveend" registration silently never fired, freezing clusters), and animated camera moves stall when a tile source is still loading, so cluster taps now use instant jumpTo with a guaranteed zoom step. Verified live: 150 chicken rice stalls open as 6 clusters, split through 18, then 37, reaching 69 single rated pins around Chinatown and Maxwell. Directions still hand off to Google Maps. Nothing pushed.

The v1 PWA from the overnight build was re-verified against the final 52.5% dataset: 93 dish chips, 5,621 stalls loaded, chicken rice shows 149 pins and 150 stalls, stall sheet opens with Google rating, review count, SAFE grade, closure status and directions link. Two fixes made during verification: the search placeholder now reads the live dish count instead of the stale 45, and the result list ranks by a Bayesian-weighted rating (a 5.0 from 3 reviews no longer beats a 4.8 from 76; pins still show the true Google number). Map tiles do not load inside this VM sandbox (OSM needs the egress proxy); pins and UI verified, tiles are stock OSM and load on a real device. Service worker still needs one live check on the deployed host. Awaiting Marcus's push approval for marcustayye93/Hawker-Where plus GitHub Pages.

## What needs Marcus's eye in the morning

1. **The whole batch** — approve (or reject) pushing to `marcustayye93/Hawker-Where` and enabling GitHub Pages. Nothing has been pushed.
2. **Coverage honesty check** — 30.5% dish coverage at v1. Decide: ship with the tagging loop as the growth engine, or delay for a second classification signal first.
3. **Tagline** — the PWA header reads "Find your number. One dish, every stall." ("Find your number" is GetHowMuch language; may want a HawkerWhere-native line.)
4. **The 5 zero-count dishes** (mee siam, murtabak, kueh pie tee, tutu kueh, ice kacang) — seed manually or leave for tagging.
5. **Service worker** — needs one live offline check on the deployed host (could not be tested in this sandbox).
6. **v1.1** — non-NEA food-business types in the SFA API (food courts, kopitiams) are still unchecked; the script takes the type as a parameter when he wants it.

## Addendum 3 (2 Oct 2026, Brave v2 pass hit its October cap)

- Brave Search API emailed at 17:36 SGT that usage had crossed 50% of the $5 free-credit limit ($3.15 used), then at 17:46 SGT that the enforced limit was reached ($5.00 used). Additional Brave calls may be rejected until the limit is raised or the billing period resets.
- The strict Brave v2 pass aborted after repeated search failures, exactly as designed. It had stored 187 venue-specific mappings, which were applied to `data/stalls_classified.json`.
- Local merge completed with no new Google Places searches (`MERGE_MAX_SEARCHES=4174`): `data/stalls.json` now carries 2,922 of 5,621 stalls classified (52.0%), up from 2,735 (48.7%). Rating coverage is unchanged: 2,330 stall-level ratings in the progress log, 1,997 venue-fallback stalls, 1,294 unrated.
- Remaining unclassified: 2,699 stalls, comprising 1,576 unnamed stalls for the tagging loop and 1,123 named stalls (1,075 distinct names). The refreshed list is `data/unclassified-names-2026-10-02.md`.
- Recommendation: SKIP raising the Brave limit now. Marcus already set a stay-free boundary for HawkerWhere. Keep the 1 November quota-reset work, and only pay for Brave overage if he wants the remaining named-stall pass finished before November. Nothing has been pushed.

## Addendum 8 (3 Oct 2026, map must carry no colour)

Marcus opened the Addendum 7 screenshots full-size: the basemap was coloured (yellow roads, blue water, green parks), which he rejected. The thumbnails had only looked clean at small size.

Fix: OpenFreeMap liberty out, positron in. Every basemap layer is recoloured to neutral greys on load (water, parks, buildings, labels), road shields and the airport symbol are hidden, and the map canvas is rendered grayscale so no tile colour can show through. Pins, cluster badges and the red UI keep their colour; those are app elements, not the map. Service worker cache bumped to hawkerwhere-v3.

Verified live in headless Chrome with real tiles: 93 dishes over 5,621 stalls, 150 chicken rice stalls opening as 6 clusters plus 1 single, splitting through 18 and 37 groups to 32 clusters plus 69 single rated pins around Chinatown and Maxwell, stall sheet opens, zero console errors. Pixel check on the map area of the new screenshots: colour channel spread ~0. Screenshots: verify/12-map-v1.png (island) and verify/16-map-zoom3.png (street). Nothing pushed.

Note (3 Oct, later): Marcus re-opened a proof screenshot and still saw the coloured Leaflet map. The image in his screenshot carries the old "Leaflet | OpenStreetMap contributors" attribution, so he was viewing the pre-switch screenshot, not the new grey one (the reused screenshot filenames let the client serve the older cached image). Proof screenshots now go out under fresh filenames (17-map-grey-island.png, 18-map-grey-street.png); the new map's attribution reads "OpenFreeMap". Rule going forward: never reuse a screenshot filename when sending Marcus a revised proof.
