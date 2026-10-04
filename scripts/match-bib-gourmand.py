#!/usr/bin/env python3
"""Match the Michelin Bib Gourmand 2025 list to our SFA stall register.

Reads the 97-entry list (name + location hint, from the CNA Lifestyle
publication of the Michelin Guide Singapore 2026 selection, 28 Jul 2026), scores
candidate stalls by normalized name overlap and venue match, and
prints a review table. It changes nothing: the human picks the IDs.
"""
import json
import re

BIB = [
    ("Boon Keng Road Fish Head Bee Hoon", "Boon Keng"),
    ("Hup Kee Fried Oyster Omelette", "Newton Food Centre"),
    ("Jia Xiang", "Redhill Market"),
    ("King of Laksa", "Aljunied"),
    ("Rajarani Thosai", "Tampines Round Market & Food Centre"),
    ("Seng Kee Black Chicken Herbal Soup", "Kaki Bukit 511 Market & Food Centre"),
    ("Tian Nan Xing Minced Pork Noodle", "Kaki Bukit 511 Market & Food Centre"),
    ("Xiangyee", ""),
    ("Xiu Ji Ikan Bilis Yong Tau Fu", "Chinatown Complex Market & Food Centre"),
    ("Yi Pin Wei Braised Duck Kway Chap", "Tampines Round Market & Food Centre"),
    ("A Noodle Story", "Amoy Street Food Centre"),
    ("Adam Rd Noo Cheng Big Prawn Noodle", "Adam Food Centre"),
    ("Alliance Seafood", "Newton Food Centre"),
    ("Anglo Indian", "Shenton Way"),
    ("Ar Er Soup", "ABC Brickworks Market & Food Centre"),
    ("Bahrakath Mutton Soup", "Adam Food Centre"),
    ("Beach Road Fish Head Bee Hoon", "Whampoa Makan Place"),
    ("Bismillah Biryani", "Little India"),
    ("Boon Tong Kee", "Balestier Road"),
    ("Chai Chuan Tou Yang Rou Tang", "115 Bukit Merah View Market & Hawker Centre"),
    ("Chef Kang's Noodle House", ""),
    ("Cheok Kee", "Geylang Bahru Market & Food Centre"),
    ("Chey Sua Carrot Cake", "127 Toa Payoh West Market & Food Centre"),
    ("Chuan Kee Boneless Braised Duck", "20 Ghim Moh Road Market & Food Centre"),
    ("Cumi Bali", ""),
    ("Da Shi Jia Big Prawn Mee", ""),
    ("Delhi Lahori", "Tekka Centre"),
    ("Dudu Cooked Food", "Jurong West 505 Market & Food Centre"),
    ("Fei Fei Roasted Noodle", "Yuhua Village Market and Food Centre"),
    ("Fico", ""),
    ("Fu Ming Cooked Food", "Redhill Market"),
    ("Hai Nan Xing Zhou Beef Noodle", "Kim Keat Palm Market & Food Centre"),
    ("Hai Nan Zai", "Chong Pang Market and Food Centre"),
    ("Han Kee", "Amoy Street Food Centre"),
    ("Heng", "Newton Food Centre"),
    ("Heng Heng Cooked Food", "Yuhua Village Market and Food Centre"),
    ("Heng Kee", "Hong Lim Market and Food Centre"),
    ("Hong Heng Fried Sotong Prawn Mee", "Tiong Bahru Market"),
    ("Hong Kong Yummy Soup", "Alexandra Village Food Centre"),
    ("Hoo Kee Bak Chang", "Amoy Street Food Centre"),
    ("Hui Wei Chilli Ban Mian", "Geylang Bahru Market & Food Centre"),
    ("Indocafe", ""),
    ("J2 Famous Crispy Curry Puff", "Amoy Street Food Centre"),
    ("Jalan Sultan Prawn Mee", ""),
    ("Jason Penang Cuisine", "ABC Brickworks Market & Food Centre"),
    ("Ji De Lai Hainanese Chicken Rice", "Chong Pang Market and Food Centre"),
    ("Ji Ji Noodle House", "Hong Lim Market and Food Centre"),
    ("Jian Bo Tiong Bahru Shui Kueh", "Jurong West 505 Market & Food Centre"),
    ("Joo Siah Bak Koot Teh", "Kai Xiang Food Centre"),
    ("Jungle", ""),
    ("Kelantan Kway Chap Pig Organ Soup", "Berseh Food Centre"),
    ("Kitchenman Nasi Lemak", ""),
    ("Koh Brother Pig's Organ Soup", "Tiong Bahru Market"),
    ("Kok Sen", ""),
    ("Kotuwa", ""),
    ("Kwang Kee Teochew Fish Porridge", "Newton Food Centre"),
    ("Kwee Heng", "Newton Food Centre"),
    ("Lagnaa", ""),
    ("Lai Heng Handmade Teochew Kueh", "Yuhua Market & Hawker Centre"),
    ("Lao Fu Zi Fried Kway Teow", "Old Airport Road Food Centre"),
    ("Lian He Ben Ji Claypot", "Chinatown Complex Market & Food Centre"),
    ("Lixin Teochew Fishball Noodles", "Kim Keat Palm Market & Food Centre"),
    ("Margaret Drive Sin Kee Chicken Rice", "40 Holland Drive"),
    ("MP Thai", "Vision Exchange"),
    ("Muthu's Curry", ""),
    ("Na Na Curry", "115 Bukit Merah View Market & Hawker Centre"),
    ("Nam Sing Hokkien Fried Mee", "Old Airport Road Food Centre"),
    ("New Lucky Claypot Rice", "Holland Drive Market & Food Centre"),
    ("No.18 Zion Road Fried Kway Teow", "Zion Riverside Food Centre"),
    ("Outram Park Fried Kway Teow Mee", "Hong Lim Market and Food Centre"),
    ("Ru Ji Kitchen", "Holland Drive Market & Food Centre"),
    ("Selamat Datang Warong Pak Sapari", "Adam Food Centre"),
    ("Sik Bao Sin", ""),
    ("Sin Heng Claypot Bak Koot Teh", ""),
    ("Sin Huat Seafood Restaurant", ""),
    ("Singapore Fried Hokkien Mee", "Whampoa Makan Place"),
    ("Soh Kee Cooked Food", "Jurong West 505 Market & Food Centre"),
    ("Song Fa Bak Kut Teh", "New Bridge Road"),
    ("Song Fish Soup", "Clementi 448 Food Centre"),
    ("Song Kee Teochew Fish Porridge", "Newton Food Centre"),
    ("Soon Huat", "North Bridge Road Market & Food Centre"),
    ("Spinach Soup", "Geylang Bahru Market & Food Centre"),
    ("Tai Seng Fish Soup", "Taman Jurong Market & Food Centre"),
    ("Tai Wah Pork Noodle", "Hong Lim Market and Food Centre"),
    ("The Blue Ginger", ""),
    ("The Coconut Club", "Beach Road"),
    ("Tian Tian Hainanese Chicken Rice", "Maxwell Food Centre"),
    ("Tiong Bahru Hainanese Boneless Chicken Rice", "Tiong Bahru Market"),
    ("To-Ricos Kway Chap", "Old Airport Road Food Centre"),
    ("True Blue Cuisine", ""),
    ("Un-Yang-Kor-Dai", ""),
    ("Whole Earth", ""),
    ("Wok Hei Hor Fun", "Redhill Food Centre"),
    ("Yhingthai Palace", ""),
    ("Yong Chun Wan Ton Noodle", "115 Bukit Merah View Market & Hawker Centre"),
    ("Zai Shun Curry Fish Head", ""),
    ("Zhi Wei Xian Zion Road Big Prawn Noodle", "Zion Riverside Food Centre"),
    ("Zhup Zhup", ""),
]

STOP = {"the", "and", "food", "centre", "center", "market", "hawker", "cooked",
        "stall", "restaurant", "pte", "ltd", "sg", "singapore"}


def norm(s):
    s = s.lower().replace("&", " and ").replace("'", "").replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in STOP)


def toks(s):
    return set(norm(s).split())


def main():
    d = json.load(open("data/stalls.json"))
    venues = {v["id"]: v for v in d["venues"]}
    stalls = [s for s in d["stalls"] if s["name"] and s["name"] != "Unnamed stall"]

    for bib_name, bib_venue in BIB:
        bt = toks(bib_name)
        vt = toks(bib_venue)
        scored = []
        for s in stalls:
            st = toks(s["name"])
            if not st:
                continue
            inter = len(bt & st)
            if not inter:
                continue
            name_score = inter / max(1, len(bt))
            venue = venues.get(s["venue_id"], {})
            sv = toks(venue.get("name", ""))
            v_hit = len(vt & sv) / max(1, len(vt)) if vt else 0
            score = name_score * 2 + v_hit
            scored.append((score, name_score, v_hit, s, venue.get("name", "")))
        scored.sort(key=lambda x: -x[0])
        top = scored[:3]
        print(f"\n### {bib_name} [{bib_venue}]")
        for score, ns, vh, s, vname in top:
            print(f"  {score:4.2f} name={ns:.2f} venue={vh:.2f}  {s['id']} | {s['name']} | {vname} | dish={s.get('dish')}")


if __name__ == "__main__":
    main()
