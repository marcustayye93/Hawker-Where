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

## Addendum 9 (3 Oct 2026, pushed to GitHub)

Marcus approved the push ("beautiful okay push it to GitHub"). Jev done-gate ran first: PASS (scope_match complete 1.93, confidence 0.89, threshold 0.8).

Pushed to marcustayye93/Hawker-Where (public, was empty): commit ea1b5e80 on main, "HawkerWhere v1: dish-first hawker map with cached Google ratings", on top of the Contents API seed commit 72c5d78a. 19 files, 3.2 MB: app shell, vendor/maplibre, data/stalls.json plus the sample fallback, scripts/ pipeline, README.md, this summary. Excluded as agreed in the change doc: vendor/leaflet, verify/ harness and screenshots, data backups and progress files, pipeline logs.

Verified after the push through the GitHub API: the recursive tree lists all 19 files with the right sizes, and the README serves from raw.githubusercontent.com. GitHub Pages is NOT enabled (the check returns an error and the Pages URL 404s); enabling it is Marcus's manual Settings tap, and the service worker offline check is owed once the site is live.

## Addendum 10 (3 Oct 2026, live on hawkerwhere.com)

Marcus enabled GitHub Pages (main, root) and the DNS was already in place. His Settings custom-domain entry did not persist (the Pages API showed cname null and hawkerwhere.com returned GitHub's "Site not found"), so the domain was claimed by pushing a CNAME file instead (commit 330a70c5), the same mechanism the Pages UI uses. GitHub built it, claimed hawkerwhere.com, and the certificate state reached approved (expires 1 Jan 2027).

Verified live on the real host, in a real browser, against both marcustayye93.github.io/Hawker-Where and https://hawkerwhere.com/: 93 dish chips, live list of 5,621 stalls, chicken rice opens as 6 clusters plus 1 single with 150 stalls, stall sheet opens (Leng Heng 4.8, 76 reviews), zero console errors. The owed service worker check is now done: the worker registers, caches 10 shell and data entries, and the app reloads fully offline with all 93 dishes. HTTPS answers 200 on the apex and www redirects to it; http is not yet redirected (GitHub's Enforce HTTPS flag is still off while the certificate settles).

## Addendum 11 (3 Oct 2026, search + location batch pushed live)

Marcus replaced the picker: landing is now one search bar under "What food are you looking to eat?" with live dish-name suggestions as the user types. Location fires only when Near me is tapped, which drops the blue dot and centres the map on the user. His three trims all held: no suggestion stall counts, no nearest-first sorting (the list keeps its weighted-rating order), and no automatic location prompt on dish pick. Jev done-gate flagged scope creep through the review rounds (0.93, then 0.89, then 0.55 after each trim); Marcus reviewed the flagged extras and approved the final batch as is.

Pushed as commit 3abde882 (index.html, app.js, styles.css, sw.js with cache hawkerwhere-v4). Verified live on https://hawkerwhere.com/ afterward: clean landing, "chick" suggests chicken rice and curry chicken, no dot before the Near me tap, dot and centring after it, list stays in rating order, service worker v4 caches and reloads offline, zero console errors.

## Addendum 13 (3 Oct 2026, Bib matching extended, local only)

- Marcus asked to retry the 13 unmatched Bib Gourmand names. 8 matched by verified unit number: Beach Road Fish Head Bee Hoon (Blk 91 #01-46), Singapore Fried Hokkien Mee (Blk 90 #01-32), Cheok Kee (Geylang Bahru #01-35), Hui Wei Chilli Ban Mian (#01-58), Spinach Soup (#01-12), Dudu Cooked Food (Jurong West 505 #01-19), Jian Bo Tiong Bahru Shui Kueh (#01-27), Yong Chun Wan Ton Noodle (115 Bukit Merah View #01-56). Tab now 61 establishments / 68 stall records.
- Not matched, honestly: Na Na Curry and Yi Pin Wei (register lists a different named stall at the cited unit), Boon Keng Road Fish Head Bee Hoon (operates from a Bedok kopitiam, outside the NEA register), Hai Nan Zai and Ji De Lai (Chong Pang has no stalls in the register).
- Where Michelin's specialty maps to a taxonomy dish and the stall had none, dish set from the Bib evidence (fish soup, hokkien mee, duck rice, ban mian, kueh x2, wanton mee); Spinach Soup left dishless. apply-bib.py now does this. Verified: 68 cards, A Noodle Story sheet flow, zero real errors. Still NOT pushed; gate still FLAG (creep 0.90).

## Addendum 14 (5 Oct 2026, saved stalls + HeyNemo borrows, local only)

- Marcus reviewed the CheapFoodMap and HeyNemo teardowns (Firecrawl scrape + Grok independent pass). Adopted: saved stalls (big add button repurposed to store selected stalls; localStorage, on-device), shareable ?dish=/?stall= links, pin-above-sheet offset, cluster tap overshoot +0.25. Rejected by Marcus: freshness dates. Also rejected: HeyNemo 3D tilt (violates his simple 2D rule) and its 25-layer system; no React replatform.
- Verified (verify/verify_saved_links.py, verify/verify_cant_decide.py): save persists across reload, deep links land, Bib flow clean, zero errors. sw cache hawkerwhere-v6.
- Jev done-gate: FLAG (creep 0.97) - the Can't Decide batch keeps accreting features Marcus did not name in the original ask (saved + links + offsets are his calls from 4 Oct, but outside the gate's original spec). Awaiting his push call; still NOT pushed.

## Addendum 15 (5 Oct 2026, Can't Decide batch PUSHED LIVE)

- Marcus approved ("push the big Gorman 61 establishments"; Author's Pick content deferred to a later push, placeholder tab ships). Commit 2be601af on main: index.html, app.js, styles.css, sw.js (hawkerwhere-v6), data/stalls.json (68 bib-flagged records), data/bib_gourmand.json, scripts/apply-bib.py, scripts/match-bib-gourmand.py.
- Verified live on https://hawkerwhere.com/ (verify/verify_saved_links.py with HW_PAGE): landing saved button, Bib sheet flow, save persists, ?stall= and ?dish=laksa deep links, 34 laksa stalls, zero errors.
- Follow-up already built locally, awaiting his push call: headline "Find your food in Singapore" + centred picker-meta (index.html/styles.css, sw hawkerwhere-v7), verified on the capture build.
- The 5 unmapped Bib hawkers stay off the tab honestly; two unit-conflict names retry during the Nov 1 harvest, the kopitiam one waits for v1.1, the two Chong Pang names wait for register records.

## Addendum 16 (5 Oct 2026, headline + restyle PUSHED LIVE)

- Headline batch: commit 49b6b5c2 ("Find your food in Singapore", centred headline + meta, sw v7). Gate FLAG (creep 0.86); Marcus ordered the push anyway. Verified live on hawkerwhere.com (h1 centred, zero exceptions).
- Restyle batch: Marcus sent his Stock Research Tool screenshot as the reference: serif display headlines (Iowan Old Style/Georgia stack) + system sans, angular buttons (12px), search bar 14px, cards 12px; choices (Stalls/Venues, Bib/Author's Pick) are borderless tabs with a 2px red underline; map pins/clusters stay round. Commit 02ff2d2d, sw v8. Gate FLAG (partial 1.45, creep 0.69); Marcus approved after seeing the capture screenshot. Verified live (serif h1, red tab underline, 12px saved button); first load after push serves the old SW shell once, then v8 takes over.

## Addendum 17 (5 Oct 2026, tagline + Bib regions PUSHED LIVE)

- Commit 0342c021: tagline "Your local dish companion" + Bib Gourmand region filter (All/North/South/East/West/Central tabs under the Bib tab; regionOf() coordinate buckets in app.js; hidden on Author's Pick; empty region message). sw hawkerwhere-v10. Gate FLAG (creep 0.77, complete 1.96); Marcus approved on the screenshot.
- Region distribution (records/establishments): central 47/42, west 9/8, south 8/8, east 4/3, north 0. Verified live on hawkerwhere.com with a clean browser profile: new tagline, 6 region tabs, West filter shows 9 cards with "(West)" note, zero exceptions. Note: the returning-visitor service worker serves the old shell for one load after each push; documented pattern since v8.
- Harness notes from this session: copying app files into verify/capture/ wipes BOTH capture patches (data-inline script tag AND the loadData boot patch); re-apply both after every copy. The proxy relay (127.0.0.1:8899) can wedge with a stale upstream; kill the listener pid and restart proxy_relay.py.

## Addendum 18 (5 Oct 2026, Grok audit fixes PUSHED LIVE)

- Grok deep audit (Marcus's request): 56/100, verdict KEEP. Full text in ~/workspace/roundtable/sessions/2026-10-05-hawkerwhere-grok-audit/. Boiny verified each claim against the code before implementing; two corrections surfaced: the venue review-count was already capped at 10 in the sort, and the sheet already labels evidence + "venue rating".
- Commit c7af8fc4: app.js, index.html, styles.css, sw.js (v12), data/taxonomy.json, scripts/make-taxonomy.py, scripts/gen-dish-pages.py, 90 dish pages, sitemap.xml (91 URLs), robots.txt. Gate FLAG (creep 0.76); Marcus approved.
- Live-verified on hawkerwhere.com (clean load + relay): landing meta, Maxwell venue search (100 stalls incl. untagged), venue view, dish page 200 with correct title, zero exceptions.
- Declined from Grok's list (recorded in gate change doc): deleting Author's Pick placeholder, clipboard tag export, rating cache dates (owner rejected freshness dates), live search/3D/accounts.
- Nov 1 cron note: after merge-places.py regenerates the payload, rerun scripts/make-taxonomy.py AND scripts/gen-dish-pages.py AND apply-bib.py, or the new files silently go stale.

## Addendum 19 (5 Oct 2026, hokkien-name fix PUSHED LIVE)

- Trigger: Marcus at Ang Mo Kio 628 found Sumo Fried Hokkien Prawn Mee "missing". Root cause: register trade name is the plain "Fried Hokkien Prawn Noodle" (no Sumo branding anywhere in the SFA record) and the name parser had the stall under prawn mee. 18 stalls with "Hokkien" in the name sat under prawn mee.
- Commit 9f5033b9 (Marcus approved): 17 stalls flipped to hokkien mee via data/corrections.json + scripts/apply-corrections.py (idempotent; run after apply-bib.py on every payload regeneration; also added to the Nov 1 cron body). Deliberately NOT flipped: The Old Stall Hokkien Street Famous Prawn Mee (Hong Lim #02-67) - verified soup hae mee (1943 lineage), reason recorded in corrections.json. Sumo Big Prawn #01-72 untouched: Marcus confirmed it closed and Imperial Fish Soup replaced it, register current.
- AM80176003 renamed "Sumo Fried Hokkien Prawn Mee", also: carrot cake, oyster omelette, dish_source "correction" (app.js gains the sentence "Dish corrected from local evidence."). classify.py name-pass rule order fixed (hokkien before prawn). sw v13. Dish pages regenerated.
- Live-verified 6 Oct: hokkien mee = 90 stalls on the 16,073-stall payload (the kopitiam import merged later on 5 Oct and carried the corrections; live blob sha matches local), "sumo" suggests the stall, zero exceptions. Gate FLAG (creep 0.68), disclosed before push.
- Open judgment call for Marcus: BL201163003 "Penang Hokkien Noodle" stays hokkien mee (Penang hokkien mee is strictly soup-style; no stall-level evidence; no silent flip).

## Addendum 20 (7 Oct 2026, landing map teaser + red-N fix PUSHED LIVE)

- Commit 2655b4c0 (Marcus approved): landing gains a clickable mini-map (second non-interactive MapLibre instance, grey, smaller cluster badges, zoomed to the island; tap focuses the search bar); the .r-rating::first-letter CSS that painted the "N" of "No rating yet" red is gone (star is now a .star span; only the star is red); Adam Rd Noo Cheng Big Prawn Noodle (ADF0127003) renamed from Michelin's listing + dished prawn mee via corrections.json (18 entries); payload/dish pages/taxonomy regenerated; sw v14.
- Live-verified: landing badges render (16 at island zoom), zero exceptions.
- Desktop layout built in the same session (CSS-only, @media 900px: two-pane map, 400px sheet card, 880px landing) and presented separately, gate FLAG creep 0.55.

## Addendum 21 (8 Oct 2026, Author's Pick listings PUSHED LIVE)

- Pushed 8 Oct 2026 on Marcus's approval: commit 0bf52a7e on main, sw hawkerwhere-v16. Live-verified on hawkerwhere.com: sw.js serves v16, live payload carries the 5 author picks, hokkien mee dish page reads 91 stalls, Author's Pick tab renders the grouped list in a clean browser with zero console errors.

- Marcus supplied Author's Pick names: Neighbourwok (Hokkien Mee), Lazy Lizard (Western food), Pietro Pizza (Italian food), Dong Bei Ren Jia (China food), then added Wee Kim Hainanese Chicken Rice at Yishun Park Hawker Centre. Built as specific or flagship locations: The Neighbourwok at Bukit Batok, Lazy Lizard Sixth Avenue, Pietro Ristorante Italiano, Dong Bei Ren Jia, and Wee Kim at Yishun Park Hawker Centre #01-32.
- Author's Pick now groups by region headings (North, South, East, West, Central) with the cuisine as a red sub-label on each card. Cards open the place itself, not the whole dish category. Manual non-register places are marked author_manual, so the headline register count stays 16,073 and generated dish pages stay register-based.
- Durable route: data/authors_picks.json + scripts/apply-authors-picks.py, run after apply-corrections.py and before make-taxonomy.py/gen-dish-pages.py. The Nov 1 cron body now includes that step. DONG BEI CAI at People's Park Food Centre is deliberately not flagged as Dong Bei Ren Jia.
- Verified locally on the capture build: Author heads North/West/Central, 5 cards with cuisine labels, Wee Kim and Pietro sheets open correctly, Bib flow and saved/deep-link suite pass, zero page errors in verify_cant_decide.py. sw hawkerwhere-v16.

## Addendum 22 (9 Oct 2026, self-healing updates PUSHED LIVE)

- Trigger: Marcus reported zooming the map never updated the stall list on his phone. Reproduced on the live site first (phone-size emulation): zoom buttons, cluster taps and pinch all narrowed the list correctly ("40 stalls" to "4 of 40" etc.), zero errors, and live app.js contained syncListToViewport. The list logic was never broken.
- Root cause: delivery. A page keeps running the app.js it loaded with; clients.claim() swaps the controller, not the running script, and data is network-first so the app looks current. On a rarely-closed iPhone PWA the running code stayed pre-v15 indefinitely, so no moveend listener existed. There was no mechanism to reload a stale page onto a fresh shell.
- Commit 843e63aa (Marcus approved): sw hawkerwhere-v17 force-reloads open pages onto the fresh shell when an upgrade activates (first installs excluded, so first-time visitors are not bounced); app.js checks for updates on foreground return and reloads once if a new worker takes control mid-session. No data changes.
- Live upgrade proof (the step the local sim could not run, Chrome loopback blocked): a browser page was held open on v16 ("40 stalls", cache hawkerwhere-v16); after deploy, an update check made the page reload itself in about 11s onto v17, and the zoom test then narrowed to "4 of 40 stalls in this view", zero exceptions. Screenshot verify/44-healed-live-zoom.png.
- Done gate FLAG again (scope complete 1.52, creep 0.37, blocker 0.35, confidence 0.30): Jev low-confidence because the fix does not touch list code, which was the correct call. Marcus approved the push.

## Addendum 23 (10 Oct 2026, Author's Pick +3 PUSHED LIVE)

- Marcus added three picks (2026-10-10): "tai Hwa bachormee", "Leng Bak Kut Teh", and "Jiao cai seafood for bbq seafood". Resolved against the register: Hill Street Tai Hwa Pork Noodle (W84231K002, 465 Crawford Lane #01-12, previously untagged, now dish bak chor mee via dish_source author_pick, cuisine label "Bak chor mee"); Jiao Cai Seafood (SJHC0214001, Senja Hawker Centre #02-14, venue rating 4.1, tagged zhi char, label "BBQ seafood"; Senja is the brand's outlet from the Yishun Park original, he picked the name-matched stall, Yishun alternative flagged). "Leng Bak Kut Teh" matched nothing; offered Leong Kee (Klang) vs Legendary Rangoon Road, Marcus tapped "Push these two, add Leong Kee (Klang) too", so E90054A001 Leong Kee (Klang) Bak Kut Teh (251 Geylang Road, already tagged bak kut teh, label "Bak kut teh") joined too. Its duplicate company record stays unflagged. Central group now 6, total picks 8. Jev gate FLAG (scope partial 1.35, creep 0.66, confidence 0.47) on the unresolved Leng question; disclosed, Marcus ruled, pushed on his tap.
- Commit 519550378, sw hawkerwhere-v18 (push message says +2; the batch carries all three picks because Leong Kee was added before the push). Pushed: authors_picks.json, stalls.json, taxonomy.json, bak chor mee + zhi char dish pages, sw.js.
- Verified live: sw v18, Author's Pick renders 8 cards (North 1, West 1, Central 6) with cuisine labels, zero exceptions. Screenshots: 45 (capture 7-card), 48 (Leong Kee sheet), 49 (live 8-card).

## Addendum 24 (10 Oct 2026, Author's Pick +2 Wisma Atria PUSHED LIVE)

- Marcus at Wisma Atria added two Food Republic stalls (2026-10-10): a Korean stall and Hot Hot Pot (mala), neither in the SFA register (the Wisma Atria venue holds 6 register records), exactly as he suspected his database was behind. Both went in as author_manual records. The Korean stall's signboard (his photo) literally reads "KOREAN HOMESTYLE BEAK BAN", which matched his words exactly, so his spelling stands: "Korean Homestyle Beak Ban", label "Korea food", no dish tag (no Korean dish exists, same as Pietro). Hot Hot Pot: label "Mala", dish mala (his pick is the evidence). Both attach to the existing Wisma Atria venue record. apply-authors-picks.py gained a backward-compatible venue_ref branch for manual stalls inside registered venues. Jev FLAG (creep 0.59 on the script generalization + mala tag; scope complete 1.98, confidence 0.97), disclosed, Marcus tapped "Push the two Wisma Atria picks".
- Commit e17ad9b6, sw hawkerwhere-v19. Pushed: authors_picks.json, stalls.json, scripts/apply-authors-picks.py, sw.js. Payload 16,078 records / 1,553 venues, register count still 16,073.
- Verified live: sw v19, Author's Pick renders 10 cards (North 1, West 1, Central 8) with correct labels, zero exceptions. Screenshots: 50 (capture 10-card), 51 (Beak Ban sheet), 52 (Hot Hot Pot sheet).
- Follow-ups Marcus raised right after the push (same evening, built locally, push pending his call): an intro line at the top of the Author's Pick list in his voice; renaming the Korean stall to Jangsan Korean Cuisine (menu header "JANG SAN KOREAN CUISINE", Stall 15) with the homestyle name kept visible; and adding their Clementi outlet (NEWest, 1 West Coast Drive #01-107, the brand's original; coords 1.31641, 103.75745, Central by the app's region rules).

## Addendum 25 (11 Oct 2026, Author's Pick intro line + Jangsan PUSHED LIVE)

- Gate PASS this time (scope complete 1.95, confidence 0.93). Marcus tapped "Push the intro line and the two Jangsan entries".
- Intro line at the top of the Author's Pick list (app.js renderInspire + .inspire-intro in styles.css): "Every pick here is food I stand behind. Not the tourist-famous names, just food that truly hits the spot for me, and I am glad to share it." Rephrased from his words of 2026-10-10.
- Jangsan: the Wisma Atria Korean stall renamed to "Jangsan Korean Cuisine (Korean Homestyle Beak Ban)" (Jangsan primary, homestyle name kept visible per his instruction; unit #04-15 from his menu photo) and the Clementi outlet added at NEWest, 1 West Coast Drive #01-107, Singapore 128020 (OneMap coords 1.31641, 103.75745; Central under the app's region rules). 11 picks, payload 16,079 records / 1,554 venues, register count still 16,073.
- Commit 27d477f8, sw hawkerwhere-v20. Pushed: app.js, styles.css, authors_picks.json, stalls.json, sw.js.
- Verified live: sw v20, 11 cards with both Jangsan entries, zero exceptions; live app.js carries the intro line. Screenshot: 53 (capture, intro + list).

## Addendum 26 (11 Oct 2026, Meta Pixel + privacy page PUSHED LIVE)

- Pre-launch batch for the first Meta ads campaign (adopted modified plan, 2026-10-11): Meta Pixel installed on the site and a privacy notice page added. Dataset "HawkerWhere" (ID 1628915405255644) created by Marcus in Events Manager and verified via the Ads API in the gethowmuch business before the push.
- index.html: pixel base code verbatim in head (fbq init + PageView + noscript) and a small Privacy footer link at the bottom of the picker screen. privacy.html: new page with the notice text (no accounts, anonymous usage data, Near me location stays on device, Meta Pixel disclosure, no data sale), dated 11 October 2026. sw.js: cache hawkerwhere-v21, privacy.html added to the shell. app.js and styles.css untouched.
- Verified locally on the capture build before the push: app boots with full data, fbq loads, pixel script present, Privacy link in the rendered page, zero exceptions; privacy page rendered in brand style.
- Jev gate FLAG on a confidence dip (scope complete 1.86-1.97 across runs, creep 0.12, blocker 0.19; second run confidence 0.78 against the 0.8 line). Disclosed to Marcus; he tapped "Push the pixel batch".

## Addendum 27 (11 Oct 2026, facebook-domain-verification tag PUSHED LIVE)

- Marcus supplied the exact meta tag from Meta Business Settings and asked for it to be added: facebook-domain-verification, content g3ihc3z2lo0jjfljq3w5v0xksk2n4u, inserted in the index.html head. sw.js bumped to hawkerwhere-v22 (the standing shell-change mechanism). Nothing else changed.
- Jev gate FLAG (creep 0.94): the scorer read the service worker bump as creep because the spec text omitted it. Disclosed to Marcus as a spec-wording miss; he tapped "Push the domain verification tag".

## Addendum 28 (2026-10-11): ViewContent search event for the Meta Pixel

- app.js: a guarded trackSearch() helper fires fbq('track', 'ViewContent', {content_name, content_type, content_category: 'search'}) at the three search-selection points in renderSuggestions: a dish pick (type 'dish'), a place pick (type 'venue'), and a stall pick (type 'stall'). The Enter key path clicks the first suggestion, so it is covered by the same handlers. Deep links, map browsing and saved stalls do not fire it: the event means "the user searched and chose a result".
- sw.js: cache bumped to hawkerwhere-v23 (app.js is in the shell).
- index.html unchanged (the pixel base code from Addendum 26 already loads fbq on every page).
- Verified on the capture build (file://, full payload): three simulated searches each produced exactly one ViewContent call with the expected parameters (dish 'laksa'; venue 'Maxwell Food Centre (Kim Hua Market)'; stall 'Tian Tian Xiang'), and the run had zero JS exceptions.
- Purpose: the event gives the HawkerWhere dataset a deeper optimisation and audience signal than PageView alone, per the campaign plan discussion on 2026-10-11.

## Addendum 29 (2026-10-20): venue-inherited ratings present as unrated (option A)

- Trigger: user feedback that every stall at Pasir Ris Central Hawker Centre shows 4.1 stars. Root cause (verified in data): merge-places.py fetches one Google rating per venue, then stamps every stall lacking an individual rating with the venue's rating and review count (rating_source "venue"). At Pasir Ris Central all 31 stalls carry the centre's own 4.1 (2,161 reviews); island-wide 2,561 of 4,891 rated stalls (52%) hold an inherited number across 74 venues.
- Marcus chose option A (full display fix) on 2026-10-20.
- app.js: ratingLine() returns "No rating yet" for rating_source "venue" (covers result list, picker lists, Author's Picks, saved list and the stall sheet, which all funnel through it); sortKey() ranks venue-sourced stalls with the unrated tier; the result list no longer inserts the "Centre ratings below" note; stall map pins for venue-sourced stalls render as no-rating pins. Venue-mode pins are untouched: a centre's own pin still shows its own rating.
- scripts/gen-dish-pages.py: weight() and rating_text() apply the same rule; the page subtitle no longer claims centre ratings are labelled. All 88 dish pages regenerated; no "venue rating" or "centre rating" string remains in app.js or dish/.
- sw.js: cache bumped to hawkerwhere-v24. This push also carries the Addendum 28 ViewContent batch (built 2026-10-11, never pushed; live was still v22), so app.js ships with both changes.
- Verified on the capture build: Pasir Ris Central venue view lists all stalls as "No rating yet" with no centre note and zero star pins (21 clusters, 7 no-rating pins); Venues mode still shows the centre's own 4.1 pin; laksa list still leads with Eddy's 4.7 (301 reviews) on its own rating; Wee Kim's sheet now reads "No rating yet"; zero JS exceptions.
