"""
Phase 3: Extract all variants with full specs from CarWale -> variants.csv

Flow:
  1. Read models.csv
  2. For each model page, extract variant/trim links
  3. For each variant page, scrape:
       brand_name, model_name, variant_name, variant_slug, variant_url,
       price, fuel_type, transmission, engine, mileage, power, torque,
       seating_capacity, airbags, body_type, source_url, scraped_at

Run locally:
    pip install requests beautifulsoup4
    python 03_extract_variants.py
"""

import csv
import os
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from fallback import cardekho_fallback

BASE_URL = "https://www.carwale.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

MODELS_FILE  = "output/models.csv"
OUTPUT_FILE  = "output/variants.csv"
DELAY        = 1.5   # seconds between requests

EXCLUDED_SLUGS = {
    "360-view", "variants", "offers", "similar-cars", "colours", "colors",
    "brochure", "mileage", "reviews", "news", "expert-reviews", "videos",
    "images", "faqs", "automatic", "cng", "diesel", "petrol",
    "specifications", "specs", "features", "price","range",
}
PRICE_IN_RE = re.compile(r"^price-in-")


# ── helpers ──────────────────────────────────────────────────────────────────

def fetch(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"        [retry {attempt}] {e}")
            time.sleep(delay * attempt)
    print(f"        FAILED: {url}")
    return None


def soup(html):
    return BeautifulSoup(html, "html.parser")


def text_after(s, label):
    """Find a tag whose text contains label, return sibling/parent text."""
    tag = s.find(string=re.compile(re.escape(label), re.I))
    if tag:
        parent = tag.parent
        nxt = parent.find_next_sibling()
        if nxt:
            return nxt.get_text(strip=True)
        # sometimes value is in same container, next text node
        full = parent.get_text(" ", strip=True)
        after = full.replace(label, "").strip()
        if after:
            return after
    return ""


def find_text(s, patterns):
    """Try multiple regex patterns on full page text, return first match group 1."""
    text = s.get_text(" ", strip=True)
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip()
    return ""


# ── variant link extraction (from model page) ─────────────────────────────

def get_variant_links(html, brand_slug, model_slug):
    pattern = re.compile(
    r'href="(?:https://www\.carwale\.com)?/'
    + re.escape(brand_slug)
    + r'-cars/'
    + re.escape(model_slug)
    + r'/([a-z0-9-]+)/?"'
)
    seen = {}
    for m in pattern.finditer(html):
        slug = m.group(1)
        if slug in EXCLUDED_SLUGS or PRICE_IN_RE.match(slug):
            continue
        if slug not in seen:
            seen[slug] = f"{BASE_URL}/{brand_slug}-cars/{model_slug}/{slug}/"
    return seen   # {slug: url}


# ── field extraction (from variant page) ──────────────────────────────────

def extract_price(s):
    txt = s.get_text(" ", strip=True)

    # Crore first
    m = re.search(
        r'(?:Rs\.|₹)\s*([\d,\.]+)\s*Crore',
        txt,
        re.I
    )
    if m:
        return f"Rs. {m.group(1)} Crore"

    # Then lakh
    m = re.search(
        r'(?:Rs\.|₹)\s*([\d,\.]+)\s*Lakh',
        txt,
        re.I
    )
    if m:
        return f"Rs. {m.group(1)} Lakh"

    return ""


def extract_fuel_type(s):
    m = re.search(r'Fuel Type\s*([A-Za-z/ &]+?)(?=\n|Engine|Ethanol|$)',
                  s.get_text("\n"), re.I)
    if m:
        return m.group(1).strip()
    # fallback: look for explicit petrol/diesel/cng/electric
    txt = s.get_text(" ")
    for fuel in ["Electric", "Hydrogen", "Petrol", "Diesel", "CNG", "LPG", "Hybrid"]:
        if re.search(rf'\bFuel Type\b.*?\b{fuel}\b', txt, re.I | re.S):
            return fuel
    return ""


def extract_transmission(s):
    txt = s.get_text(" ", strip=True)

    patterns = [
        r'Transmission Type\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
        r'Transmission\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
    ]

    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1).title()

    return ""


def extract_engine(s):
    m = re.search(r'Engine\s+(\d[\d,\.]+\s*cc[^\n]*)', s.get_text("\n"), re.I)
    if m:
        return m.group(1).strip()
    return ""


def extract_mileage(s):
    txt = s.get_text(" ", strip=True)

    m = re.search(
        r'(?:User Reported|Mileage)[:\s]+([\d\.]+)\s*kmpl',
        txt,
        re.I
    )

    if not m:
        return ""

    value = float(m.group(1))

    if value > 40:
        return ""

    return f"{value} kmpl"


def extract_power(s):
    txt = s.get_text(" ", strip=True)

    patterns = [
        r'Max Power[^\d]*([\d\.]+\s*bhp)',
        r'Max Power[^\d]*([\d\.]+\s*PS)',
        r'Max Power[^\d]*([\d\.]+\s*kW)',
    ]

    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1).strip()

    return ""


def extract_torque(s):
    m = re.search(r'Max Torque[^\d]*([\d\.]+\s*Nm)', s.get_text(" "), re.I)
    if m:
        return m.group(1).strip()
    return ""


def extract_seating(s):
    m = re.search(r'Seating Capacity\s+(\d+)\s*Seat', s.get_text(" "), re.I)
    if m:
        return m.group(1)
    return ""


def extract_airbags(s):
    m = re.search(r'(\d+)\s*Airbag', s.get_text(" "), re.I)
    if m:
        return m.group(1)
    return ""


def extract_body_type(s):
    # body type appears in meta description or page text
    txt = s.get_text(" ")
    for body in ["Convertible", "Coupe", "Pickup Truck", "Minivan", "Van",
                 "Station Wagon", "Hatchback", "Sedan", "SUV", "MUV",
                 "Crossover", "Compact SUV"]:
        if re.search(rf'\b{re.escape(body)}\b', txt, re.I):
            return body
    return ""


def scrape_variant(url):
    html = fetch(url)
    if html is None:
        return None
    s = soup(html)
    return {
        "price":            extract_price(s),
        "fuel_type":        extract_fuel_type(s),
        "transmission":     extract_transmission(s),
        "engine":           extract_engine(s),
        "mileage":          extract_mileage(s),
        "power":            extract_power(s),
        "torque":           extract_torque(s),
        "seating_capacity": extract_seating(s),
        "airbags":          extract_airbags(s),
        "body_type":        extract_body_type(s),
    }


# ── main ──────────────────────────────────────────────────────────────────

SPEC_FIELDS = [
    "price", "fuel_type", "transmission", "engine", "mileage",
    "power", "torque", "seating_capacity", "airbags", "body_type",
]

FIELDNAMES = (
    ["brand_name", "model_name", "variant_name", "variant_slug", "variant_url"]
    + SPEC_FIELDS
    + ["data_source", "source_url", "scraped_at"]
)


def load_models():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    models = load_models()
    print(f"Loaded {len(models)} models.")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    total = 0
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, model in enumerate(models, 1):
            brand_slug  = model["brand_slug"]
            brand_name  = model["brand_name"]
            model_slug  = model["model_slug"]
            model_name  = model["model_name"]
            model_url   = model["model_url"]

            print(f"[{i}/{len(models)}] {brand_name} {model_name}")

            html = fetch(model_url)
            if html is None:
                continue

            variant_links = get_variant_links(html, brand_slug, model_slug)
            print(f"  {len(variant_links)} variant(s) found")

            for v_slug, v_url in variant_links.items():
                print(f"    -> {v_url}")
                data = scrape_variant(v_url)
                if data is None:
                    data = {}

                # Track missing BEFORE fallback fills them
                missing_before = [k for k in SPEC_FIELDS if not data.get(k)]

                # Fill missing fields from CarDekho
                data = cardekho_fallback(data, brand_slug, model_slug)

                if not missing_before:
                    data_source = "carwale"
                elif all(data.get(k) for k in SPEC_FIELDS):
                    data_source = "carwale+cardekho"
                else:
                    data_source = "carwale+cardekho(partial)"
                
                variant_slug_name = v_slug.lower()
                if model_slug.lower() == "vanquish":
                    data["body_type"] = "Coupe"

                elif "volante" in variant_slug_name:
                    data["body_type"] = "Convertible"

                elif "convertible" in variant_slug_name:    
                    data["body_type"] = "Convertible"

                elif "coupe" in variant_slug_name:
                    data["body_type"] = "Coupe"

                writer.writerow({
                    "brand_name":       brand_name,
                    "model_name":       model_name,
                    "variant_name":     v_slug.replace("-", " ").title(),
                    "variant_slug":     v_slug,
                    "variant_url":      v_url,
                    "price":            data.get("price", ""),
                    "fuel_type":        data.get("fuel_type", ""),
                    "transmission":     data.get("transmission", ""),
                    "engine":           data.get("engine", ""),
                    "mileage":          data.get("mileage", ""),
                    "power":            data.get("power", ""),
                    "torque":           data.get("torque", ""),
                    "seating_capacity": data.get("seating_capacity", ""),
                    "airbags":          data.get("airbags", ""),
                    "body_type":        data.get("body_type", ""),
                    "data_source":      data_source,
                    "source_url":       v_url,
                    "scraped_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                out_f.flush()
                total += 1
                time.sleep(DELAY)

            time.sleep(DELAY)

    print(f"\nDone. Total variants scraped: {total}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()