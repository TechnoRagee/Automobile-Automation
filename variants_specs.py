"""
Phase 3 variant scraper: VersionName from model page JSON -> build variant URL ->
fetch each variant page -> extract specs.
Headers: price, fuel_type, transmission, engine, mileage, power, torque,
seating_capacity, airbags, body_type, source_url, scraped_at
price = Ex-Showroom only.
"""

import csv
import os
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

try:
    from fallback import cardekho_fallback
except ImportError:
    def cardekho_fallback(data, brand_slug, model_slug):
        return data

BASE_URL = "https://www.carwale.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

MODELS_FILE = "output/variants1.csv"
OUTPUT_FILE = "output/variants_specs.csv"
DELAY       = 1.5

SPEC_FIELDS = [
    "price", "fuel_type", "transmission", "engine", "mileage",
    "power", "torque", "seating_capacity", "airbags", "body_type",
]
FIELDNAMES = [
    "brand_name",
    "model_name",
    "variant_name",
    "variant_slug",
    "variant_url",
] + SPEC_FIELDS + [
    "source_url",
    "scraped_at",
]


# ── helpers ──────────────────────────────────────────────────────────────

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




# ── field extraction (from variant page) ───────────────────────────────
def extract_price(s):
    txt = s.get_text(" ", strip=True)

    m = re.search(
        r'(?:Rs\.|₹)\s*([\d.,]+)\s*(Crore|Lakh)',
        txt,
        re.I
    )

    if m:
        return f"Rs. {m.group(1)} {m.group(2).title()}"

    return ""


def extract_fuel_type(s):
    m = re.search(r'Fuel Type\s*([A-Za-z/ &]+?)(?=\n|Engine|Ethanol|$)',
                  s.get_text("\n"), re.I)
    if m:
        return m.group(1).strip()
    txt = s.get_text(" ")
    for fuel in ["Electric", "Hydrogen", "Petrol", "Diesel", "CNG", "LPG", "Hybrid"]:
        if re.search(rf'\bFuel Type\b.*?\b{fuel}\b', txt, re.I | re.S):
            return fuel
    return ""


def extract_transmission(s):
    txt = s.get_text(" ", strip=True)
    for p in [
        r'Transmission Type\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
        r'Transmission\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
    ]:
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
    m = re.search(r'(?:User Reported|Mileage)[:\s]+([\d\.]+)\s*kmpl', txt, re.I)
    if not m:
        return ""
    value = float(m.group(1))
    return "" if value > 40 else f"{value} kmpl"


def extract_power(s):
    txt = s.get_text(" ", strip=True)
    for p in [
        r'Max Power[^\d]*([\d\.]+\s*bhp)',
        r'Max Power[^\d]*([\d\.]+\s*PS)',
        r'Max Power[^\d]*([\d\.]+\s*kW)',
    ]:
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
    
    if "db11" in url:
        with open("debug_db11.html", "w", encoding="utf-8") as f:
            f.write(html)

    s = soup(html)

    if "db11" in url:
        import json
        for tag in s.find_all("script",type="application/ld+json"):
                try:
                    data = json.loads(tag.string)

                    with open("db11_json.txt", "w", encoding="utf-8") as f:
                        f.write(json.dumps(data, indent=2))
                    
                    break
                except:
                    pass

    return {
        "price": extract_price(s),
        "fuel_type": extract_fuel_type(s),
        "transmission": extract_transmission(s),
        "engine": extract_engine(s),
        "mileage": extract_mileage(s),
        "power": extract_power(s),
        "torque": extract_torque(s),
        "seating_capacity": extract_seating(s),
        "airbags": extract_airbags(s),
        "body_type": extract_body_type(s),
    }

    print("\nURL:", url)
    print(data)

    return data


# ── main ─────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        models = list(csv.DictReader(f))

    print(f"Models loaded: {len(models)}")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    total = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, model in enumerate(models, 1):
            

            
                variant_url = model.get("variant_url","")
                data = scrape_variant(variant_url)
                print(variant_url)
                print(data)
                if not variant_url:
                    continue

                data =  scrape_variant(variant_url)

                if data is None:
                    data ={}
                brand_slug = model.get("brand_slug","")
                model_slug = model.get("model_slug","")
                data = cardekho_fallback(
                    data,
                    brand_slug,
                    model_slug
                )
                writer.writerow({
                    "brand_name": model.get("brand_name", ""),
                    "model_name": model.get("model_name", ""),
                    "variant_name": model.get("variant_name", ""),
                    "variant_slug": model.get("variant_slug", ""),
                    "variant_url": variant_url,
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
                    "source_url":       variant_url,
                    "scraped_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                out_f.flush()
                total += 1
                time.sleep(DELAY)


    print(f"\nDone. Total: {total}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()