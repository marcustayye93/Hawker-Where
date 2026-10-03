#!/usr/bin/env python3
"""Classify each SFA stall's specialty dish from its trade name.

Reads data/sfa_raw.json, writes data/stalls_classified.json (stall rows with
dish, dish_confidence, unit, postal, venue_id=null) and data/review_queue.json
(ambiguous rows for human review).

One-stall-one-dish rule: each stall has exactly one specialty dish, parsed
from its trade name. Matching stages, in order:
  1. beverage-only check (drinks stalls)
  2. brand rules (exact chain names with no dish word, per Marcus 2 Oct)
  3. alias phrases (specific dishes; multiple hits -> name-pass decides)
  4. ordered fallback buckets (zi char, dessert, roast, kueh, named noodles,
     kopi-teh stalls) with a noodle guard on the zi char rule
  5. single distinctive fragments (medium confidence)
  6. Marcus's ordered name-pass (his 2 Oct rule doc): first high hit is the
     dish, the rest are recorded as secondary hits
Medium-confidence rules from the same doc form a separate "cuisine"
dimension (Thai, Malay / Muslim, Seafood...), stored on every stall.

Bare "seafood" / "hai xian" names with no other signal are parked in the
review queue tagged "seafood_untyped" (zi char vs soup, human call).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

TAXONOMY = [
    "chicken rice", "char kway teow", "hokkien mee", "laksa", "bak chor mee",
    "wanton mee", "prawn mee", "mee siam", "mee rebus", "lor mee",
    "bak kut teh", "fish soup", "ban mian", "yong tau foo", "roti prata",
    "nasi lemak", "nasi padang", "nasi briyani", "murtabak", "thosai",
    "satay", "oyster omelette", "carrot cake", "popiah", "kueh pie tee",
    "western food",
    "chee cheong fun", "porridge and congee", "duck rice", "kway chap",
    "chwee kueh", "tutu kueh", "putu piring", "rojak", "tau huay",
    "cheng tng", "ice kacang", "cendol", "sugarcane juice", "kopi and teh",
    "mixed vegetable rice", "zhi char", "claypot rice", "thunder tea rice",
    "fishball noodles", "ngoh hiang",
    "dumplings", "dim sum", "you tiao", "fried snacks", "pancake",
    "dessert", "roast meats", "mutton soup", "pig organ soup",
    "herbal soup", "mala", "kueh", "curry puff", "otah", "cuttlefish",
    "steamboat", "hor fun", "la mian", "kolo mee",
    # Name-pass categories added 2 Oct (Marcus's ordered rule set).
    "beer", "juice", "fruit stall", "bakery", "goreng pisang",
    "indian snacks", "spring roll", "curry chicken", "ayam penyet",
    "beef noodle", "turtle soup", "spinach soup", "seafood soup",
    "steamed fish", "bee hoon", "claypot", "fried rice", "mee goreng",
    "kacang pool", "kebab", "pho", "salad", "lu wei", "pao fan",
    "pork rib", "sup tulang", "bakso", "ramen",
]

# Alias / colloquial phrase -> dish. Checked before single-keyword matching.
ALIASES = {
    "hainanese chicken": "chicken rice",
    "soya sauce chicken": "chicken rice",
    "soy sauce chicken": "chicken rice",
    "chicken rice": "chicken rice",
    "char kway teow": "char kway teow",
    "char kuay teow": "char kway teow",
    "fried kway teow": "char kway teow",
    "hokkien mee": "hokkien mee",
    "hokkien noodle": "hokkien mee",
    "laksa": "laksa",
    "bak chor mee": "bak chor mee",
    "minced meat noodle": "bak chor mee",
    "mee pok": "bak chor mee",
    "wanton mee": "wanton mee",
    "wanton noodle": "wanton mee",
    "wonton noodle": "wanton mee",
    "wan ton noodle": "wanton mee",
    "wonton mee": "wanton mee",
    "wan ton mee": "wanton mee",
    "prawn mee": "prawn mee",
    "prawn noodle": "prawn mee",
    "hee kiaw": "prawn mee",
    "mee siam": "mee siam",
    "mee rebus": "mee rebus",
    "lor mee": "lor mee",
    "bak kut teh": "bak kut teh",
    "bak kut": "bak kut teh",
    "fish soup": "fish soup",
    "sliced fish": "fish soup",
    "fish head": "fish soup",
    "fishhead": "fish soup",
    "yu tang": "fish soup",
    "ban mian": "ban mian",
    "pan mee": "ban mian",
    "you mian": "ban mian",
    "yong tau foo": "yong tau foo",
    "yong tau fu": "yong tau foo",
    "yong tou fu": "yong tau foo",
    "yong dou fu": "yong tau foo",
    "yong tow foo": "yong tau foo",
    "yong tau": "yong tau foo",
    "niang dou fu": "yong tau foo",
    "niang tou fu": "yong tau foo",
    "roti prata": "roti prata",
    "prata": "roti prata",
    "nasi lemak": "nasi lemak",
    "nasi padang": "nasi padang",
    "nasi briyani": "nasi briyani",
    "nasi biryani": "nasi briyani",
    "briyani": "nasi briyani",
    "biryani": "nasi briyani",
    "murtabak": "murtabak",
    "mutabak": "murtabak",
    "western": "western food",
    "western food": "western food",
    "western cuisine": "western food",
    "pasta": "western food",
    "spaghetti": "western food",
    "chicken chop": "western food",
    "fish and chips": "western food",
    "fish & chips": "western food",
    "lamb chop": "western food",
    "pork chop": "western food",
    "steak": "western food",
    "thosai": "thosai",
    "dosa": "thosai",
    "tosai": "thosai",
    "satay": "satay",
    "sate ": "satay",
    "oyster omelette": "oyster omelette",
    "orh luak": "oyster omelette",
    "or lua": "oyster omelette",
    "oyster cake": "oyster omelette",
    "carrot cake": "carrot cake",
    "chai tow kway": "carrot cake",
    "chai tau kway": "carrot cake",
    "popiah": "popiah",
    "kueh pie tee": "kueh pie tee",
    "kueh pietee": "kueh pie tee",
    "chee cheong fun": "chee cheong fun",
    "chee cheung fun": "chee cheong fun",
    "cheung fun": "chee cheong fun",
    "porridge": "porridge and congee",
    "congee": "porridge and congee",
    "teochew porridge": "porridge and congee",
    "zhou pin": "porridge and congee",
    "bubur cha cha": "dessert",
    "bubur": "porridge and congee",
    "duck rice": "duck rice",
    "duck noodle": "duck rice",
    "duck porridge": "duck rice",
    "braised duck": "duck rice",
    "kway chap": "kway chap",
    "chwee kueh": "chwee kueh",
    "water rice cake": "chwee kueh",
    "tutu kueh": "tutu kueh",
    "putu piring": "putu piring",
    "rojak": "rojak",
    "tau huay": "tau huay",
    "dou hua": "tau huay",
    "bean curd": "tau huay",
    "dou jiang": "tau huay",
    "soyabean curd": "tau huay",
    "soya bean curd": "tau huay",
    "cheng tng": "cheng tng",
    "ching teng": "cheng tng",
    "ice kacang": "ice kacang",
    "ais kacang": "ice kacang",
    "cendol": "cendol",
    "chendol": "cendol",
    "sugarcane": "sugarcane juice",
    "sugar cane": "sugarcane juice",
    "kopi": "kopi and teh",
    "teh": "kopi and teh",
    "coffee": "kopi and teh",
    "toast": "kopi and teh",
    "kaya toast": "kopi and teh",
    "mixed vegetable rice": "mixed vegetable rice",
    "mixed veg rice": "mixed vegetable rice",
    "mixed vege": "mixed vegetable rice",
    "mixed rice": "mixed vegetable rice",
    "cai png": "mixed vegetable rice",
    "cai fan": "mixed vegetable rice",
    "za cai fan": "mixed vegetable rice",
    "zha cai fan": "mixed vegetable rice",
    "zhu jiao fan": "mixed vegetable rice",
    "jing ji fan": "mixed vegetable rice",
    "economy rice": "mixed vegetable rice",
    "economic rice": "mixed vegetable rice",
    "economical rice": "mixed vegetable rice",
    "economical bee hoon": "mixed vegetable rice",
    "economic bee hoon": "mixed vegetable rice",
    "econ fried bee hoon": "mixed vegetable rice",
    "econ bee hoon": "mixed vegetable rice",
    "chap chye png": "mixed vegetable rice",
    "vegetarian": "mixed vegetable rice",
    "zhi char": "zhi char",
    "zi char": "zhi char",
    "tze char": "zhi char",
    "claypot rice": "claypot rice",
    "thunder tea rice": "thunder tea rice",
    "lui cha": "thunder tea rice",
    "fishball noodle": "fishball noodles",
    "fish ball noodle": "fishball noodles",
    "fish cake": "fishball noodles",
    "ngoh hiang": "ngoh hiang",
    "wu xiang": "ngoh hiang",
    "five spice": "ngoh hiang",
    # Dumplings (Marcus 2 Oct: keep literal; pau/bao/dim sum is separate)
    "xiao long bao": "dumplings",
    "rice dumpling": "dumplings",
    "dumpling": "dumplings",
    "gyoza": "dumplings",
    "bak chang": "dumplings",
    # Dim sum family (pau / bao / dian xin). Chee cheong fun stays its own dish.
    "dim sum": "dim sum",
    "dimsum": "dim sum",
    "tim sum": "dim sum",
    "dian xin": "dim sum",
    "pau": "dim sum",
    "bao": "dim sum",
    # You tiao (brand Xi De Li is in BRAND_RULES)
    "you tiao": "you tiao",
    "youtiao": "you tiao",
    "pancake": "pancake",
    "mutton soup": "mutton soup",
    "soup kambing": "mutton soup",
    "pig organ": "pig organ soup",
    "pig s organ": "pig organ soup",
    "lao huo tang": "herbal soup",
    "huo tang": "herbal soup",
    "herbal soup": "herbal soup",
    "black chicken": "herbal soup",
    "mala": "mala",
    "ma la": "mala",
    "xiang guo": "mala",
    "curry puff": "curry puff",
    "epok": "curry puff",
    "otah": "otah",
    "otak": "otah",
    "cuttlefish": "cuttlefish",
    "steamboat": "steamboat",
    "hot pot": "steamboat",
    "hotpot": "steamboat",
}

# Brand rules: exact chain names that carry no dish word (Marcus, 2 Oct).
# Checked before alias matching; confidence high.
BRAND_RULES = [
    # Chong Pang Huat = Chinese satay / BBQ chicken wing chain -> zi char bucket
    ("chong pang huat", "zhi char"),
    # Delisnacks chain (you tiao, ham chim peng, goreng pisang) -> fried snacks
    ("delisnack", "fried snacks"),
    ("delisnacks", "fried snacks"),
    ("deli snack", "fried snacks"),
    ("deli snacks", "fried snacks"),
    # Xi De Li = you tiao chain since the 1920s
    ("xi de li", "you tiao"),
]

# Distinctive single-word fragments -> dish (medium confidence only,
# and never when a stronger match already fired).
FRAGMENTS = {
    "wanton": "wanton mee",
    "fishball": "fishball noodles",
    "duck": "duck rice",
    "soya": "tau huay",
    "soyabean": "tau huay",
    "soybean": "tau huay",
    "oyster": "oyster omelette",
    "curry rice": "mixed vegetable rice",
    "xia mian": "prawn mee",
    "mee kia": "bak chor mee",
    "mee tai mak": "laksa",
    "char siew": "wanton mee",
}

# Beverage-only names -> "drinks" (not part of the dish taxonomy).
DRINK_WORDS = ("drink", "drinks", "juice", "beverage", "bubble tea")

# Kopi/teh-centric stalls: food phrase missing but beverage named.
BEVERAGE_DISH = "kopi and teh"

# --- Ordered fallback buckets (Marcus, 2 Oct). Medium confidence. ---

# Zi char / BBQ seafood, tight rule. A noodle word anywhere in the name
# vetoes it (Hwa Kee Barbeque Pork Noodle is a noodle stall, not zi char).
ZI_CHAR_WORDS = (
    "bbq", "b b q", "barbeque", "barbecue", "xiao chao", "siao chao",
    "shao kao", "stingray", "lok lok", "lalapot", "chicken wing",
)
NOODLE_GUARD = (
    "noodle", "mee", "kway teow", "kuay teow", "hor fun", "bee hoon",
    "la mian", "lor mee", "laksa", "ban mian", "wanton", "chee cheong",
    "cheung fun",
)

DESSERT_WORDS = (
    "dessert", "tang shui", "tian pin", "ah balling", "peanut soup",
    "grass jelly", "hot and cold", "hot cold", "leng re",
)
ROAST_WORDS = ("shao la", "roast", "roasted")
KUEH_WORDS = ("kueh", "kuih")
NOODLE_NAME_RULES = (
    ("hor fun", "hor fun"),
    ("la mian", "la mian"),
    ("kolo mee", "kolo mee"),
    ("kway teow", "char kway teow"),
    ("kuay teow", "char kway teow"),
)
KOPI_FALLBACK = (
    ("cha shi", "kopi and teh"),
    ("tea stall", "kopi and teh"),
    ("sarabat", "kopi and teh"),
    ("minuman", "kopi and teh"),
    ("drinkstall", "drinks"),
)

# --- Marcus's name-pass (2 Oct, ordered rules doc) ---
# Applied only when the stages above found no dish. First high hit wins;
# remaining high hits are recorded in "also". Medium rules feed the
# separate "cuisine" field; low (Chinese-cooked-only) is not imported.
# Deviations from his table, his earlier rulings win:
#   - xiao long bao stays "dumplings" (rule 67 maps dim sum only)
#   - kueh / kuih stays the "kueh" dish, not dessert (rule 5)
#   - bak kut teh stays its own dish (rule 29)
#   - mala stays its own dish, not steamboat (rule 62)
#   - white bee hoon folds into "bee hoon" (rule 68; his assignments agree)
#   - char siew / BBQ pork noodle stays "wanton mee" (rule 70)
NAME_PASS_RULES = [
    (["beer"], "beer"),
    (["sugarcane", "sugar cane"], "sugarcane juice"),
    (["soy", "soya", "soyabean", "soyabeancurd", "soy bean", "bean curd",
      "beancurd", "tau huay", "tau huey", "dou hua", "douhua",
      "wobbly"], "tau huay"),
    (["grass jelly", "cincau"], "dessert"),
    (["snow ice", "ice blend", "ice kacang", "ais kacang", "cheng tng",
      "chendol", "ondeh", "tutu cake", "tutu kueh", "dessert", "desert",
      "jelly bean", "tang yuan", "tong yuan", "ice"], "dessert"),
    (["juice", "juz", "air buah", "sarbat", "sarabah", "wedang",
      "smoothie", "fruit ice"], "juice"),
    (["fruit", "fruits", "shui guo"], "fruit stall"),
    (["bakery", "bakehouse", "bakes", "confection", "confectionery",
      "pastry", "pastries", "muffin", "bread", "baguette", "pau",
      "pao dian", "tart", "puff", "crumb"], "bakery"),
    (["coffee", "kopi", "ka fei", "kafei", "kopitiam", "teh tarik",
      "tehtarik", "toast", "yin liao", "drinking stall", "drinking point",
      "tea house", "tea cafe", "happy tea", "cha tan"], "kopi and teh"),
    (["you tiao", "youtiao", "fried dough"], "you tiao"),
    (["chwee kueh", "chwee kuey"], "chwee kueh"),
    (["chee cheong fun", "chee cheong", "cheong fun", "chang fen",
      "chee chong fun"], "chee cheong fun"),
    (["carrot cake", "carrot stick", "chai tow", "chye thow", "cai tao",
      "cai tou guo"], "carrot cake"),
    (["ngoh hiang", "ngo hiang", "gor hiong", "prawn cracker",
      "prawn fritter"], "ngoh hiang"),
    (["goreng pisang", "fried banana"], "goreng pisang"),
    (["vadai", "putu mayam", "appam", "apam"], "indian snacks"),
    (["thosai", "dosai", "dosa"], "thosai"),
    (["popiah"], "popiah"),
    (["otah", "otak"], "otah"),
    (["spring roll", "springroll"], "spring roll"),
    (["fish cake", "fishcake"], "fishball noodles"),
    (["chicken rice", "hainanese chicken", "soy chicken", "ji fan",
      "qi gu ji", "qi gu ji"], "chicken rice"),
    (["curry chicken"], "curry chicken"),
    (["ayam penyet", "nasi ayam", "ayam bakar", "penyet"], "ayam penyet"),
    (["duck rice", "braised duck", "roasted duck", "roast duck", "lu ya",
      "duck noodle", "duck porridge"], "duck rice"),
    (["kway chap", "kuay chap", "kwap chap"], "kway chap"),
    (["pig organ", "pigs organ", "pig s organ", "viscera",
      "zhu shi"], "pig organ soup"),
    (["turtle soup"], "turtle soup"),
    (["mutton soup", "sup kambing", "yang rou", "mutton"], "mutton soup"),
    (["herbal soup"], "herbal soup"),
    (["spinach soup"], "spinach soup"),
    (["fish soup", "fish porridge", "yu tang"], "fish soup"),
    (["seafood soup"], "seafood soup"),
    (["steamed fish", "steam fish"], "steamed fish"),
    (["ban mian", "ban main", "pan mee", "mee hoon kueh", "mee hoon kway",
      "mian fen guo", "you mian"], "ban mian"),
    (["laksa"], "laksa"),
    (["prawn mee", "prawn noodle", "har mee", "hae mee",
      "shrimp noodle"], "prawn mee"),
    (["lor mee", "lormee"], "lor mee"),
    (["bak chor", "minced meat", "minced pork", "mushroom minced",
      "rou cuo"], "bak chor mee"),
    (["wanton", "wan tan", "wonton", "yun tun"], "wanton mee"),
    (["fish ball", "fishball", "yu yuan"], "fishball noodles"),
    (["yong tau", "yong tou foo", "yong tau foo"], "yong tau foo"),
    (["beef noodle", "niu rou", "beef king"], "beef noodle"),
    (["kway teow", "kuay teow", "char kway", "guo tiao"], "char kway teow"),
    (["hokkien mee", "hokkien prawn"], "hokkien mee"),
    (["fried oyster", "oyster omelette", "orh luak", "hao jian",
      "oyster"], "oyster omelette"),
    (["fried rice", "nasi goreng", "chao fan"], "fried rice"),
    (["economical", "economic bee", "economic fried", "economic food",
      "economic noodle", "mixed veg", "chap chye", "economy rice",
      "cai fan"], "mixed vegetable rice"),
    (["bee hoon", "beehoon"], "bee hoon"),
    (["nasi lemak"], "nasi lemak"),
    (["nasi padang"], "nasi padang"),
    (["briyani", "biryani", "biriyani", "bryani"], "nasi briyani"),
    (["clay pot", "claypot"], "claypot"),
    (["porridge", "congee", "teochew porridge"], "porridge and congee"),
    (["satay", "sa tay"], "satay"),
    (["rojak"], "rojak"),
    (["mee goreng", "mee goreong"], "mee goreng"),
    (["mee rebus"], "mee rebus"),
    (["mee siam"], "mee siam"),
    (["mee soto", "mee bandung", "lontong"], "mee rebus"),
    (["kacang pool"], "kacang pool"),
    (["prata", "roti"], "roti prata"),
    (["kebab", "shawarma", "shwarma"], "kebab"),
    (["pho"], "pho"),
    (["hot pot", "hotpot", "steamboat", "huo guo"], "steamboat"),
    (["salad"], "salad"),
    (["pasta", "pizza", "burger", "sandwich", "quesadilla", "bento",
      "brunch", "italian", "steak"], "western food"),
    (["lei cha", "thunder tea"], "thunder tea rice"),
    (["lu wei", "lor bak", "lu zhi", "braised"], "lu wei"),
    (["dim sum", "sheng jian"], "dim sum"),
    (["pao fan"], "pao fan"),
    (["barbeque pork", "bbq pork", "char siew", "cha shao"], "wanton mee"),
    (["pork rib"], "pork rib"),
    (["tulang"], "sup tulang"),
    (["bakso"], "bakso"),
    (["ramen"], "ramen"),
    (["jia chang", "home cook"], "zhi char"),
]

# Medium rules -> cuisine bucket (separate dimension, not a dish).
CUISINE_RULES = [
    (["thai", "tom yum", "som tum", "pad thai"], "Thai"),
    (["japanese", "udon", "yakitori", "donburi"], "Japanese"),
    (["korean"], "Korean"),
    (["vietnam", "vietnamese", "viet fusion"], "Vietnamese"),
    (["indonesian", "indonesia", "warung"], "Indonesian"),
    (["nyonya", "nonya", "peranakan"], "Peranakan"),
    (["hakka"], "Hakka"),
    (["tandoor", "tiffin", "chettinad", "punjabi", "mughlai", "lahori",
      "north indian", "pakistan", "pakistani", "indian food",
      "indian muslim", "indian cuisine", "tamil", "ceylonese", "masala",
      "dhaba", "banana leaf", "indian"], "Indian"),
    (["muslim", "malay", "warong", "selera", "dapur", "bismillah",
      "nasi campur", "halal"], "Malay / Muslim"),
    (["hajjah", "hajah", "haji", "hjh", "mak", "wak", "aminah", "fatimah",
      "abdul", "mohamed", "muhammad"], "Malay / Muslim"),
    (["vegetarian", "veggie"], "Vegetarian"),
    (["seafood", "hai xian", "la xie", "spicy crab", "crab"], "Seafood"),
    (["grill", "bak kwa"], "Grill / BBQ"),
    (["teochew", "teo chew", "teochow", "hainan", "cantonese", "hong kong",
      "hongkong", "sichuan", "szechuan", "beijing", "tianjin", "taiwan",
      "macau", "fuzhou", "dongbei", "dong bei", "yunnan", "chaozhou",
      "chaoshan", "guangzhou"], "Chinese regional"),
    (["noodle", "noodles", "mian", "mian shi", "mian guan",
      "mian zhuang"], "Noodle (unspecified)"),
    (["soup"], "Soup (unspecified)"),
    (["chicken"], "Chicken (unspecified)"),
    (["cafe", "cafeteria", "eating house"], "Cafe"),
    (["snack", "snacks", "xiao chi", "xiao chu"], "Snacks"),
]

# Bare generic signboards carry no signal even if a loose pattern hits.
GENERIC_NAMES = {
    "cooked food", "cook food", "mei shi", "shu shi", "xiao chi",
    "xiao chu", "gourmet", "cuisine", "delicacy", "delicacies",
    "no signboard", "no name", "to be updated",
}


def normalize(name):
    n = (name or "").lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def plural_pattern(phrase):
    """Token-aware regex: each word tolerates a plural 's' (words already
    ending in 's' match as-is, so 'grass' can match)."""
    parts = []
    for w in phrase.split():
        w = w.strip()
        if not w:
            continue
        parts.append(re.escape(w) if w.endswith("s") else re.escape(w) + r"(?:s)?")
    return r"\s+".join(parts)


def phrase_in(phrase, normal):
    return re.search(r"(?<![a-z0-9])" + plural_pattern(phrase) + r"(?![a-z0-9])",
                     normal) is not None


def _zi_char(normal):
    if any(phrase_in(g, normal) for g in NOODLE_GUARD):
        return False
    return any(phrase_in(w, normal) for w in ZI_CHAR_WORDS)


def _fallback(normal):
    """Ordered fallback buckets -> (dish, 'medium') or (None, None)."""
    if _zi_char(normal):
        return "zhi char", "medium"
    if any(phrase_in(w, normal) for w in DESSERT_WORDS):
        return "dessert", "medium"
    if any(phrase_in(w, normal) for w in ROAST_WORDS):
        return "roast meats", "medium"
    if any(phrase_in(w, normal) for w in KUEH_WORDS):
        return "kueh", "medium"
    for phrase, dish in NOODLE_NAME_RULES:
        if phrase_in(phrase, normal):
            return dish, "medium"
    for phrase, dish in KOPI_FALLBACK:
        if phrase_in(phrase, normal):
            return dish, "medium"
    return None, None


def _name_pass(normal):
    """Marcus's ordered high rules. Returns (primary_dish, also_dishes)."""
    hits = []
    for phrases, dish in NAME_PASS_RULES:
        if any(phrase_in(p, normal) for p in phrases):
            if dish not in hits:
                hits.append(dish)
    if not hits:
        return None, []
    return hits[0], hits[1:]


def _cuisine(normal):
    for phrases, label in CUISINE_RULES:
        if any(phrase_in(p, normal) for p in phrases):
            return label
    return None


def classify(name):
    """Return (dish, confidence, candidates, cuisine, also, dish_source).

    candidates is only set when a stall is genuinely ambiguous; cuisine is
    Marcus's medium-confidence bucket dimension; also lists secondary dish
    hits from his name-pass.
    """
    if not name or name.strip().upper() in ("NA", "(NO SIGNBOARD)", "NO SIGNBOARD"):
        return None, None, [], None, [], None
    normal = normalize(name)
    if not normal or normal in GENERIC_NAMES:
        return None, None, [], None, [], None

    cuisine = _cuisine(normal)
    dish, conf, candidates = _classify_main(name, normal)
    if dish == "review":
        # Ambiguous to the main parser: Marcus's ordered rules pick the
        # primary; the rest ride along as secondary hits.
        primary, also = _name_pass(normal)
        if primary:
            rest = [d for d in candidates if d != primary and d not in also]
            return primary, "high", [], cuisine, also + rest, "name_pass"
        return None, None, candidates, cuisine, [], None
    if dish:
        return dish, conf, [], cuisine, [], "name"

    # Main stage found nothing: fall to Marcus's ordered name-pass.
    primary, also = _name_pass(normal)
    if primary:
        return primary, "high", [], cuisine, also, "name_pass"
    return None, None, [], cuisine, [], None


def _classify_main(name, normal):
    """Original name parser. Returns (dish, confidence); dish None = nothing."""
    # Beverage-only check first (so "XYZ Drinks" never matches a food dish).
    beverage = any(phrase_in(w, normal) for w in DRINK_WORDS)
    if beverage and not any(
        phrase_in(a, normal) for a, d in ALIASES.items() if d not in (BEVERAGE_DISH, "sugarcane juice")
    ):
        return "drinks", "high", []

    # Brand rules (chains whose names carry no dish word).
    for phrase, dish in BRAND_RULES:
        if phrase_in(phrase, normal):
            return dish, "high", []

    hits = {}
    work = " " + normal + " "
    # Longest alias first, consuming matched spans, so a short alias nested
    # inside a longer one ("teh" in "bak kut teh") cannot fire a second hit.
    for alias, dish in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        if dish is None:
            continue
        m = re.search(r"(?<![a-z0-9])" + plural_pattern(alias) + r"(?![a-z0-9])", work)
        if m:
            hits.setdefault(dish, []).append(alias)
            work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]
    if len(hits) == 1:
        dish = next(iter(hits))
        return dish, "high", []
    if len(hits) > 1:
        # Single-stall-one-dish: ambiguous names go to the review queue.
        return "review", None, sorted(hits.keys())

    # Ordered fallback buckets (zi char, dessert, roast, kueh, noodles, kopi).
    dish, conf = _fallback(normal)
    if dish:
        return dish, conf, []

    # Single distinctive fragment -> medium confidence.
    for frag, dish in FRAGMENTS.items():
        if dish is None or frag is None:
            continue
        if phrase_in(frag, normal):
            return dish, "medium", []

    return None, None, []


UNIT_RE = re.compile(r"#\d+-\d+")
POSTAL_RE = re.compile(r"\b(\d{6})\b")


def extract_unit(address):
    if not address:
        return None
    m = UNIT_RE.search(address)
    if m:
        return m.group(0)
    # Some centres list bare unit numbers ("166 JALAN BESAR 017,BERSEH FOOD CENTRE")
    first = address.split(",")[0]
    m = re.search(r"(?<![\d#])(\d{2,4})(?![\d])$", first.strip())
    if m:
        return "#" + m.group(1)
    return None


def extract_postal(address):
    if not address:
        return None
    ms = POSTAL_RE.findall(address)
    return ms[-1] if ms else None


def main():
    rows = json.loads((DATA / "sfa_raw.json").read_text(encoding="utf-8"))
    stalls = []
    review = []
    for r in rows:
        name = (r.get("businessName") or "").strip()
        address = (r.get("establishmentAddress") or "").strip()
        dish, conf, candidates, cuisine, also, source = classify(name)
        lic = (r.get("licenceNumber") or "").strip()
        grade = (r.get("grades") or "").strip() or None
        if candidates:
            review.append({
                "stall_id": lic,
                "name": name or "Unnamed stall",
                "venue": None,
                "candidate_dishes": candidates,
            })
        # Bare seafood names: park as an untyped review tag (Marcus, 2 Oct).
        if dish is None and name:
            normal = normalize(name)
            if phrase_in("seafood", normal) or phrase_in("hai xian", normal):
                review.append({
                    "stall_id": lic,
                    "name": name,
                    "venue": None,
                    "candidate_dishes": ["seafood_untyped"],
                })
        stalls.append({
            "id": lic,
            "name": name if name and name.upper() != "NA" else "Unnamed stall",
            "unit": extract_unit(address),
            "address": address,
            "postal": extract_postal(address),
            "venue_id": None,
            "dish": dish,
            "dish_confidence": conf,
            "dish_source": source,
            "cuisine": cuisine,
            "also": also or None,
            "rating": None,
            "rating_count": None,
            "rating_source": None,
            "safe_grade": grade,
        })

    (DATA / "stalls_classified.json").write_text(
        json.dumps(stalls, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "review_queue.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")

    total = len(stalls)
    hi = sum(1 for s in stalls if s["dish_confidence"] == "high")
    med = sum(1 for s in stalls if s["dish_confidence"] == "medium")
    un = sum(1 for s in stalls if not s["dish"])
    print(f"total {total} | high {hi} | medium {med} | unclassified {un} | review {len(review)}")
    print(f"with unit: {sum(1 for s in stalls if s['unit'])} | real names: {sum(1 for s in stalls if s['name'] != 'Unnamed stall')}")
    from collections import Counter
    print("unclassified sample:", Counter(s["name"] for s in stalls if not s["dish"]).most_common(10))
    print("drinks:", sum(1 for s in stalls if s["dish"] == "drinks"))
    print("dish counts:", Counter(s["dish"] for s in stalls if s["dish"]).most_common(70))


if __name__ == "__main__":
    main()
