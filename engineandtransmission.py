"""
CarDekho standalone spec scraper — fallback for missing CarWale data.
Hits cardekho.com/{brand}/{model}/specs
Headers match: FIELDNAMES from var_specs scripts (v2 schema).
"""

import csv
import os
import re
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.cardekho.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

MODELS_FILE = "output/variants1.csv"
OUTPUT_FILE = "output/Engine&Transmission.csv"
DELAY       = 1.0
WORKERS     = 5

FIELDNAMES = [
    "brand_name", "model_name", "variant_name", "variant_url",
    # engine & transmission
    "fuel_type", "engine_type", "engine_cc", "max_power", "max_torque",
    "turbocharger", "transmission_type", "gearbox", "drive_type",
    # fuel & performance
    "mileage",
    # EV specific
    "battery_capacity", "motor_power", "motor_type",
    "driving_range", "ac_charging", "dc_charging",
    # general
    "price", "seating_capacity", "airbags", "body_type",
    "data_source", "source_url", "scraped_at",
]

_lock   = threading.Lock()
_failed = 0


# ── helpers ───────────────────────────────────────────────────────────────

def fetch(url, retries=4, delay=2):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.content          # raw bytes — avoids BOM issues
        except requests.RequestException as e:
            print(f"        [retry {attempt}] {e}")
            time.sleep(delay * attempt)
    print(f"        FAILED: {url}")
    return None


def cd_url(brand_slug, model_slug):
    return f"{BASE_URL}/{brand_slug}/{model_slug}/specs"


# ── extractors (CarDekho label names from screenshot) ─────────────────────

def extract_fuel_type(txt):
    for fuel in ["Petrol", "Diesel", "Electric", "Hybrid", "CNG", "LPG"]:
        if re.search(rf'Fuel Type\s+{fuel}', txt, re.I):
            return fuel
    return ""

def extract_engine_type(txt):
    # Label: "Engine Type   1.0L Turbo Boosterjet"
    m = re.search(r'Engine Type\s+([^\n]{3,60}?)(?=\s{2,}|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_engine_cc(txt):
    # Label: "Displacement   998 cc"
    m = re.search(r'Displacement\s+(\d{3,5}\s*cc)', txt, re.I)
    if not m:
        m = re.search(r'(\d{3,5}\s*cc)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_max_power(txt):
    # Label: "Max Power   98.69bhp@5500rpm"
    m = re.search(r'Max Power\s+([\d.]+)\s*bhp\s*@?\s*([\d,\-]+)\s*rpm', txt, re.I)
    if m:
        return f"{m.group(1)} bhp @ {m.group(2)} rpm"
    m = re.search(r'Max Power\s+([\d.]+)\s*bhp', txt, re.I)
    if m:
        return f"{m.group(1)} bhp"
    return ""

def extract_max_torque(txt):
    # Label: "Max Torque   147.6Nm@2000-4500rpm"
    m = re.search(r'Max Torque\s+([\d.]+)\s*Nm\s*@?\s*([\d,\-]+)\s*rpm', txt, re.I)
    if m:
        return f"{m.group(1)} Nm @ {m.group(2)} rpm"
    m = re.search(r'Max Torque\s+([\d.]+)\s*Nm', txt, re.I)
    if m:
        return f"{m.group(1)} Nm"
    return ""

def extract_turbocharger(txt):
    # Label: "Turbo Charger   ✓" (tick = Yes)
    m = re.search(r'Turbo\s*Charger\s+([✓✗YesNo]+)', txt, re.I)
    if m:
        val = m.group(1).strip()
        if val in ("✓", "Yes"):
            return "Yes"
        if val in ("✗", "No"):
            return "No"
    # fallback: check raw HTML for checkmark
    if re.search(r'Turbo\s*Charger', txt, re.I):
        # rely on caller passing html check if needed
        pass
    return ""

def extract_transmission(txt):
    # Label: "Transmission Type   Automatic"
    for p in [
        r'Transmission Type\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
        r'Transmission\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
    ]:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1).title()
    return ""

def extract_gearbox(txt):
    # Label: "Gearbox   6-Speed AT"
    m = re.search(r'Gearbox\s+([\w\-]+\s*Speed\s*\w*|Single Speed)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_drive_type(txt):
    # Label: "Drive Type   FWD"
    m = re.search(r'Drive Type\s+(FWD|RWD|AWD|4WD|4x4|4x2)', txt, re.I)
    if m:
        return m.group(1).upper()
    return ""

def extract_mileage(txt):
    # CarDekho shows ARAI mileage: "Mileage   21.79 kmpl"
    m = re.search(r'Mileage\s+([\d.]+)\s*kmpl', txt, re.I)
    if m:
        val = float(m.group(1))
        return f"{val} kmpl" if val <= 40 else ""
    return ""

def extract_price(txt):
    # "Ex-Showroom Price   Rs. 10,49,000" or "₹10.49 Lakh"
    m = re.search(r'Ex-?Showroom Price\s*Rs\.?\s*([\d,]+)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)}"
    m = re.search(r'(?:Rs\.?|₹)\s*([\d.,]+)\s*(Crore|Lakh)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)} {m.group(2).title()}"
    return ""

def extract_seating(txt):
    m = re.search(r'Seating Capacity\s+(\d+)', txt, re.I)
    return m.group(1) if m else ""

def extract_airbags(txt):
    for p in [r'No\.\s*of\s*Airbags?\s*(\d+)', r'(\d+)\s*Airbags?', r'Airbags?\s*(\d+)']:
        m = re.search(p, txt, re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:
                return str(n)
    return ""

def extract_body_type(txt):
    for body in ["SUV", "Sedan", "Hatchback", "MUV", "MPV",
                 "Convertible", "Coupe", "Crossover", "Pickup Truck", "Pickup", "Wagon"]:
        if re.search(rf'Body\s*Type.*?\b{re.escape(body)}\b', txt, re.I):
            return body
    return ""

# EV specific
def extract_battery(txt):
    m = re.search(r'Battery[^.]*?([\d.]+)\s*kWh', txt, re.I)
    if m:
        return f"{m.group(1)} kWh"
    return ""

def extract_motor_power(txt):
    m = re.search(r'Motor Power\s+([\d.]+)\s*kW', txt, re.I)
    if m:
        return f"{m.group(1)} kW"
    return ""

def extract_motor_type(txt):
    m = re.search(r'Electric Motor\s+([^\n]{5,80}?)(?=\s{2,}|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_driving_range(txt):
    m = re.search(r'(?:Driving Range|Range)\s+([\d\-]+)\s*km', txt, re.I)
    if m:
        return f"{m.group(1)} km"
    return ""

def extract_ac_charging(txt):
    m = re.search(r'AC (?:Regular )?Charging\s+([^\n]{5,80}?)(?=\s{2,}|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_dc_charging(txt):
    m = re.search(r'DC (?:Fast )?Charging\s+([^\n]{5,80}?)(?=\s{2,}|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""


# ── turbocharger from HTML (tick mark) ───────────────────────────────────

def extract_turbocharger_html(soup):
    """CarDekho uses a ✓ tick icon — check raw HTML for it near Turbo Charger label."""
    rows = soup.find_all(["li", "tr", "div"])
    for row in rows:
        txt = row.get_text(" ", strip=True)
        if re.search(r'Turbo\s*Charger', txt, re.I):
            # check for tick SVG / checkmark entity / Yes
            html = str(row)
            if "✓" in html or "check" in html.lower() or "Yes" in txt:
                return "Yes"
            if "✗" in html or "No" in txt:
                return "No"
    return ""


# ── scraper ───────────────────────────────────────────────────────────────

def scrape_cd(brand_slug, model_slug):
    url = cd_url(brand_slug, model_slug)
    raw = fetch(url)
    if not raw:
        return None, url

    soup = BeautifulSoup(raw, "html.parser")
    txt  = soup.get_text(" ", strip=True)

    fuel_type = extract_fuel_type(txt)
    is_ev = fuel_type.lower() == "electric"

    turbo = extract_turbocharger_html(soup) or extract_turbocharger(txt)

    return {
        "fuel_type":         fuel_type,
        "engine_type":       "" if is_ev else extract_engine_type(txt),
        "engine_cc":         "" if is_ev else extract_engine_cc(txt),
        "max_power":         extract_max_power(txt),
        "max_torque":        extract_max_torque(txt),
        "turbocharger":      "" if is_ev else turbo,
        "transmission_type": extract_transmission(txt),
        "gearbox":           extract_gearbox(txt),
        "drive_type":        extract_drive_type(txt),
        "mileage":           "" if is_ev else extract_mileage(txt),
        "battery_capacity":  extract_battery(txt) if is_ev else "",
        "motor_power":       extract_motor_power(txt) if is_ev else "",
        "motor_type":        extract_motor_type(txt) if is_ev else "",
        "driving_range":     extract_driving_range(txt) if is_ev else "",
        "ac_charging":       extract_ac_charging(txt) if is_ev else "",
        "dc_charging":       extract_dc_charging(txt) if is_ev else "",
        "price":             extract_price(txt),
        "seating_capacity":  extract_seating(txt),
        "airbags":           extract_airbags(txt),
        "body_type":         extract_body_type(txt),
    }, url


# ── worker ────────────────────────────────────────────────────────────────

def process_row(args):
    global _failed
    idx, total, model = args

    brand_slug = model.get("brand_slug", "").strip()
    model_slug = model.get("model_slug", "").strip()
    if not brand_slug or not model_slug:
        return None

    print(f"[{idx}/{total}] {model.get('brand_name')} {model.get('model_name')}")
    time.sleep(DELAY)

    data, src_url = scrape_cd(brand_slug, model_slug)
    if data is None:
        with _lock:
            _failed += 1
        data = {}
    else:
        missing = [k for k, v in data.items() if not v]
        if missing:
            print(f"  MISSING {missing}")

    return {
        "brand_name":        model.get("brand_name", ""),
        "model_name":        model.get("model_name", ""),
        "variant_name":      model.get("variant_name", ""),
        "variant_url":       model.get("variant_url", ""),
        "fuel_type":         data.get("fuel_type", ""),
        "engine_type":       data.get("engine_type", ""),
        "engine_cc":         data.get("engine_cc", ""),
        "max_power":         data.get("max_power", ""),
        "max_torque":        data.get("max_torque", ""),
        "turbocharger":      data.get("turbocharger", ""),
        "transmission_type": data.get("transmission_type", ""),
        "gearbox":           data.get("gearbox", ""),
        "drive_type":        data.get("drive_type", ""),
        "mileage":           data.get("mileage", ""),
        "battery_capacity":  data.get("battery_capacity", ""),
        "motor_power":       data.get("motor_power", ""),
        "motor_type":        data.get("motor_type", ""),
        "driving_range":     data.get("driving_range", ""),
        "ac_charging":       data.get("ac_charging", ""),
        "dc_charging":       data.get("dc_charging", ""),
        "price":             data.get("price", ""),
        "seating_capacity":  data.get("seating_capacity", ""),
        "airbags":           data.get("airbags", ""),
        "body_type":         data.get("body_type", ""),
        "data_source":       "cardekho",
        "source_url":        src_url,
        "scraped_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        models = [m for m in csv.DictReader(f)
                  if m.get("brand_slug", "").strip() and m.get("model_slug", "").strip()]

    print(f"Variants to scrape (CarDekho): {len(models)}")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    args_list = [(i, len(models), m) for i, m in enumerate(models, 1)]
    written = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(process_row, a): a for a in args_list}
            for future in as_completed(futures):
                row = future.result()
                if row:
                    with _lock:
                        writer.writerow(row)
                        out_f.flush()
                        written += 1

    print(f"\nDone. Written: {written}  Failed: {_failed}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()