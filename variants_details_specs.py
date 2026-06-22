"""
Phase 3 variant scraper — full spec set from CarWale variant pages.
Primary: CarWale. CarDekho fallback only if field still empty after CarWale.
Parallel execution: WORKERS threads, DELAY per thread.
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

try:
    from fallback_details import cardekho_fallback
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
OUTPUT_FILE = "output/variants_details_specs.csv"
DELAY       = 0.8
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

_lock = threading.Lock()
_failed = 0


# ── helpers ───────────────────────────────────────────────────────────────

def fetch(url, retries=4, delay=2):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"        [retry {attempt}] {e}")
            time.sleep(delay * attempt)
    print(f"        FAILED: {url}")
    return None


def get_text(s):
    return s.get_text(" ", strip=True)


def field_value(txt, label):
    """
    Extract value after a label in CarWale spec table text.
    e.g. "Fuel Type Petrol Ethanol..." -> "Petrol"
    """
    m = re.search(rf'{re.escape(label)}\s+([^\n]+?)(?=\s{{2,}}|\s[A-Z][a-z]{{2,}}|\Z)',
                  txt, re.I)
    if m:
        return m.group(1).strip()
    return ""


# ── extractors ────────────────────────────────────────────────────────────

def extract_price(txt):
    m = re.search(r'Ex-?Showroom Price\s*Rs\.?\s*([\d,]+)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)}"
    m = re.search(r'(?:Rs\.?|₹)\s*([\d.,]+)\s*(Crore|Lakh)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)} {m.group(2).title()}"
    return ""

def extract_fuel_type(txt):
    for fuel in ["Petrol", "Diesel", "Electric", "Hybrid", "CNG", "LPG"]:
        if re.search(rf'Fuel Type\s+{fuel}', txt, re.I):
            return fuel
    return ""

def extract_engine_type(txt):
    # "Engine Type 1.2L Revotron" or "Engine Type 1.2L Turbocharged Revotron Engine"
    m = re.search(r'Engine Type\s+([^\n]{3,50}?)(?=\s{2,}|Engine\s|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_engine_cc(txt):
    # "Engine 1199 cc, 3 Cylinders..." -> "1199 cc"
    m = re.search(r'Engine\s+(\d{3,5}\s*cc)', txt, re.I)
    if not m:
        m = re.search(r'(\d{3,5}\s*cc)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_max_power(txt):
    # "Max Power (bhp@rpm) 118 bhp @ 5500 rpm"
    m = re.search(r'Max Power[^0-9]*([\d.]+)\s*bhp', txt, re.I)
    if m:
        rpm = re.search(r'Max Power[^@]*@\s*([\d,\-]+)\s*rpm', txt, re.I)
        return f"{m.group(1)} bhp @ {rpm.group(1)} rpm" if rpm else f"{m.group(1)} bhp"
    return ""

def extract_max_torque(txt):
    # "Max Torque (Nm@rpm) 170 Nm @ 1750-4000 rpm"
    m = re.search(r'Max Torque[^0-9]*([\d.]+)\s*Nm', txt, re.I)
    if m:
        rpm = re.search(r'Max Torque[^@]*@\s*([\d,\-]+)\s*rpm', txt, re.I)
        return f"{m.group(1)} Nm @ {rpm.group(1)} rpm" if rpm else f"{m.group(1)} Nm"
    return ""

def extract_turbocharger(txt):
    m = re.search(r'Turbocharger[/\s\w]*\s+(Yes|No|Turbocharged|NA)', txt, re.I)
    if m:
        val = m.group(1).strip().lower()
        if val in ("yes", "turbocharged"):
            return "Yes"
        if val == "no":
            return "No"
    return ""

def extract_transmission(txt):
    # "Transmission Type Automatic" (CarWale variant page exact label)
    for p in [
        r'Transmission Type\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
        r'Transmission\s+(Automatic|Manual|CVT|AMT|DCT|DSG|iMT)',
    ]:
        m = re.search(p, txt, re.I)
        if m:
            return m.group(1).title()
    return ""

def extract_gearbox(txt):
    m = re.search(r'Gearbox\s+([\w\-]+\s*Speed|Single Speed)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_drive_type(txt):
    m = re.search(r'Drive Type\s+(FWD|RWD|AWD|4WD|4x4|4x2)', txt, re.I)
    if m:
        return m.group(1).upper()
    return ""

def extract_mileage(txt):
    m = re.search(r'User Reported[:\s]+([\d.]+)\s*kmpl', txt, re.I)
    if not m:
        m = re.search(r'Mileage[:\s]+([\d.]+)\s*kmpl', txt, re.I)
    if m:
        val = float(m.group(1))
        return f"{val} kmpl" if val <= 40 else ""
    return ""

def extract_seating(txt):
    m = re.search(r'Seating Capacity\s+(\d+)\s*Seat', txt, re.I)
    return m.group(1) if m else ""

def extract_airbags(txt):
    for p in [r'(\d+)\s*Airbags?', r'Airbags?\s*(\d+)', r'No\.\s*of\s*Airbags?\s*(\d+)']:
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
    # "Battery Lithium Ion, 30 kWh, Placed Under Floor Pan"
    m = re.search(r'Battery[^.]*?([\d.]+)\s*kWh', txt, re.I)
    if m:
        return f"{m.group(1)} kWh"
    return ""

def extract_motor_power(txt):
    # "Motor Power 95 kW" or from CarDekho "Motor Power 95 kW"
    m = re.search(r'Motor Power\s+([\d.]+)\s*kW', txt, re.I)
    if m:
        return f"{m.group(1)} kW"
    return ""

def extract_motor_type(txt):
    # "Electric Motor Single Permanent Magnet Synchronous Motor..."
    m = re.search(r'Electric Motor\s+([^\n]{5,80}?)(?=\s{2,}|\Z)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_driving_range(txt):
    # "Driving Range 355 km"
    m = re.search(r'Driving Range\s+([\d\-]+)\s*km', txt, re.I)
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


# ── scraper ───────────────────────────────────────────────────────────────

def scrape_variant(url):
    html = fetch(url)
    if not html:
        return None
    txt = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    fuel_type = extract_fuel_type(txt)
    is_ev = fuel_type.lower() == "electric"

    return {
        "fuel_type":        fuel_type,
        "engine_type":      "" if is_ev else extract_engine_type(txt),
        "engine_cc":        "" if is_ev else extract_engine_cc(txt),
        "max_power":        extract_max_power(txt),
        "max_torque":       extract_max_torque(txt),
        "turbocharger":     "" if is_ev else extract_turbocharger(txt),
        "transmission_type": extract_transmission(txt),
        "gearbox":          extract_gearbox(txt),
        "drive_type":       extract_drive_type(txt),
        "mileage":          "" if is_ev else extract_mileage(txt),
        "battery_capacity": extract_battery(txt) if is_ev else "",
        "motor_power":      extract_motor_power(txt) if is_ev else "",
        "motor_type":       extract_motor_type(txt) if is_ev else "",
        "driving_range":    extract_driving_range(txt) if is_ev else "",
        "ac_charging":      extract_ac_charging(txt) if is_ev else "",
        "dc_charging":      extract_dc_charging(txt) if is_ev else "",
        "price":            extract_price(txt),
        "seating_capacity": extract_seating(txt),
        "airbags":          extract_airbags(txt),
        "body_type":        extract_body_type(txt),
    }


# ── worker ────────────────────────────────────────────────────────────────

def process_row(args):
    global _failed
    idx, total, model = args

    url = model.get("variant_url", "").strip()
    if not url:
        return None

    print(f"[{idx}/{total}] {model.get('brand_name')} {model.get('model_name')} | {url}")
    time.sleep(DELAY)

    data = scrape_variant(url)
    if data is None:
        with _lock:
            _failed += 1
        data = {}
    else:
        missing = [k for k, v in data.items() if not v]
        if missing:
            print(f"  MISSING {missing}")

    brand_slug = model.get("brand_slug", "")
    model_slug = model.get("model_slug", "")
    missing = [
        k for k, v in data.items()
        if not v
    ]
    if missing:
        print( f"Calling Fallback: "
        f"{brand_slug} {model_slug}")
    data = cardekho_fallback(data, brand_slug, model_slug)

    return {
        "brand_name":       model.get("brand_name", ""),
        "model_name":       model.get("model_name", ""),
        "variant_name":     model.get("variant_name", ""),
        "variant_url":      url,
        "fuel_type":        data.get("fuel_type", ""),
        "engine_type":      data.get("engine_type", ""),
        "engine_cc":        data.get("engine_cc", ""),
        "max_power":        data.get("max_power", ""),
        "max_torque":       data.get("max_torque", ""),
        "turbocharger":     data.get("turbocharger", ""),
        "transmission_type": data.get("transmission_type", ""),
        "gearbox":          data.get("gearbox", ""),
        "drive_type":       data.get("drive_type", ""),
        "mileage":          data.get("mileage", ""),
        "battery_capacity": data.get("battery_capacity", ""),
        "motor_power":      data.get("motor_power", ""),
        "motor_type":       data.get("motor_type", ""),
        "driving_range":    data.get("driving_range", ""),
        "ac_charging":      data.get("ac_charging", ""),
        "dc_charging":      data.get("dc_charging", ""),
        "price":            data.get("price", ""),
        "seating_capacity": data.get("seating_capacity", ""),
        "airbags":          data.get("airbags", ""),
        "body_type":        data.get("body_type", ""),
        "data_source":      model.get("data_source", "carwale"),
        "source_url":       url,
        "scraped_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        models = [m for m in csv.DictReader(f) if m.get("variant_url", "").strip()]

    print(f"Variants to scrape: {len(models)}")
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