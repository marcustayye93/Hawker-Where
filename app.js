/* HawkerWhere v1 app.
 *
 * Flow: fetch data/stalls.json (falls back to data/sample-stalls.json),
 * render the dish picker, then a MapLibre map of stall pins with a
 * bottom-sheet stall card and a community tagging queue (localStorage only).
 */

(function () {
  "use strict";

  var SG_CENTER = [1.3521, 103.8198];
  var SG_ZOOM = 11;
  var DATA_URL = "./data/stalls.json";
  var SAMPLE_URL = "./data/sample-stalls.json";
  var TAG_QUEUE_KEY = "hawkerwhere_tag_queue";
  var TAG_DAY_KEY = "hawkerwhere_tag_day";
  var TAG_DAILY_CAP = 20;

  var data = null;          // full payload: { taxonomy, venues, stalls }
  var venueById = {};       // venue_id -> venue
  var map = null;
  var markers = [];         // live map markers (MapLibre has no layer group)
  var venuePopup = null;    // shared popup for venue-mode pins
  var currentDish = null;
  var pinMode = "stalls";   // "stalls" | "venues"
  var userLoc = null;       // [lat, lng]
  var userMarker = null;    // MapLibre marker for the user's dot
  var sheetStall = null;

  /* ---------- helpers ---------- */

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtCount(n) {
    if (n == null) return "";
    return Number(n).toLocaleString("en-SG");
  }

  // Haversine distance in km.
  function haversineKm(aLat, aLng, bLat, bLng) {
    var R = 6371;
    var dLat = (bLat - aLat) * Math.PI / 180;
    var dLng = (bLng - aLng) * Math.PI / 180;
    var s = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(aLat * Math.PI / 180) * Math.cos(bLat * Math.PI / 180) *
      Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  // Deterministic pseudo-random from a string (FNV-1a). Used for pin jitter
  // so stalls sharing a venue get stable, separated positions.
  function hash01(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ((h >>> 0) % 1000) / 1000;
  }

  function jitter(lat, lng, id) {
    var angle = hash01("a" + id) * Math.PI * 2;
    var radius = 0.0006 + hash01("b" + id) * 0.0009; // degrees, a few dozen metres
    return [lat + Math.sin(angle) * radius, lng + Math.cos(angle) * radius];
  }

  function todayKeySG() {
    // Calendar day in Asia/Singapore for the tag rate limit.
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Singapore", year: "numeric", month: "2-digit", day: "2-digit"
    }).format(new Date());
  }

  /* ---------- data load ---------- */

  function loadData() {
    fetch(DATA_URL)
      .then(function (res) { if (!res.ok) throw new Error("stalls.json " + res.status); return res.json(); })
      .then(function (json) { boot(json, "live"); })
      .catch(function () {
        fetch(SAMPLE_URL)
          .then(function (res) { if (!res.ok) throw new Error("sample " + res.status); return res.json(); })
          .then(function (json) { boot(json, "sample"); })
          .catch(function () { showDataError(); });
      });
  }

  function boot(json, source) {
    data = json;
    data.venues.forEach(function (v) { venueById[v.id] = v; });
    renderPicker(source);
    initMap();
    showScreen("picker-screen");
  }

  function showDataError() {
    var picker = $("picker-screen");
    picker.classList.add("screen-active");
    picker.innerHTML =
      "<h1>Stall data is not ready yet</h1>" +
      "<div class='empty-state'><p class='empty-title'>We could not load the stall list</p>" +
      "<p class='empty-body'>Please check your connection and reload. The data file is still being prepared.</p></div>";
  }

  function showScreen(id) {
    ["picker-screen", "map-screen"].forEach(function (s) {
      $(s).classList.toggle("screen-active", s === id);
    });
    if (id === "map-screen" && map) {
      // The container was hidden, so the canvas needs a resize before
      // fitBounds can frame anything sensibly.
      map.resize();
      setTimeout(function () { map.resize(); }, 50);
    }
  }

  /* ---------- screen 1: dish picker ---------- */

  function renderPicker(source) {
    var meta = $("picker-meta");
    meta.textContent = data.taxonomy.length + " dishes, " +
      fmtCount(data.stalls.length) + " stalls across Singapore." +
      (source === "sample" ? " Sample preview data." : "");
    var input = $("dish-search");
    input.placeholder = "Search " + data.taxonomy.length + " dishes, e.g. laksa";
    input.addEventListener("input", function () { renderSuggestions(input.value); });
    input.addEventListener("focus", function () { renderSuggestions(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        var first = $("dish-suggestions").querySelector(".suggest-item");
        if (first) first.click();
      }
    });
  }

  // Live suggestions under the one search bar: as the user types,
  // matching dishes appear; tapping one goes straight to the map.
  function dishMatches(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    var starts = [], contains = [];
    data.taxonomy.forEach(function (dish) {
      var d = dish.toLowerCase();
      if (d.indexOf(q) === 0) starts.push(dish);
      else if (d.indexOf(q) !== -1) contains.push(dish);
    });
    return starts.concat(contains).slice(0, 8);
  }

  function renderSuggestions(q) {
    var box = $("dish-suggestions");
    var matches = dishMatches(q || "");
    if (!matches.length) {
      box.innerHTML = q && q.trim()
        ? "<p class='suggest-empty'>No dish matches that yet.</p>" : "";
      box.classList.toggle("hidden", !q || !q.trim());
      return;
    }
    box.innerHTML = "";
    matches.forEach(function (dish) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "suggest-item";
      b.setAttribute("role", "option");
      b.innerHTML = "<span class='suggest-name'>" + esc(dish) + "</span>";
      b.addEventListener("click", function () { pickDish(dish); });
      box.appendChild(b);
    });
    box.classList.remove("hidden");
  }

  /* ---------- screen 2: map ---------- */

  // Simple 2D basemap: OpenFreeMap vector tiles (free, no API key).
  // Positron is the near-monochrome light style. On top of that every
  // basemap layer is recoloured to neutral greys on load, and the
  // canvas is rendered grayscale, so the map itself carries no colour.
  // Only the pins, badges and UI carry colour.
  var MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
  var MAP_HIDE_LAYERS = ["airport", "highway-shield-non-us",
    "highway-shield-us-interstate", "road_shield_us"];

  function neutralizeBasemap() {
    var layers = (map.getStyle() && map.getStyle().layers) || [];
    layers.forEach(function (layer) {
      try {
        if (layer.type === "background") {
          map.setPaintProperty(layer.id, "background-color", "#f7f7f5");
        } else if (layer.type === "fill") {
          if (layer.id === "water") {
            map.setPaintProperty(layer.id, "fill-color", "#d9dee1");
          } else if (layer.id === "park" || layer.id.indexOf("landcover") === 0) {
            map.setPaintProperty(layer.id, "fill-color", "#e9ebe9");
          } else if (layer.id === "building") {
            map.setPaintProperty(layer.id, "fill-color", "#e9e9e6");
            map.setPaintProperty(layer.id, "fill-outline-color", "#d7d7d4");
          } else {
            map.setPaintProperty(layer.id, "fill-color", "#efefed");
          }
        } else if (layer.type === "line") {
          if (layer.id === "waterway") {
            map.setPaintProperty(layer.id, "line-color", "#c2ccd0");
          }
        } else if (layer.type === "symbol") {
          var text = layer.id.indexOf("water") === 0 ? "#7d868c" : "#444444";
          map.setPaintProperty(layer.id, "text-color", text);
          map.setPaintProperty(layer.id, "text-halo-color", "#ffffff");
        }
      } catch (e) { /* one layer failing must not stop the rest */ }
    });
  }

  function initMap() {
    map = new maplibregl.Map({
      container: "map",
      style: MAP_STYLE,
      center: [SG_CENTER[1], SG_CENTER[0]],
      zoom: SG_ZOOM,
      attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    map.on("load", function () {
      MAP_HIDE_LAYERS.forEach(function (id) {
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
      });
      neutralizeBasemap();
      drawPins(false);
    });
    // Airbnb pattern: pins re-cluster as the zoom changes.
    // (MapLibre takes one event type per registration, unlike Leaflet.)
    map.on("moveend", function () { drawPins(false); });

    $("mode-stalls").addEventListener("click", function () { setPinMode("stalls"); });
    $("mode-venues").addEventListener("click", function () { setPinMode("venues"); });
    $("back-btn").addEventListener("click", function () { showScreen("picker-screen"); });
    $("near-btn").addEventListener("click", nearMe);
  }

  function setPinMode(mode) {
    pinMode = mode;
    $("mode-stalls").classList.toggle("active", mode === "stalls");
    $("mode-venues").classList.toggle("active", mode === "venues");
    $("mode-stalls").setAttribute("aria-pressed", mode === "stalls");
    $("mode-venues").setAttribute("aria-pressed", mode === "venues");
    renderPins();
  }

  function pickDish(dish) {
    currentDish = dish;
    $("map-title").textContent = dish;
    $("dish-suggestions").classList.add("hidden");
    showScreen("map-screen");
    renderPins();
    // Location is only requested when the user taps Near me.
  }

  function filteredStalls() {
    if (!currentDish) return data.stalls.slice();
    return data.stalls.filter(function (s) { return s.dish === currentDish; });
  }

  // Pin badge: color band by rating; hollow ring for venue-rating fallback.
  function ratingBand(rating) {
    if (rating >= 4.5) return "r-great";
    if (rating >= 4.0) return "r-good";
    return "r-low";
  }

  function pinHtml(rating, ratingSource) {
    if (rating == null) return "<span class='pin norating' aria-hidden='true'></span>";
    var cls = "pin " + ratingBand(rating) + (ratingSource === "venue" ? " hollow" : "");
    return "<span class='" + cls + "' aria-hidden='true'><span class='star'>★</span>" + rating.toFixed(1) + "</span>";
  }

  function clusterHtml(count) {
    var size = count >= 100 ? " c-lg" : count >= 20 ? " c-md" : "";
    return "<span class='pin cluster" + size + "' aria-hidden='true'>" + count + "</span>";
  }

  function currentItems() {
    var stalls = filteredStalls();
    var items = [];
    if (pinMode === "stalls") {
      stalls.forEach(function (stall) {
        var v = venueById[stall.venue_id];
        if (!v) return;
        items.push({
          pos: jitter(v.lat, v.lng, stall.id),
          html: pinHtml(stall.rating, stall.rating_source),
          title: stall.name,
          action: function () { openSheet(stall); }
        });
      });
    } else {
      // Venue mode: one item per venue that has a matching stall.
      var seen = {};
      stalls.forEach(function (stall) {
        var v = venueById[stall.venue_id];
        if (!v || seen[v.id]) return;
        seen[v.id] = true;
        var count = stalls.filter(function (s) { return s.venue_id === v.id; }).length;
        items.push({
          pos: [v.lat, v.lng],
          html: pinHtml(v.rating, "venue"),
          title: v.name,
          action: function (m, pos) {
            if (venuePopup) venuePopup.remove();
            venuePopup = new maplibregl.Popup({ closeButton: false, offset: 18 })
              .setLngLat(pos)
              .setHTML("<strong>" + esc(v.name) + "</strong><br>" + count +
                " matching stall" + (count === 1 ? "" : "s"))
              .addTo(map);
          }
        });
      });
    }
    return items;
  }

  // Airbnb pattern: at low zoom, nearby pins collapse into count
  // badges; zooming in splits them apart until single stalls show.
  var CLUSTER_PX = 64;       // on-screen merge distance at current zoom
  var CLUSTER_OFF_ZOOM = 17; // close enough: always single pins

  function clusterize(items) {
    var zoom = map.getZoom();
    if (zoom >= CLUSTER_OFF_ZOOM || items.length < 2) {
      return items.map(function (it) { return { members: [it], pos: it.pos }; });
    }
    var groups = [];
    items.forEach(function (it) {
      var p = map.project([it.pos[1], it.pos[0]]);
      var hit = null;
      for (var i = 0; i < groups.length; i++) {
        var dx = groups[i].px.x - p.x, dy = groups[i].px.y - p.y;
        if (dx * dx + dy * dy <= CLUSTER_PX * CLUSTER_PX) { hit = groups[i]; break; }
      }
      if (!hit) { hit = { members: [], px: p, pos: it.pos }; groups.push(hit); }
      hit.members.push(it);
    });
    groups.forEach(function (g) {
      var la = 0, ln = 0;
      g.members.forEach(function (m) { la += m.pos[0]; ln += m.pos[1]; });
      g.pos = [la / g.members.length, ln / g.members.length];
    });
    return groups;
  }

  function drawPins(fit) {
    if (!map) return;
    markers.forEach(function (m) { m.remove(); });
    markers = [];
    if (venuePopup) { venuePopup.remove(); venuePopup = null; }
    var items = currentItems();
    if (fit && items.length) {
      var lngs = items.map(function (i) { return i.pos[1]; });
      var lats = items.map(function (i) { return i.pos[0]; });
      map.fitBounds([[Math.min.apply(null, lngs), Math.min.apply(null, lats)],
                     [Math.max.apply(null, lngs), Math.max.apply(null, lats)]],
                    { padding: 36, duration: 0 });
    }
    clusterize(items).forEach(function (g) {
      var el = document.createElement("div");
      el.style.cursor = "pointer";
      if (g.members.length === 1) {
        var it = g.members[0];
        el.innerHTML = it.html;
        el.title = it.title;
        var ll = [it.pos[1], it.pos[0]];
        var m = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat(ll).addTo(map);
        el.addEventListener("click", function () { it.action(m, ll); });
        markers.push(m);
      } else {
        el.innerHTML = clusterHtml(g.members.length);
        el.title = g.members.length + " stalls";
        var cm = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([g.pos[1], g.pos[0]]).addTo(map);
        el.addEventListener("click", function () {
          var mlng = g.members.map(function (x) { return x.pos[1]; });
          var mlat = g.members.map(function (x) { return x.pos[0]; });
          var cam = map.cameraForBounds(
            [[Math.min.apply(null, mlng), Math.min.apply(null, mlat)],
             [Math.max.apply(null, mlng), Math.max.apply(null, mlat)]],
            { padding: 60 });
          // Always step closer, even when the cluster's own bounds
          // would keep the same framing (dense downtown clusters).
          // Instant jump, not an animated flight: if a tile source is
          // still loading, MapLibre never pumps the animation frames
          // and the map looks dead. jumpTo always lands.
          var target = Math.min(CLUSTER_OFF_ZOOM,
            Math.max(cam.zoom, map.getZoom() + 1.75));
          map.jumpTo({ center: cam.center, zoom: target });
        });
        markers.push(cm);
      }
    });
  }

  function renderPins() {
    var stalls = filteredStalls();
    $("empty-state").classList.toggle("hidden", stalls.length > 0);
    $("result-count").textContent = stalls.length + " stall" + (stalls.length === 1 ? "" : "s");
    drawPins(true);
    renderResultList(stalls);
  }

  /* ---------- result list (under the map) ---------- */

  function stallVenue(s) { return venueById[s.venue_id]; }

  function sortKey(s) {
    // Weighted rating: a 5.0 from 3 reviews must not outrank a 4.7
    // backed by hundreds. Bayesian average against the dataset mean.
    // Unrated stalls last. Location never reorders this list.
    if (s.rating == null) return [0, Infinity];
    var c = s.rating_count || 0;
    var w = (s.rating * c + 3.9 * 25) / (c + 25);
    return [0, -w];
  }

  function renderResultList(stalls) {
    var list = $("result-list");
    list.innerHTML = "";
    stalls.slice().sort(function (a, b) {
      var ka = sortKey(a), kb = sortKey(b);
      return ka[0] - kb[0] || ka[1] - kb[1];
    }).slice(0, 30).forEach(function (s) {
      var v = stallVenue(s);
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "result-item";
      var dist = "";
      if (userLoc && v) {
        dist = " &middot; " + haversineKm(userLoc[0], userLoc[1], v.lat, v.lng).toFixed(1) + " km away";
      }
      btn.innerHTML =
        "<p class='r-name'>" + esc(s.name) + "</p>" +
        "<p class='r-rating'>" + esc(ratingLine(s).short) + "</p>" +
        "<p class='r-sub'>" + esc(s.dish || "Dish not tagged yet") + " &middot; " + esc(v ? v.name : "") + dist + "</p>";
      btn.addEventListener("click", function () { openSheet(s); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  // User location: a blue dot on the map, so each user can see where
  // they are relative to the stalls. The result list keeps its
  // rating order; the dot is for orientation only.
  function drawUserDot() {
    if (!map || !userLoc) return;
    if (userMarker) userMarker.remove();
    var el = document.createElement("div");
    el.className = "user-dot";
    el.innerHTML = "<span class='user-dot-pulse'></span><span class='user-dot-core'></span>";
    el.title = "You are here";
    userMarker = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat([userLoc[1], userLoc[0]]).addTo(map);
  }

  function locateUser(center) {
    if (!navigator.geolocation) {
      if (center) $("result-count").textContent = "Location is not supported on this device.";
      return;
    }
    var btn = $("near-btn");
    btn.disabled = true;
    btn.textContent = "Locating...";
    navigator.geolocation.getCurrentPosition(function (pos) {
      userLoc = [pos.coords.latitude, pos.coords.longitude];
      btn.disabled = false;
      btn.textContent = "Near me";
      drawUserDot();
      if (center && map) {
        map.jumpTo({ center: [userLoc[1], userLoc[0]],
                     zoom: Math.max(map.getZoom(), 14.5) });
      }
      var stalls = filteredStalls();
      $("result-count").textContent = stalls.length +
        " stall" + (stalls.length === 1 ? "" : "s");
      renderResultList(stalls);
    }, function () {
      btn.disabled = false;
      btn.textContent = "Near me";
      if (center) $("result-count").textContent = "Could not get your location. Showing top rated.";
    }, { timeout: 10000, maximumAge: 60000 });
  }

  function nearMe() {
    if (userLoc) {
      drawUserDot();
      if (map) map.jumpTo({ center: [userLoc[1], userLoc[0]],
                            zoom: Math.max(map.getZoom(), 14.5) });
      renderResultList(filteredStalls());
      return;
    }
    locateUser(true);
  }

  /* ---------- stall card (bottom sheet) ---------- */

  function ratingLine(stall) {
    if (stall.rating_source === "venue") {
      if (stall.rating == null) return { short: "No rating yet", long: "No rating yet" };
      return {
        short: "\u2605 " + stall.rating.toFixed(1) + " venue rating",
        long: "\u2605 " + stall.rating.toFixed(1) +
          " <span class='count'>(" + fmtCount(stall.rating_count) + " reviews, venue rating)</span>"
      };
    }
    if (stall.rating == null) return { short: "No rating yet", long: "No rating yet" };
    return {
      short: "\u2605 " + stall.rating.toFixed(1),
      long: "\u2605 " + stall.rating.toFixed(1) +
        " <span class='count'>(" + fmtCount(stall.rating_count) + " reviews)</span>"
    };
  }

  function openSheet(stall) {
    sheetStall = stall;
    var v = stallVenue(stall);

    $("sheet-name").textContent = stall.name;
    $("sheet-dish").textContent = stall.dish || "Dish not tagged yet";
    $("sheet-rating").innerHTML = ratingLine(stall).long;
    $("sheet-venue").innerHTML = esc(v ? v.name : "") +
      (stall.unit ? " " + esc(stall.unit) : "") +
      "<br>" + esc(stall.address);
    $("sheet-safe").innerHTML = "SAFE hygiene grade: <strong>" + esc(stall.safe_grade || "?") + "</strong>";

    var statusEl = $("sheet-status");
    if (v && v.closed) {
      statusEl.innerHTML = "<span class='closed-note'>Closed</span> &middot; " + esc(v.closure_note || "See venue for details.");
    } else {
      statusEl.innerHTML = "<span class='open-note'>Open</span>";
    }

    var q = encodeURIComponent(stall.name + ", " + stall.address);
    $("sheet-directions").href = "https://www.google.com/maps/search/?api=1&query=" + q;

    // Reset the tagging UI.
    $("tag-form").classList.add("hidden");
    $("tag-open").classList.remove("hidden");
    $("tag-thanks").classList.add("hidden");
    renderTagChips();

    $("sheet-scrim").classList.remove("hidden");
    $("stall-sheet").classList.remove("hidden");
  }

  function closeSheet() {
    $("sheet-scrim").classList.add("hidden");
    $("stall-sheet").classList.add("hidden");
    sheetStall = null;
  }

  $("sheet-close").addEventListener("click", closeSheet);
  $("sheet-scrim").addEventListener("click", closeSheet);

  /* ---------- tagging UI (localStorage queue, no backend in v1) ---------- */

  function renderTagChips() {
    var grid = $("tag-chips");
    grid.innerHTML = "";
    data.taxonomy.forEach(function (dish) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = dish;
      b.addEventListener("click", function () { recordTag(dish); });
      grid.appendChild(b);
    });
  }

  function getTagQueue() {
    try {
      var raw = localStorage.getItem(TAG_QUEUE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function recordTag(dish) {
    if (!sheetStall) return;
    var today = todayKeySG();
    var lastDay = null;
    try { lastDay = localStorage.getItem(TAG_DAY_KEY); } catch (e) {}
    var countToday = 0;
    if (lastDay === today) {
      try { countToday = parseInt(localStorage.getItem(TAG_QUEUE_KEY + "_count") || "0", 10) || 0; }
      catch (e) { countToday = 0; }
    }
    var thanks = $("tag-thanks");
    if (countToday >= TAG_DAILY_CAP) {
      thanks.textContent = "Tag limit reached for today. Come back tomorrow.";
      thanks.classList.remove("hidden");
      return;
    }
    var queue = getTagQueue();
    queue.push({ stall_id: sheetStall.id, dish: dish, ts: new Date().toISOString() });
    try {
      localStorage.setItem(TAG_QUEUE_KEY, JSON.stringify(queue));
      localStorage.setItem(TAG_DAY_KEY, today);
      localStorage.setItem(TAG_QUEUE_KEY + "_count", String(countToday + 1));
    } catch (e) { /* storage full or blocked: still thank the user */ }
    thanks.textContent = "Thanks. Your tag is saved and will be reviewed.";
    thanks.classList.remove("hidden");
  }

  $("tag-open").addEventListener("click", function () {
    $("tag-open").classList.add("hidden");
    $("tag-form").classList.remove("hidden");
  });

  /* ---------- PWA service worker ---------- */

  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("./sw.js").catch(function () { /* offline is best-effort */ });
    });
  }

  /* ---------- go ---------- */

  loadData();
})();
