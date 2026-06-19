"""
Phase 3 variant scraper — PARALLEL version (ThreadPoolExecutor).
WORKERS = 5 parallel threads, DELAY = 0.8s per thread.
Effective throughput ~5x faster than sequential.
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
OUTPUT_FILE = "output/var_specification.csv"
DELAY       = 0.8   # per-thread delay
WORKERS     = 5     # parallel threads; increase to 8 if no blocks, decrease to 3 if getting 429s

SPEC_FIELDS = [
    "price", "fuel_type", "transmission", "engine", "mileage",
    "power", "torque", "seating_capacity", "airbags", "body_type",
]
FIELDNAMES = [
    "brand_name", "model_name", "variant_name", "variant_slug", "variant_url",
] + SPEC_FIELDS + ["source_url", "scraped_at"]

# thread-safe counters
_lock = threading.Lock()
_total = 0
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


def soup(html):
    return BeautifulSoup(html, "html.parser")


# ── field extraction ──────────────────────────────────────────────────────

def extract_price(s):
    txt = s.get_text(" ", strip=True)
    # primary: "Ex-Showroom Price Rs. 8,36,990" (raw rupees, no Lakh)
    m = re.search(r'Ex-?Showroom Price\s*Rs\.?\s*([\d,]+)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)}"
    # fallback: Rs/₹ + Lakh/Crore anywhere
    m = re.search(r'(?:Rs\.?|₹)\s*([\d.,]+)\s*(Crore|Lakh)', txt, re.I)
    if m:
        return f"Rs. {m.group(1)} {m.group(2).title()}"
    return ""

def extract_fuel_type(s):
    txt = s.get_text(" ", strip=True)
    for fuel in ["Petrol", "Diesel", "Electric", "Hybrid", "CNG", "LPG"]:
        if re.search(rf'Fuel Type\s*{fuel}', txt, re.I):
            return fuel.title()
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
    txt = s.get_text(" ", strip=True)
    # page shows: "1199 cc, 3 Cylinders..." — grab NNN cc before comma
    m = re.search(r'(\d{3,5}\s*cc)', txt, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_mileage(s):
    txt = s.get_text(" ", strip=True)
    # page shows: "User Reported: 15 kmpl" (colon format)
    m = re.search(r'User Reported[:\s]+([\d\.]+)\s*kmpl', txt, re.I)
    if not m:
        m = re.search(r'Mileage[:\s]+([\d\.]+)\s*kmpl', txt, re.I)
    if not m:
        return ""
    value = float(m.group(1))
    return "" if value > 40 else f"{value} kmpl"

def extract_power(s):
    txt = s.get_text(" ", strip=True)
    # page shows: "118 bhp @ 5500 rpm" under "Max Power (bhp@rpm)"
    m = re.search(r'Max Power[^0-9]*([\d.]+)\s*bhp', txt, re.I)
    if m:
        return f"{m.group(1)} bhp"
    m = re.search(r'([\d.]+)\s*bhp\s*@', txt, re.I)
    if m:
        return f"{m.group(1)} bhp"
    return ""

def extract_torque(s):
    txt = s.get_text(" ", strip=True)
    # page shows: "170 Nm @ 1750-4000 rpm" under "Max Torque (Nm@rpm)"
    m = re.search(r'Max Torque[^0-9]*([\d.]+)\s*Nm', txt, re.I)
    if m:
        return f"{m.group(1)} Nm"
    m = re.search(r'([\d.]+)\s*Nm\s*@', txt, re.I)
    if m:
        return f"{m.group(1)} Nm"
    return ""

def extract_engine_ev(s):
    txt = s.get_text(" ", strip=True)
    for p in [r'Battery.*?(\d+(?:\.\d+)?)\s*kWh', r'(\d+(?:\.\d+)?)\s*kWh']:
        m = re.search(p, txt, re.I)
        if m:
            return f"{m.group(1)} kWh Battery"
    return ""

def extract_power_ev(s):
    txt = s.get_text(" ", strip=True)
    for p in [
        r'(\d+(?:\.\d+)?)\s*bhp',
        r'Motor Power.*?(\d+(?:\.\d+)?)\s*kW',
        r'Power.*?(\d+(?:\.\d+)?)\s*kW',
    ]:
        m = re.search(p, txt, re.I)
        if m:
            return f"{m.group(1)} kW" if "kW" in p else f"{m.group(1)} bhp"
    return ""

def extract_torque_ev(s):
    txt = s.get_text(" ", strip=True)
    m = re.search(r'Max Torque.*?(\d+(?:\.\d+)?)\s*Nm', txt, re.I)
    if m:
        return f"{m.group(1)} Nm"
    return ""

def extract_seating(s):
    m = re.search(r'Seating Capacity\s+(\d+)\s*Seat', s.get_text(" "), re.I)
    return m.group(1) if m else ""

def extract_airbags(s):
    txt = s.get_text(" ", strip=True)
    for p in [r'(\d+)\s*Airbags?', r'Airbags?\s*(\d+)', r'Airbag Count\s*(\d+)']:
        m = re.search(p, txt, re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:
                return str(n)
    return ""

def extract_body_type(s):
    txt = s.get_text(" ", strip=True)
    for body in ["SUV", "Sedan", "Hatchback", "MUV", "MPV",
                 "Convertible", "Coupe", "Crossover", "Pickup Truck", "Pickup", "Wagon"]:
        if re.search(rf'Body\s*Type.*?\b{re.escape(body)}\b', txt, re.I):
            return body
    return ""


# ── worker ────────────────────────────────────────────────────────────────

def process_row(args):
    """Called per thread. Returns completed row dict or None on total failure."""
    global _total, _failed
    idx, total_count, model = args

    variant_url = model.get("variant_url", "").strip()
    if not variant_url:
        return None

    print(f"[{idx}/{total_count}] {model.get('brand_name')} {model.get('model_name')} | {variant_url}")

    time.sleep(DELAY)  # per-thread rate limit

    html = fetch(variant_url)
    if html is None:
        with _lock:
            _failed += 1
        data = {}
    else:
        s = soup(html)
        fuel_type = extract_fuel_type(s)
        if fuel_type and fuel_type.lower() == "electric":
            engine = extract_engine_ev(s)
            power  = extract_power_ev(s)
            torque = extract_torque_ev(s)
        else:
            engine = extract_engine(s)
            power  = extract_power(s)
            torque = extract_torque(s)

        data = {
            "price":            extract_price(s),
            "fuel_type":        fuel_type,
            "transmission":     extract_transmission(s),
            "engine":           engine,
            "mileage":          extract_mileage(s),
            "power":            power,
            "torque":           torque,
            "seating_capacity": extract_seating(s),
            "airbags":          extract_airbags(s),
            "body_type":        extract_body_type(s),
        }
        missing = [k for k, v in data.items() if not v]
        if missing:
            print(
            f"[{idx}/{total_count}] "
            f"{model.get('brand_name')} "
            f"{model.get('model_name')} "
            f"->{'variant_url'}"
        )
            print("MISSING:", missing)

    brand_slug = model.get("brand_slug", "")
    model_slug = model.get("model_slug", "")
    print("Calling Fallback:",brand_slug,model_slug)
    before = data.copy()
    data = cardekho_fallback(
        data,
        brand_slug,
        model_slug
    )
    if before != data:
        print("Fallback Updated:",brand_slug,model_slug)
    return {
        "brand_name":       model.get("brand_name", ""),
        "model_name":       model.get("model_name", ""),
        "variant_name":     model.get("variant_name", ""),
        "variant_slug":     model.get("variant_slug", ""),
        "variant_url":      variant_url,
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
    }


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        models = [m for m in csv.DictReader(f) if m.get("variant_url", "").strip()]

    print(f"Models loaded: {len(models)} (non-empty URLs only)")
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

    print(f"\nDone. Written: {written}  Failed fetches: {_failed}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()