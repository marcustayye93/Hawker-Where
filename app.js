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
  var TAXONOMY_URL = "./data/taxonomy.json";
  var SAMPLE_URL = "./data/sample-stalls.json";
  var TAG_QUEUE_KEY = "hawkerwhere_tag_queue";
  var TAG_DAY_KEY = "hawkerwhere_tag_day";
  var TAG_DAILY_CAP = 20;

  var data = null;          // full payload: { taxonomy, venues, stalls }
  var venueById = {};       // venue_id -> venue
  var stallById = {};       // stall id -> stall
  var map = null;
  var markers = [];         // live map markers (MapLibre has no layer group)
  var venuePopup = null;    // shared popup for venue-mode pins
  var currentDish = null;
  var currentVenueId = null; // set when browsing one venue from search
  var pendingDish = null;    // dish picked before the full data arrived
  var taxonomyMeta = null;   // light payload: { dishes, stall_count, venue_count }
  var pinMode = "stalls";   // "stalls" | "venues"
  var inspireTab = "bib";   // "bib" | "author"
  var inspireRegion = "all"; // bib region filter
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
    // Light file first: the picker and dish suggestions come alive
    // while the full 2.1MB payload is still on its way.
    fetch(TAXONOMY_URL)
      .then(function (res) { if (!res.ok) throw new Error("taxonomy " + res.status); return res.json(); })
      .then(function (t) { taxonomyMeta = t; if (!data) renderPicker("taxonomy"); })
      .catch(function () { /* the full payload will render the picker */ });
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
    data.stalls.forEach(function (s) { stallById[s.id] = s; });
    renderPicker(source);
    renderInspire();
    refreshSavedUI();
    initMap();
    initLandingMap();
    showScreen("picker-screen");
    handleDeepLink();
    if (pendingDish) {
      var d = pendingDish;
      pendingDish = null;
      pickDish(d);
    }
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

  var searchBound = false;

  function renderPicker(source) {
    var dishCount = data ? data.taxonomy.length
      : (taxonomyMeta ? taxonomyMeta.dishes.length : 0);
    var stallCount = data ? data.stalls.filter(function (s) { return !s.author_manual; }).length
      : (taxonomyMeta ? taxonomyMeta.stall_count : 0);
    var meta = $("picker-meta");
    meta.textContent = dishCount + " dishes, " +
      fmtCount(stallCount) + " stalls across Singapore." +
      (source === "sample" ? " Sample preview data." : "");
    var input = $("dish-search");
    input.placeholder = "Search " + dishCount + " dishes, stalls and places";
    if (searchBound) return;
    searchBound = true;
    input.addEventListener("input", function () { renderSuggestions(input.value); });
    input.addEventListener("focus", function () { renderSuggestions(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        var first = $("dish-suggestions").querySelector(".suggest-item");
        if (first) first.click();
      }
    });
  }

  function dishList() {
    if (data) return data.taxonomy;
    if (taxonomyMeta) return taxonomyMeta.dishes;
    return [];
  }

  // Live suggestions under the one search bar: dishes first, then
  // venues and stall names once the full payload has landed. The
  // untagged stalls are invisible to dish search; venue and stall
  // search is how a user reaches them ("I'm at Maxwell", "Tian Tian").
  function dishMatches(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    var starts = [], contains = [];
    dishList().forEach(function (dish) {
      var d = dish.toLowerCase();
      if (d.indexOf(q) === 0) starts.push(dish);
      else if (d.indexOf(q) !== -1) contains.push(dish);
    });
    return starts.concat(contains).slice(0, 6);
  }

  function venueMatches(q) {
    if (!data) return [];
    q = q.trim().toLowerCase();
    if (q.length < 2) return [];
    var starts = [], contains = [];
    data.venues.forEach(function (v) {
      var n = v.name.toLowerCase();
      if (n.indexOf(q) === 0) starts.push(v);
      else if (n.indexOf(q) !== -1) contains.push(v);
    });
    return starts.concat(contains).slice(0, 3);
  }

  function stallMatches(q) {
    if (!data) return [];
    q = q.trim().toLowerCase();
    if (q.length < 3) return [];
    var hits = [];
    for (var i = 0; i < data.stalls.length && hits.length < 4; i++) {
      var s = data.stalls[i];
      if (!s.name || /^unnamed/i.test(s.name)) continue;
      if (s.name.toLowerCase().indexOf(q) !== -1) hits.push(s);
    }
    return hits;
  }

  function renderSuggestions(q) {
    var box = $("dish-suggestions");
    var dishes = dishMatches(q || "");
    var venues = venueMatches(q || "");
    var stalls = stallMatches(q || "");
    if (!dishes.length && !venues.length && !stalls.length) {
      box.innerHTML = q && q.trim()
        ? "<p class='suggest-empty'>Nothing matches that yet.</p>" : "";
      box.classList.toggle("hidden", !q || !q.trim());
      return;
    }
    box.innerHTML = "";
    function addHead(text) {
      var h = document.createElement("p");
      h.className = "suggest-head";
      h.textContent = text;
      box.appendChild(h);
    }
    function addItem(main, sub, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "suggest-item";
      b.setAttribute("role", "option");
      b.innerHTML = "<span class='suggest-name'>" + esc(main) + "</span>" +
        (sub ? "<span class='suggest-sub'>" + esc(sub) + "</span>" : "");
      b.addEventListener("click", fn);
      box.appendChild(b);
    }
    if (dishes.length) {
      dishes.forEach(function (dish) {
        addItem(dish, "", function () { pickDish(dish); });
      });
    }
    if (venues.length) {
      addHead("Places");
      venues.forEach(function (v) {
        addItem(v.name, "", function () { pickVenue(v); });
      });
    }
    if (stalls.length) {
      addHead("Stalls");
      stalls.forEach(function (s) {
        var v = venueById[s.venue_id];
        addItem(s.author_name || s.name, (s.author_cuisine || s.dish || "dish not tagged") + (v ? " · " + v.name : ""),
          function () { openCuratedStall(s); });
      });
    }
    box.classList.remove("hidden");
  }

  /* ---------- can't decide: curated tabs ---------- */

  function inspireStalls(tab) {
    if (tab === "author") {
      return data.stalls.filter(function (s) { return s.author_pick; });
    }
    return data.stalls.filter(function (s) { return s.bib; });
  }

  // Region buckets from venue coordinates (Marcus, 5 Oct):
  // north / south / east / west / central.
  function regionOf(v) {
    if (!v || v.lat == null || v.lng == null) return "central";
    if (v.lat >= 1.395) return "north";
    if (v.lng <= 103.755) return "west";
    if (v.lng >= 103.895) return "east";
    if (v.lat <= 1.29 && v.lng < 103.83) return "south";
    return "central";
  }

  function renderInspire() {
    var list = $("inspire-list");
    var note = $("inspire-note");
    $("tab-bib").classList.toggle("tab-on", inspireTab === "bib");
    $("tab-author").classList.toggle("tab-on", inspireTab === "author");
    $("region-tabs").classList.toggle("hidden", inspireTab !== "bib");
    Array.prototype.forEach.call(
      document.querySelectorAll(".region-tab"),
      function (b) {
        b.classList.toggle("tab-on", b.getAttribute("data-region") === inspireRegion);
      }
    );
    var stalls = inspireStalls(inspireTab);
    list.innerHTML = "";

    if (inspireTab === "author" && !stalls.length) {
      note.textContent = "";
      var li0 = document.createElement("li");
      li0.className = "inspire-empty";
      li0.textContent = "The author's picks land here soon.";
      list.appendChild(li0);
      return;
    }

    var shown = stalls;
    if (inspireTab === "bib" && inspireRegion !== "all") {
      shown = stalls.filter(function (s) {
        return regionOf(venueById[s.venue_id]) === inspireRegion;
      });
    }

    var names = {};
    shown.forEach(function (s) { names[s.author_name || s.bib_name || s.name] = true; });
    note.textContent = inspireTab === "bib"
      ? "Michelin Bib Gourmand 2026: " + Object.keys(names).length +
        " hawker establishments on the map." +
        (inspireRegion !== "all"
          ? " (" + inspireRegion.charAt(0).toUpperCase() + inspireRegion.slice(1) + ")"
          : "")
      : shown.length + " hand picked places.";

    if (!shown.length) {
      var liE = document.createElement("li");
      liE.className = "inspire-empty";
      liE.textContent = "No Bib Gourmand stalls here yet.";
      list.appendChild(liE);
      return;
    }

    if (inspireTab === "author") {
      var regionOrder = ["north", "south", "east", "west", "central"];
      var regionLabels = {
        north: "North", south: "South", east: "East", west: "West", central: "Central"
      };
      var byRegion = {};
      shown.forEach(function (s) {
        var r = regionOf(venueById[s.venue_id]);
        if (!byRegion[r]) byRegion[r] = [];
        byRegion[r].push(s);
      });
      regionOrder.forEach(function (r) {
        var group = byRegion[r];
        if (!group || !group.length) return;
        var head = document.createElement("li");
        head.className = "inspire-region";
        head.textContent = regionLabels[r];
        list.appendChild(head);
        group.slice().sort(function (a, b) {
          var ao = a.author_order == null ? 99 : a.author_order;
          var bo = b.author_order == null ? 99 : b.author_order;
          return ao - bo || (a.author_name || a.name).localeCompare(b.author_name || b.name);
        }).forEach(function (s) {
          var v = venueById[s.venue_id];
          var li = document.createElement("li");
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "result-item";
          btn.innerHTML =
            "<p class='r-name'>" + esc(s.author_name || s.name) + "</p>" +
            "<p class='r-rating'>" + ratingShortHtml(s) + "</p>" +
            "<p class='r-cuisine'>" + esc(s.author_cuisine || s.dish || "Cuisine not tagged yet") + "</p>" +
            "<p class='r-sub'>" + esc(s.author_manual ? (v ? v.address : "") : (v ? v.name : "")) + (s.unit ? " &middot; " + esc(s.unit) : "") + "</p>";
          btn.addEventListener("click", function () { openAuthorPick(s); });
          li.appendChild(btn);
          list.appendChild(li);
        });
      });
      return;
    }

    shown.slice().sort(function (a, b) {
      return (a.bib_name || a.name).localeCompare(b.bib_name || b.name);
    }).forEach(function (s) {
      var v = venueById[s.venue_id];
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "result-item";
      btn.innerHTML =
        "<p class='r-name'>" + esc(s.bib_name || s.name) + "</p>" +
        "<p class='r-rating'>" + ratingShortHtml(s) + "</p>" +
        "<p class='r-sub'>" + esc(s.dish || "Dish not tagged yet") + " &middot; " +
        esc(v ? v.name : "") + (s.unit ? " &middot; " + esc(s.unit) : "") + "</p>";
      btn.addEventListener("click", function () { openCuratedStall(s); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  function setInspireTab(tab) {
    inspireTab = tab;
    renderInspire();
  }

  function setInspireRegion(region) {
    inspireRegion = region;
    renderInspire();
  }

  // An Author's Pick card goes to the place itself, not the whole
  // dish category, then opens the place card.
  function openAuthorPick(s) {
    var v = venueById[s.venue_id];
    currentDish = null;
    currentVenueId = s.venue_id;
    $("map-title").textContent = s.author_name || s.name;
    $("dish-suggestions").classList.add("hidden");
    showScreen("map-screen");
    renderPins();
    if (map && v && typeof v.lat === "number" && typeof v.lng === "number") {
      map.jumpTo({ center: [v.lng, v.lat], zoom: 16.5 });
    }
    setShareParam("venue", s.venue_id);
    setShareParam("dish", null);
    openSheet(s);
  }

  // A curated card goes to the map on the stall's own dish filter,
  // then opens the stall card.
  function openCuratedStall(s) {
    if (s.author_pick) {
      openAuthorPick(s);
      return;
    }
    if (s.dish) {
      pickDish(s.dish);
    } else {
      currentDish = null;
      currentVenueId = null;
      $("map-title").textContent = s.bib_name || s.name;
      showScreen("map-screen");
      renderPins();
    }
    openSheet(s);
  }

  /* ---------- saved stalls (this device only, localStorage) ---------- */

  var SAVED_KEY = "hawkerwhere:saved";
  var savedOpen = false;

  function savedIds() {
    try {
      var raw = localStorage.getItem(SAVED_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function isSaved(id) { return savedIds().indexOf(id) !== -1; }

  function saveLabel(stall) {
    if (!stall) return "Save this stall";
    return isSaved(stall.id) ? "Saved. Tap to remove"
      : (stall.author_manual ? "Save this place" : "Save this stall");
  }

  function toggleSaved(id) {
    var ids = savedIds();
    var i = ids.indexOf(id);
    if (i >= 0) { ids.splice(i, 1); } else { ids.push(id); }
    try { localStorage.setItem(SAVED_KEY, JSON.stringify(ids)); } catch (e) { /* storage full or blocked */ }
    refreshSavedUI();
  }

  function refreshSavedUI() {
    var ids = savedIds();
    $("saved-count").textContent = ids.length ? "(" + ids.length + ")" : "";
    if (sheetStall) {
      $("sheet-save").textContent = saveLabel(sheetStall);
    }
    if (savedOpen) { renderSavedList(); }
  }

  function renderSavedList() {
    var list = $("saved-list");
    list.innerHTML = "";
    var stalls = savedIds().map(function (id) { return stallById[id]; }).filter(Boolean);
    if (!stalls.length) {
      var li0 = document.createElement("li");
      li0.className = "inspire-empty";
      li0.textContent = "Nothing saved yet. Open any stall and tap Save this stall.";
      list.appendChild(li0);
      return;
    }
    stalls.forEach(function (s) {
      var v = venueById[s.venue_id];
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "result-item";
      btn.innerHTML =
        "<p class='r-name'>" + esc(s.author_name || s.bib_name || s.name) + "</p>" +
        "<p class='r-rating'>" + ratingShortHtml(s) + "</p>" +
        "<p class='r-sub'>" + esc(s.author_cuisine || s.dish || "Dish not tagged yet") + " &middot; " +
        esc(v ? v.name : "") + (s.unit ? " &middot; " + esc(s.unit) : "") + "</p>";
      btn.addEventListener("click", function () { openCuratedStall(s); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  $("saved-btn").addEventListener("click", function () {
    savedOpen = !savedOpen;
    $("saved-wrap").classList.toggle("hidden", !savedOpen);
    if (savedOpen) { renderSavedList(); }
  });

  $("sheet-save").addEventListener("click", function () {
    if (sheetStall) { toggleSaved(sheetStall.id); }
  });

  /* ---------- screen 2: map ---------- */

  // Simple 2D basemap: OpenFreeMap vector tiles (free, no API key).
  // Positron is the near-monochrome light style. On top of that every
  // basemap layer is recoloured to neutral greys on load, and the
  // canvas is rendered grayscale, so the map itself carries no colour.
  // Only the pins, badges and UI carry colour.
  var MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
  var MAP_HIDE_LAYERS = ["airport", "highway-shield-non-us",
    "highway-shield-us-interstate", "road_shield_us"];

  function neutralizeBasemap(m) {
    m = m || map;
    if (!m) return;
    var layers = (m.getStyle() && m.getStyle().layers) || [];
    layers.forEach(function (layer) {
      try {
        if (layer.type === "background") {
          m.setPaintProperty(layer.id, "background-color", "#f7f7f5");
        } else if (layer.type === "fill") {
          if (layer.id === "water") {
            m.setPaintProperty(layer.id, "fill-color", "#d9dee1");
          } else if (layer.id === "park" || layer.id.indexOf("landcover") === 0) {
            m.setPaintProperty(layer.id, "fill-color", "#e9ebe9");
          } else if (layer.id === "building") {
            m.setPaintProperty(layer.id, "fill-color", "#e9e9e6");
            m.setPaintProperty(layer.id, "fill-outline-color", "#d7d7d4");
          } else {
            m.setPaintProperty(layer.id, "fill-color", "#efefed");
          }
        } else if (layer.type === "line") {
          if (layer.id === "waterway") {
            m.setPaintProperty(layer.id, "line-color", "#c2ccd0");
          }
        } else if (layer.type === "symbol") {
          var text = layer.id.indexOf("water") === 0 ? "#7d868c" : "#444444";
          m.setPaintProperty(layer.id, "text-color", text);
          m.setPaintProperty(layer.id, "text-halo-color", "#ffffff");
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
    map.on("moveend", function () { drawPins(false); syncListToViewport(); });

    $("mode-stalls").addEventListener("click", function () { setPinMode("stalls"); });
    $("mode-venues").addEventListener("click", function () { setPinMode("venues"); });
    $("back-btn").addEventListener("click", function () { showScreen("picker-screen"); });
    $("near-btn").addEventListener("click", nearMe);
    $("tab-bib").addEventListener("click", function () { setInspireTab("bib"); });
    $("tab-author").addEventListener("click", function () { setInspireTab("author"); });
    Array.prototype.forEach.call(
      document.querySelectorAll(".region-tab"),
      function (b) {
        b.addEventListener("click", function () {
          setInspireRegion(b.getAttribute("data-region"));
        });
      }
    );
  }

  /* ---------- landing mini-map (teaser) ---------- */

  var landingMap = null;

  function initLandingMap() {
    var box = $("landing-map");
    if (!box || landingMap || typeof maplibregl === "undefined") return;
    var activate = function () {
      var input = $("dish-search");
      input.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(function () { input.focus({ preventScroll: true }); }, 350);
    };
    box.addEventListener("click", activate);
    box.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
    });
    try {
      landingMap = new maplibregl.Map({
        container: "landing-map",
        style: MAP_STYLE,
        center: [SG_CENTER[1], SG_CENTER[0]],
        zoom: 9.6,
        interactive: false,
        attributionControl: { compact: true }
      });
    } catch (e) {
      landingMap = null;
      return;
    }
    landingMap.on("load", function () {
      MAP_HIDE_LAYERS.forEach(function (id) {
        if (landingMap.getLayer(id)) {
          landingMap.setLayoutProperty(id, "visibility", "none");
        }
      });
      neutralizeBasemap(landingMap);
      renderLandingBadges();
    });
  }

  function renderLandingBadges() {
    if (!landingMap || !data) return;
    var perVenue = {};
    data.stalls.forEach(function (s) {
      perVenue[s.venue_id] = (perVenue[s.venue_id] || 0) + 1;
    });
    var pts = [];
    data.venues.forEach(function (v) {
      var n = perVenue[v.id] || 0;
      if (n && v.lat && v.lng) pts.push({ pos: [v.lat, v.lng], n: n });
    });
    var groups = [];
    pts.forEach(function (p) {
      var px = landingMap.project([p.pos[1], p.pos[0]]);
      var hit = null;
      for (var i = 0; i < groups.length; i++) {
        var dx = groups[i].px.x - px.x, dy = groups[i].px.y - px.y;
        if (dx * dx + dy * dy <= 56 * 56) { hit = groups[i]; break; }
      }
      if (!hit) { hit = { px: px, pos: p.pos, n: 0 }; groups.push(hit); }
      hit.n += p.n;
    });
    groups.forEach(function (g) {
      var el = document.createElement("div");
      el.innerHTML = clusterHtml(g.n);
      new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([g.pos[1], g.pos[0]]).addTo(landingMap);
    });
  }

  function setPinMode(mode) {
    pinMode = mode;
    $("mode-stalls").classList.toggle("active", mode === "stalls");
    $("mode-venues").classList.toggle("active", mode === "venues");
    $("mode-stalls").setAttribute("aria-pressed", mode === "stalls");
    $("mode-venues").setAttribute("aria-pressed", mode === "venues");
    renderPins();
  }

  /* ---------- shareable links (?dish=, ?stall=) ---------- */

  function setShareParam(key, value) {
    try {
      var u = new URL(window.location.href);
      if (value) { u.searchParams.set(key, value); } else { u.searchParams.delete(key); }
      history.replaceState(null, "", u.toString());
    } catch (e) { /* file:// or exotic URL: links just stay plain */ }
  }

  function handleDeepLink() {
    var params;
    try { params = new URLSearchParams(window.location.search); } catch (e) { return; }
    var stallId = params.get("stall");
    var venueParam = params.get("venue");
    var dishParam = params.get("dish");
    if (stallId && stallById[stallId]) {
      var s = stallById[stallId];
      if (s.dish) { pickDish(s.dish); } else {
        currentDish = null;
        currentVenueId = null;
        $("map-title").textContent = s.bib_name || s.name;
        showScreen("map-screen");
        renderPins();
      }
      openSheet(s);
      return;
    }
    if (venueParam && venueById[venueParam]) {
      pickVenue(venueById[venueParam]);
      return;
    }
    if (dishParam && data.taxonomy.indexOf(dishParam) !== -1) {
      pickDish(dishParam);
    }
  }

  function pickDish(dish) {
    if (!data) { pendingDish = dish; return; }
    currentDish = dish;
    currentVenueId = null;
    $("map-title").textContent = dish;
    $("dish-suggestions").classList.add("hidden");
    showScreen("map-screen");
    renderPins();
    setShareParam("dish", dish);
    setShareParam("venue", null);
    // Location is only requested when the user taps Near me.
  }

  function pickVenue(v) {
    if (!v) return;
    currentDish = null;
    currentVenueId = v.id;
    $("map-title").textContent = v.name;
    $("dish-suggestions").classList.add("hidden");
    showScreen("map-screen");
    renderPins();
    if (map && typeof v.lat === "number" && typeof v.lng === "number") {
      map.jumpTo({ center: [v.lng, v.lat], zoom: 16.5 });
    }
    setShareParam("venue", v.id);
    setShareParam("dish", null);
  }

  function filteredStalls() {
    if (currentVenueId) {
      return data.stalls.filter(function (s) { return s.venue_id === currentVenueId; });
    }
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
            Math.max(cam.zoom + 0.25, map.getZoom() + 1.75));
          map.jumpTo({ center: cam.center, zoom: target });
        });
        markers.push(cm);
      }
    });
  }

  function renderPins() {
    var stalls = filteredStalls();
    $("empty-state").classList.toggle("hidden", stalls.length > 0);
    drawPins(true);
    renderResultList(null);
  }

  /* ---------- result list (under the map) ---------- */

  function stallVenue(s) { return venueById[s.venue_id]; }

  function sortKey(s) {
    // Weighted rating: a 5.0 from 3 reviews must not outrank a 4.7
    // backed by hundreds. Bayesian average against the dataset mean.
    // Venue (centre) ratings sit in their own tier below every stall's
    // own rating, with the centre's review count capped inside the
    // weight, so a centre score can never masquerade as a stall score.
    // Unrated stalls last. Location never reorders this list.
    if (s.rating == null) return [2, 0];
    var c = s.rating_count || 0;
    if (s.rating_source === "venue") c = Math.min(c, 10);
    var w = (s.rating * c + 3.9 * 25) / (c + 25);
    return [s.rating_source === "venue" ? 1 : 0, -w];
  }

  // Keep the plain-text list in step with the map: whatever pins
  // are in the current view are the stalls the list names. Rating
  // order inside the view does not change; only the set does.
  function syncListToViewport() {
    if (!map || !data) return;
    if (!$("map-screen").classList.contains("screen-active")) return;
    var all = filteredStalls();
    var b = map.getBounds();
    var inView = all.filter(function (s) {
      var v = stallVenue(s);
      return v && v.lng >= b.getWest() && v.lng <= b.getEast() &&
             v.lat >= b.getSouth() && v.lat <= b.getNorth();
    });
    if (inView.length === all.length) {
      renderResultList(null);
    } else {
      renderResultList(inView, all.length);
    }
  }

  function renderResultList(viewStalls, totalCount) {
    var stalls = viewStalls || filteredStalls();
    var noun = (currentVenueId && currentVenueId.indexOf("authors-pick-") === 0) ? "place" : "stall";
    if (viewStalls && typeof totalCount === "number") {
      $("result-count").textContent = stalls.length + " of " + totalCount +
        " " + noun + "s in this view";
    } else {
      $("result-count").textContent = stalls.length + " " + noun +
        (stalls.length === 1 ? "" : "s");
    }
    var list = $("result-list");
    list.innerHTML = "";
    if (viewStalls && !stalls.length) {
      var emptyLi = document.createElement("li");
      emptyLi.className = "sort-note";
      emptyLi.textContent = "Nothing for this dish in this part of the map yet. Zoom out or pan to see more stalls.";
      list.appendChild(emptyLi);
      return;
    }
    var sorted = stalls.slice().sort(function (a, b) {
      var ka = sortKey(a), kb = sortKey(b);
      return ka[0] - kb[0] || ka[1] - kb[1];
    }).slice(0, 30);
    var seenTierBoundary = false;
    sorted.forEach(function (s) {
      // One quiet note where centre-rated stalls begin, so nobody
      // mistakes a centre score for a stall score while scrolling.
      if (!seenTierBoundary && s.rating != null && s.rating_source === "venue") {
        seenTierBoundary = true;
        var note = document.createElement("li");
        note.className = "sort-note";
        note.textContent = "Centre ratings below. The number is the food centre's, not the stall's.";
        list.appendChild(note);
      }
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
        "<p class='r-rating'>" + ratingShortHtml(s) + "</p>" +
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
      syncListToViewport();
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
      syncListToViewport();
      return;
    }
    locateUser(true);
  }

  /* ---------- stall card (bottom sheet) ---------- */

  function ratingShortHtml(stall) {
    var line = ratingLine(stall).short;
    if (line.charAt(0) === "\u2605") {
      return "<span class='star'>\u2605</span>" + esc(line.slice(1));
    }
    return esc(line);
  }

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

  function dishSourceLine(stall) {
    if (stall.author_pick) return "Author's Pick.";
    if (!stall.dish) return "";
    var src = stall.dish_source || "";
    if (src === "name" || src === "name_pass") return "Dish tagged from the stall name.";
    if (src === "google_title") return "Dish tagged from the Google listing title.";
    if (src === "brave_web" || src === "grok_web") return "Dish tagged from web sources.";
    if (src === "bib_gourmand") return "Dish tagged from the Michelin Bib Gourmand listing.";
    if (src === "correction") return "Dish corrected from local evidence.";
    if (src === "licensee_transfer" || src === "name_transfer") return "Dish tagged from the licence record.";
    return "";
  }

  function openSheet(stall) {
    sheetStall = stall;
    var v = stallVenue(stall);

    $("sheet-name").textContent = stall.author_name || stall.name;
    $("sheet-dish").textContent = stall.author_cuisine || stall.dish || "Dish not tagged yet";
    $("sheet-rating").innerHTML = ratingLine(stall).long;
    $("sheet-source").textContent = dishSourceLine(stall);
    var alsoEl = $("sheet-also");
    if (stall.also && stall.also.length) {
      alsoEl.textContent = "Also known for: " + stall.also.join(", ");
      alsoEl.classList.remove("hidden");
    } else {
      alsoEl.textContent = "";
      alsoEl.classList.add("hidden");
    }
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

    // Update the save button for this stall.
    $("sheet-save").textContent = saveLabel(stall);

    // Reset the tagging UI.
    $("tag-form").classList.add("hidden");
    $("tag-open").classList.remove("hidden");
    $("tag-thanks").classList.add("hidden");
    renderTagChips();

    $("sheet-scrim").classList.remove("hidden");
    $("stall-sheet").classList.remove("hidden");
    setShareParam("stall", stall.id);

    // Keep the pin visible above the bottom sheet: shift the map so
    // the stall sits above screen centre instead of behind the card.
    if (map && v && typeof v.lng === "number" && typeof v.lat === "number") {
      var off = window.innerWidth < 760
        ? Math.round(map.getContainer().clientHeight * 0.16)
        : 70;
      map.jumpTo({ center: [v.lng, v.lat], offset: [0, -off] });
    }
  }

  function closeSheet() {
    $("sheet-scrim").classList.add("hidden");
    $("stall-sheet").classList.add("hidden");
    sheetStall = null;
    setShareParam("stall", null);
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
    // If a newer worker takes control mid-session, reload once onto
    // the fresh shell instead of running stale code until the user
    // happens to fully close and reopen the app.
    var swReloaded = false;
    var hadController = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.addEventListener("controllerchange", function () {
      if (!hadController || swReloaded) return;
      swReloaded = true;
      window.location.reload();
    });
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("./sw.js").then(function (reg) {
        // Long-lived PWA sessions may never navigate again; ask for
        // an update check whenever the app comes back to the front.
        document.addEventListener("visibilitychange", function () {
          if (document.visibilityState === "visible") {
            reg.update().catch(function () { /* best-effort */ });
          }
        });
      }).catch(function () { /* offline is best-effort */ });
    });
  }

  /* ---------- go ---------- */

  loadData();
})();
