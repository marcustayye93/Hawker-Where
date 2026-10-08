#!/usr/bin/env python3
"""Generate static per-dish share pages from data/stalls.json.

One page per dish at dish/<slug>/index.html, a dish index, a sitemap
and robots.txt. Each page has its own title and share description so a
dish link unfurls properly in WhatsApp and can be indexed, then hands
off to the live map at /?dish=<dish>. Rerun after any payload change.
"""
import html
import json
import os
import re
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SITE = "https://hawkerwhere.com"

CSS = """
:root{--red:#ff385c;--ink:#222;--muted:#717171;--line:#e3e3e3}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff}
main{max-width:720px;margin:0 auto;padding:24px 20px 48px}
.brand{color:var(--red);font-weight:800;font-size:20px;text-decoration:none;letter-spacing:-.5px}
.tag{color:var(--muted);font-size:13px;margin:2px 0 24px}
h1{font-family:"Iowan Old Style",Georgia,"Times New Roman",serif;font-size:clamp(30px,8vw,42px);line-height:1.12;margin:0 0 8px}
.sub{color:var(--muted);font-size:15px;margin:0 0 20px}
.cta{display:inline-block;background:var(--red);color:#fff;font-weight:700;text-decoration:none;padding:13px 22px;border-radius:12px;font-size:16px}
ol{list-style:none;margin:28px 0 0;padding:0}
li{border:1px solid #ebebeb;border-radius:12px;padding:14px 16px;margin:0 0 10px}
.nm{font-weight:600;font-size:16px;margin:0 0 3px}
.rt{font-weight:600;font-size:14px;margin:0 0 3px}
.rt .star{color:var(--red)}
.vn{color:var(--muted);font-size:13.5px;margin:0}
.foot{color:var(--muted);font-size:13px;margin-top:32px}
a.dish{display:block;border:1px solid #ebebeb;border-radius:12px;padding:13px 16px;margin:0 0 8px;color:var(--ink);text-decoration:none;font-weight:600}
a.dish span{color:var(--muted);font-weight:400;font-size:13.5px}
"""


def slug(dish):
    s = dish.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def cap(dish):
    return dish[:1].upper() + dish[1:]


def weight(s):
    if s.get("rating") is None:
        return (2, 0.0)
    c = s.get("rating_count") or 0
    if s.get("rating_source") == "venue":
        c = min(c, 10)
    w = (s["rating"] * c + 3.9 * 25) / (c + 25)
    return (1 if s.get("rating_source") == "venue" else 0, -w)


def rating_text(s):
    if s.get("rating") is None:
        return "No rating yet"
    if s.get("rating_source") == "venue":
        return "★ %.1f centre rating" % s["rating"]
    rc = s.get("rating_count")
    return "★ %.1f%s" % (s["rating"], (" (%d reviews)" % rc) if rc else "")


def dish_page(dish, stalls, venues_by_id):
    sl = slug(dish)
    url = "%s/dish/%s/" % (SITE, sl)
    vcount = len({s["venue_id"] for s in stalls})
    desc = ("%d stalls sell %s across %d hawker centres in Singapore. "
            "See every stall on the map with its Google rating."
            % (len(stalls), dish, vcount))
    top = sorted(stalls, key=weight)[:12]
    items = []
    for s in top:
        v = venues_by_id.get(s["venue_id"], {})
        items.append(
            "<li><p class='nm'>%s</p><p class='rt'><span class='star'></span>%s</p>"
            "<p class='vn'>%s%s</p></li>"
            % (html.escape(s["name"] or "Unnamed stall"),
               html.escape(rating_text(s).replace("★ ", "")),
               html.escape(v.get("name", "")),
               (" " + html.escape(s["unit"])) if s.get("unit") else ""))
    # rating_text already carries the star glyph via CSS-less fallback:
    items = [i.replace("<span class='star'></span>", "★ ") for i in items]
    app_link = "%s/?dish=%s" % (SITE, urllib.parse.quote(dish))
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s in Singapore · HawkerWhere</title>
<meta name="description" content="%s">
<link rel="canonical" href="%s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="HawkerWhere">
<meta property="og:title" content="%s in Singapore">
<meta property="og:description" content="%s">
<meta property="og:url" content="%s">
<style>%s</style>
</head>
<body>
<main>
<a class="brand" href="%s/">HawkerWhere</a>
<p class="tag">Your local dish companion</p>
<h1>%s in Singapore</h1>
<p class="sub">%d stalls across %d hawker centres. Ratings shown are each stall's own Google rating; centre ratings are labelled.</p>
<a class="cta" href="%s">See them on the map</a>
<ol>
%s
</ol>
<p class="foot">Top stalls by rating, small samples adjusted. Open the map for the full list.</p>
</main>
</body>
</html>
""" % (cap(dish), html.escape(desc, quote=True), url,
       cap(dish), html.escape(desc, quote=True), url, CSS, SITE,
       cap(dish), len(stalls), vcount, app_link, "\n".join(items))


def main():
    with open(os.path.join(ROOT, "data", "stalls.json")) as f:
        d = json.load(f)
    venues_by_id = {v["id"]: v for v in d["venues"]}
    by_dish = {}
    for s in d["stalls"]:
        if s.get("author_manual"):
            continue
        if s.get("dish"):
            by_dish.setdefault(s["dish"], []).append(s)

    dish_dir = os.path.join(ROOT, "dish")
    os.makedirs(dish_dir, exist_ok=True)
    urls = [SITE + "/", SITE + "/dish/"]
    index_items = []
    made = 0
    for dish in d["taxonomy"]:
        stalls = by_dish.get(dish, [])
        if not stalls:
            continue
        sl = slug(dish)
        path = os.path.join(dish_dir, sl)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "index.html"), "w") as f:
            f.write(dish_page(dish, stalls, venues_by_id))
        urls.append("%s/dish/%s/" % (SITE, sl))
        index_items.append(
            "<a class='dish' href='/dish/%s/'>%s <span>%d stalls</span></a>"
            % (sl, html.escape(cap(dish)), len(stalls)))
        made += 1

    index_html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All dishes · HawkerWhere</title>
<meta name="description" content="Every dish on HawkerWhere, from chicken rice to zi char, with the stalls that sell each one across Singapore.">
<link rel="canonical" href="%s/dish/">
<style>%s</style>
</head>
<body>
<main>
<a class="brand" href="%s/">HawkerWhere</a>
<p class="tag">Your local dish companion</p>
<h1>All dishes</h1>
<p class="sub">Pick a dish to see the stalls, or open the map and search.</p>
%s
</main>
</body>
</html>
""" % (SITE, CSS, SITE, "\n".join(index_items))
    with open(os.path.join(dish_dir, "index.html"), "w") as f:
        f.write(index_html)

    sm = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
          "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"]
    sm += ["<url><loc>%s</loc></url>" % u for u in urls]
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w") as f:
        f.write("\n".join(sm) + "\n")
    with open(os.path.join(ROOT, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE)
    print("dish pages:", made, "| sitemap urls:", len(urls))


if __name__ == "__main__":
    main()
