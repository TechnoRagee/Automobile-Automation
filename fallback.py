"""
fallback.py — CarDekho fallback scraper utility

Used by 01/02/03 scripts when CarWale returns empty/missing fields.

CarDekho URL patterns:
  Brand page:  https://www.cardekho.com/{brand_slug}/
  Model page:  https://www.cardekho.com/{brand_slug}/{model_slug}
  Specs page:  https://www.cardekho.com/{brand_slug}/{model_slug}/specs

CarDekho brand slugs mostly match CarWale slugs but some differ:
  maruti-suzuki  -> maruti
  force-motors   -> force
  rolls-royce    -> rollsroyce
  mercedes-benz  -> mercedes-benz  (same)
  land-rover     -> land-rover     (same)
"""

import re
import time
import requests
from bs4 import BeautifulSoup

CARDEKHO_BASE = "https://www.cardekho.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# CarWale slug -> CarDekho slug where they differ
BRAND_SLUG_MAP = {
    "maruti-suzuki": "maruti",
    "force-motors":  "force",
    "rolls-royce":   "rollsroyce",
}

# Upcoming brands (on CarDekho, not yet on CarWale)
UPCOMING_BRANDS = [
    {"brand_slug": "genesis",    "brand_name": "Genesis",    "brand_url": "https://www.cardekho.com/cars/Genesis",    "status": "upcoming"},
    {"brand_slug": "haima",      "brand_name": "Haima",      "brand_url": "https://www.cardekho.com/cars/Haima",      "status": "upcoming"},
    {"brand_slug": "haval",      "brand_name": "Haval",      "brand_url": "https://www.cardekho.com/cars/Haval",      "status": "upcoming"},
    {"brand_slug": "koenigsegg", "brand_name": "Koenigsegg", "brand_url": "https://www.cardekho.com/cars/Koenigsegg", "status": "upcoming"},
    {"brand_slug": "leapmotor",  "brand_name": "Leapmotor",  "brand_url": "https://www.cardekho.com/cars/Leapmotor",  "status": "upcoming"},
    {"brand_slug": "xiaomi",     "brand_name": "Xiaomi",     "brand_url": "https://www.cardekho.com/cars/Xiaomi",     "status": "upcoming"},
]

# Discontinued/expired brands (CarDekho Expired tab)
DISCONTINUED_BRANDS = [
    {"brand_slug": "ashok-leyland",    "brand_name": "Ashok Leyland",    "brand_url": "https://www.cardekho.com/cars/Ashok+Leyland",    "status": "discontinued"},
    {"brand_slug": "austin",           "brand_name": "Austin",           "brand_url": "https://www.cardekho.com/cars/Austin",           "status": "discontinued"},
    {"brand_slug": "cadillac",         "brand_name": "Cadillac",         "brand_url": "https://www.cardekho.com/cars/Cadillac",         "status": "discontinued"},
    {"brand_slug": "caterham",         "brand_name": "Caterham",         "brand_url": "https://www.cardekho.com/cars/Caterham",         "status": "discontinued"},
    {"brand_slug": "chevrolet",        "brand_name": "Chevrolet",        "brand_url": "https://www.cardekho.com/cars/Chevrolet",        "status": "discontinued"},
    {"brand_slug": "chrysler",         "brand_name": "Chrysler",         "brand_url": "https://www.cardekho.com/cars/Chrysler",         "status": "discontinued"},
    {"brand_slug": "conquest",         "brand_name": "Conquest",         "brand_url": "https://www.cardekho.com/cars/Conquest",         "status": "discontinued"},
    {"brand_slug": "daewoo",           "brand_name": "Daewoo",           "brand_url": "https://www.cardekho.com/cars/Daewoo",           "status": "discontinued"},
    {"brand_slug": "datsun",           "brand_name": "Datsun",           "brand_url": "https://www.cardekho.com/cars/Datsun",           "status": "discontinued"},
    {"brand_slug": "dc",               "brand_name": "DC",               "brand_url": "https://www.cardekho.com/cars/DC",               "status": "discontinued"},
    {"brand_slug": "dodge",            "brand_name": "Dodge",            "brand_url": "https://www.cardekho.com/cars/Dodge",            "status": "discontinued"},
    {"brand_slug": "fiat",             "brand_name": "Fiat",             "brand_url": "https://www.cardekho.com/cars/Fiat",             "status": "discontinued"},
    {"brand_slug": "hindustan-motors", "brand_name": "Hindustan Motors", "brand_url": "https://www.cardekho.com/cars/Hindustan+Motors", "status": "discontinued"},
    {"brand_slug": "hummer",           "brand_name": "Hummer",           "brand_url": "https://www.cardekho.com/cars/Hummer",           "status": "discontinued"},
    {"brand_slug": "icml",             "brand_name": "ICML",             "brand_url": "https://www.cardekho.com/cars/ICML",             "status": "discontinued"},
    {"brand_slug": "infiniti",         "brand_name": "Infiniti",         "brand_url": "https://www.cardekho.com/cars/Infiniti",         "status": "discontinued"},
    {"brand_slug": "mahindra-renault", "brand_name": "Mahindra Renault", "brand_url": "https://www.cardekho.com/cars/Mahindra+Renault", "status": "discontinued"},
    {"brand_slug": "mahindra-ssangyong","brand_name": "Mahindra Ssangyong","brand_url": "https://www.cardekho.com/cars/Mahindra+Ssangyong","status": "discontinued"},
    {"brand_slug": "maybach",          "brand_name": "Maybach",          "brand_url": "https://www.cardekho.com/cars/Maybach",          "status": "discontinued"},
    {"brand_slug": "mazda",            "brand_name": "Mazda",            "brand_url": "https://www.cardekho.com/cars/Mazda",            "status": "discontinued"},
    {"brand_slug": "opel",             "brand_name": "Opel",             "brand_url": "https://www.cardekho.com/cars/Opel",             "status": "discontinued"},
    {"brand_slug": "piaggio",          "brand_name": "Piaggio",          "brand_url": "https://www.cardekho.com/cars/Piaggio",          "status": "discontinued"},
    {"brand_slug": "premier",          "brand_name": "Premier",          "brand_url": "https://www.cardekho.com/cars/Premier",          "status": "discontinued"},
    {"brand_slug": "reva",             "brand_name": "Reva",             "brand_url": "https://www.cardekho.com/cars/Reva",             "status": "discontinued"},
    {"brand_slug": "san-motors",       "brand_name": "San Motors",       "brand_url": "https://www.cardekho.com/cars/San+Motors",       "status": "discontinued"},
    {"brand_slug": "sipani",           "brand_name": "Sipani",           "brand_url": "https://www.cardekho.com/cars/Sipani",           "status": "discontinued"},
    {"brand_slug": "smart",            "brand_name": "Smart",            "brand_url": "https://www.cardekho.com/cars/Smart",            "status": "discontinued"},
    {"brand_slug": "studebaker",       "brand_name": "Studebaker",       "brand_url": "https://www.cardekho.com/cars/Studebaker",       "status": "discontinued"},
    {"brand_slug": "subaru",           "brand_name": "Subaru",           "brand_url": "https://www.cardekho.com/cars/Subaru",           "status": "discontinued"},
]


def get_extra_brands():
    """Return combined upcoming + discontinued brand list."""
    return UPCOMING_BRANDS + DISCONTINUED_BRANDS


def cw_to_cd_brand(carwale_slug):
    """Convert CarWale brand slug to CarDekho brand slug."""
    return BRAND_SLUG_MAP.get(carwale_slug, carwale_slug)


def fetch_cd(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"          [CD retry {attempt}] {e}")
            time.sleep(delay * attempt)
    print(f"          [CD FAILED] {url}")
    return None


def soup(html):
    return BeautifulSoup(html, "html.parser")


# ── field extractors for CarDekho specs page ──────────────────────────────

def cd_extract_price(s):
    m = re.search(r'Rs\.?\s*([\d,]+(?:\.\d+)?)\s*(?:Lakh|lakh)', s.get_text(" "))
    if m:
        return f"Rs. {m.group(1)} Lakh"
    return ""


def cd_extract_fuel_type(s):
    txt = s.get_text(" ")
    m = re.search(r'Fuel\s*Type\s*[:\-]?\s*([A-Za-z/ &]+?)(?:\n|,|\.)', txt, re.I)
    if m:
        return m.group(1).strip()
    for fuel in ["Electric", "Petrol", "Diesel", "CNG", "LPG", "Hybrid"]:
        if re.search(rf'\b{fuel}\b', txt, re.I):
            return fuel
    return ""


def cd_extract_transmission(s):
    txt = s.get_text(" ", strip=True)
    patterns = [
    r'Transmission Type\s*[:\-]?\s*(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
    r'Transmission\s*[:\-]?\s*(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
]
    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1).title()
    return ""

    


def cd_extract_engine(s):
    txt = s.get_text(" ")
    m = re.search(r'(\d{3,4}\s*cc)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""


def cd_extract_mileage(s):
    txt = s.get_text(" ", strip=True)

    m = re.search(
        r'(?:Mileage|ARAI Mileage|City Mileage|Claimed Mileage).*?([0-9.]+)\s*kmpl',
        txt,
        re.I
    )

    if not m:
        return ""

    value = float(m.group(1))

    # known bad placeholder
    if abs(value - 49.75) < 0.01:
        return ""

    # unrealistic
    if value > 40:
        return ""

    # EV sanity
    if re.search(r'\bElectric\b', txt, re.I):
        return ""

    return f"{value} kmpl"


def cd_extract_power(s):
    txt = s.get_text(" ", strip=True)

    patterns = [
        r'Max Power\s*([0-9.]+\s*bhp)',
        r'Max Power\s*([0-9.]+\s*PS)',
        r'Max Power\s*([0-9.]+\s*kW)',
        r'Power\s*([0-9.]+\s*bhp)',
        r'Power\s*([0-9.]+\s*PS)',
        r'([\d\.]+\s*bhp)',
        r'([\d\.]+\s*PS)',
    ]

    for p in patterns:
        m = re.search(p, txt, re.I)
        if not m:
            continue

        val = m.group(1).strip()

        # reject charger values
        if re.match(r'^(7\.2|11|22)\s*kW$', val, re.I):
            continue

        return val

    return ""


def cd_extract_torque(s):
    txt = s.get_text(" ")
    m = re.search(r'([\d\.]+\s*Nm)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""


def cd_extract_seating(s):
    txt = s.get_text(" ")
    patterns = [
    r'Seating Capacity\s*[:\-]?\s*(\d+)',
    r'(\d+)\s*Seats?',
        ]

    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1)
    return ""


def cd_extract_airbags(s):
    txt = s.get_text(" ")
    patterns = [
    r'(\d+)\s*Airbags?',
    r'Airbags?\s*[:\-]?\s*(\d+)',
    r'Airbag Count\s*[:\-]?\s*(\d+)',
    ]
    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1)
    return ""


def cd_extract_body_type(s):
    txt = s.get_text(" ", strip=True)

    m = re.search(
    r'Body Type\s*[:\-]?\s*(SUV|Compact SUV|Sedan|Hatchback|Coupe|Convertible|MUV|Crossover)',
    txt,
    re.I
    )

    if not m:
        return ""
    
    return m.group(1)

    # body = m.group(1).strip()

    # VALID = {
    #      "SUV",
    # "Compact SUV",
    # "Sedan",
    # "Hatchback",
    # "Coupe",
    # "Convertible",
    # "MUV",
    # "Crossover",
    # }
    # for v in VALID:
    #     if body.lower() == v.lower():
    #         return v

    # if body in VALID:
    #     return body

    # return ""

# ── main fallback function ────────────────────────────────────────────────

def cardekho_fallback(carwale_data: dict, brand_slug: str, model_slug: str) -> dict:
    """
    Given a dict of fields scraped from CarWale (empty string = missing),
    fetch CarDekho specs page and fill in any empty fields.
    Returns updated dict.
    """
    # Check if any field actually needs filling
    needs_fill = [
        k for k in ["price",
                    "fuel_type",
                    "transmission",
                    "engine",
                    "mileage",
                    "power",
                    "torque",
                    "seating_capacity",
                    "airbags",
                    "body_type",]
        if not carwale_data.get(k)
    ]
    if not needs_fill:
        return carwale_data  # nothing missing, skip CarDekho entirely

    cd_brand = cw_to_cd_brand(brand_slug)
    cd_url   = f"{CARDEKHO_BASE}/{cd_brand}/{model_slug}/specs"
    print(f"          [fallback] {cd_url} (filling: {needs_fill})")

    html = fetch_cd(cd_url)
    if html is None:
        return carwale_data

    s = soup(html)
    title = s.title.text.strip() if s.title else "NO TITLE"
    print("\nURL:", cd_url)
    print("TITLE:", s.title.text if s.title else "NO TITLE")
    print("TITLE:", title)
    if brand_slug.lower() not in title.lower():
        print("WRONG PAGE DETECTED")

    extractors = {
        "price":            cd_extract_price,
        "fuel_type":        cd_extract_fuel_type,
        "transmission":     cd_extract_transmission,
        "engine":           cd_extract_engine,
        "mileage":          cd_extract_mileage,
        "power":            cd_extract_power,
        "torque":           cd_extract_torque,
        "seating_capacity": cd_extract_seating,
        "airbags":          cd_extract_airbags,
        "body_type":        cd_extract_body_type,
    }

    result = dict(carwale_data)
    for field in needs_fill:
        if field in extractors:
            val = extractors[field](s)
            if val:
                result[field] = val
                print(f"          [fallback] filled {field} = {val}")

    time.sleep(1.5)
    result = validate_specs(result)
    return result


def validate_specs(data):
    VALID_FUELS ={
        "Petrol",
    "Diesel",
    "Electric",
    "CNG",
    "LPG",
    "Hybrid"
    }
    fuel_raw = data.get("fuel_type", "").strip()
    if fuel_raw and fuel_raw not in VALID_FUELS:
        data["fuel_type"] = ""

    fuel = data.get("fuel_type", "").lower()

    # EV cleanup
    if "electric" in fuel:
        # data["engine"] = ""
        data["mileage"] = ""

    # Remove charger power values
    power = data.get("power", "")

    if power.lower().endswith("kw"):
        try:
            kw = float(re.findall(r'[\d.]+', power)[0])

            if kw <= 30:
                data["power"] = ""
        except:
            pass

    # Remove fake mileage
    mileage = data.get("mileage", "")

    if mileage:
        if "49.75" in mileage:
            data["mileage"] = ""

        try:
            value = float(re.findall(r'[\d.]+', mileage)[0])

            if value > 40:
                data["mileage"] = ""
        except:
            pass

    return data



# ── CarDekho brand list fallback (for 01_extract_brands.py) ──────────────

def cardekho_get_brands():
    """
    Scrape CarDekho's new cars page for brand list.
    Returns list of dicts: {brand_slug, brand_name, brand_url}
    Only used if CarWale sitemap returns < 30 brands.
    """
    url = f"{CARDEKHO_BASE}/new-cars/"
    print(f"[CD fallback] fetching brand list from {url}")
    html = fetch_cd(url)
    if html is None:
        return []

    s = soup(html)
    pattern = re.compile(r'^/([a-z0-9-]+)/?$')
    brands = {}
    for a in s.find_all("a", href=True):
        href = a["href"].replace(CARDEKHO_BASE, "")
        m = pattern.match(href)
        if not m:
            continue
        slug = m.group(1)
        name = a.get_text(strip=True)
        if name and slug not in brands:
            brands[slug] = {
                "brand_slug": slug,
                "brand_name": name,
                "brand_url": f"{CARDEKHO_BASE}/{slug}/",
            }
    return list(brands.values())


# ── CarDekho model list fallback (for 02_extract_models.py) ──────────────

# CarDekho uses /cars/BrandName format for discontinued brands
# and /brandslug/ for current brands - map known ones
CD_BRAND_PAGE_MAP = {
    "ashok-leyland":     "cars/Ashok+Leyland",
    "austin":            "cars/Austin",
    "cadillac":          "cars/Cadillac",
    "caterham":          "cars/Caterham",
    "chevrolet":         "cars/Chevrolet",
    "chrysler":          "cars/Chrysler",
    "conquest":          "cars/Conquest",
    "daewoo":            "cars/Daewoo",
    "datsun":            "cars/Datsun",
    "dc":                "cars/DC",
    "dodge":             "cars/Dodge",
    "fiat":              "cars/Fiat",
    "hindustan-motors":  "cars/Hindustan+Motors",
    "hummer":            "cars/Hummer",
    "icml":              "cars/ICML",
    "infiniti":          "cars/Infiniti",
    "mahindra-renault":  "cars/Mahindra+Renault",
    "mahindra-ssangyong":"cars/Mahindra+Ssangyong",
    "maybach":           "cars/Maybach",
    "mazda":             "cars/Mazda",
    "opel":              "cars/Opel",
    "piaggio":           "cars/Piaggio",
    "premier":           "cars/Premier",
    "reva":              "cars/Reva",
    "san-motors":        "cars/San+Motors",
    "sipani":            "cars/Sipani",
    "smart":             "cars/Smart",
    "studebaker":        "cars/Studebaker",
    "subaru":            "cars/Subaru",
    "genesis":           "cars/Genesis",
    "haima":             "cars/Haima",
    "haval":             "cars/Haval",
    "koenigsegg":        "cars/Koenigsegg",
    "leapmotor":         "cars/Leapmotor",
    "xiaomi":            "cars/Xiaomi",
}


def cardekho_get_models(brand_slug: str):
    """
    Scrape CarDekho brand page for model links.
    Returns list of dicts: {model_slug, model_url}
    Only used if CarWale returns 0 models for a brand.
    """
    cd_brand = cw_to_cd_brand(brand_slug)

    # Use known path if available, else default slug path
    cd_path = CD_BRAND_PAGE_MAP.get(brand_slug, cd_brand)
    url = f"{CARDEKHO_BASE}/{cd_path}"
    print(f"          [CD fallback] fetching models from {url}")
    html = fetch_cd(url)
    if html is None:
        return []

    s = soup(html)

    # Anchor pattern to the EXACT brand prefix so we never pick up
    # links from other brands or generic nav paths.
    # Matches: /{cd_brand}/{ModelSlug} or /{cd_brand}/{ModelSlug}.htm
    # Does NOT match deeper paths like /{cd_brand}/{model}/specs
    brand_prefix = re.escape(cd_path.split("/")[-1])  # last segment e.g. "Genesis"
    pattern = re.compile(
        r'^(?:https://www\.cardekho\.com)?/'
        + brand_prefix
        + r'/([A-Za-z0-9][A-Za-z0-9_\-]+?)(?:\.htm)?/?$',
        re.IGNORECASE,
    )

    SKIP = {
        "new", "used", "upcoming", "reviews", "videos", "news",
        "compare", "images", "price", "specs", "dealers",
        "emi-calculator", "on-road-price", "offers", "colours",
        "colors", "brochure", "360-view", "service-cost",
        "accessories", "faqs", "finance", "insurance",
    }

    models = {}
    for a in s.find_all("a", href=True):
        href = a["href"].rstrip("/")
        m = pattern.match(href)
        if not m:
            continue
        model_slug = m.group(1).lower().replace("_", "-")
        if model_slug in SKIP:
            continue
        if len(model_slug) < 2:          # block single-char noise
            continue
        if model_slug not in models:
            models[model_slug] = {
                "model_slug": model_slug,
                "model_url": href if href.startswith("http") else f"{CARDEKHO_BASE}{href}",
            }
    time.sleep(1.5)
    return list(models.values())