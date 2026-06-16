"""
Phase 1: Extract all car brands from CarWale -> brands.csv

Source: CarWale's official sitemap (cw-make.xml), which lists every
brand page in both English and Hindi. This is more complete/reliable
than scraping the homepage (which only shows ~38 of 47 brands inline,
with the rest behind a "View More Brands" UI element).

Run locally (requires network access to carwale.com):
    pip install requests beautifulsoup4 lxml
    python 01_extract_brands.py
"""

import csv
import os
import re
import time
import xml.etree.ElementTree as ET
import requests
from fallback import cardekho_get_brands, get_extra_brands

BASE_URL = "https://www.carwale.com"
SITEMAP_URL = f"{BASE_URL}/sitemap/cw-make.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

OUTPUT_FILE = "output/brands.csv"

# Slug -> proper display name overrides (sitemap only has slugs, no display names)
NAME_OVERRIDES = {
    "bmw": "BMW",
    "mg": "MG",
    "byd": "BYD",
    "jsw": "JSW",
    "vinfast": "VinFast",
    "mclaren": "McLaren",
    "rolls-royce": "Rolls-Royce",
    "aston-martin": "Aston Martin",
    "land-rover": "Land Rover",
    "force-motors": "Force Motors",
    "maruti-suzuki": "Maruti Suzuki",
    "mercedes-benz": "Mercedes-Benz",
}


def fetch(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.content  # raw bytes, let ElementTree handle encoding/BOM
        except requests.RequestException as e:
            print(f"  [retry {attempt}/{retries}] {url} -> {e}")
            time.sleep(delay * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


def slug_to_name(slug):
    if slug in NAME_OVERRIDES:
        return NAME_OVERRIDES[slug]
    return " ".join(w.capitalize() for w in slug.split("-"))


def extract_brands(xml_bytes):
    # Parse with built-in ElementTree (no external dependency needed).
    # Passing raw bytes lets ElementTree auto-detect encoding and handle
    # any BOM correctly. Sitemap uses a default namespace, so we strip
    # namespace prefixes when matching tags below.
    root = ET.fromstring(xml_bytes)

    pattern = re.compile(r"^https://www\.carwale\.com/([a-z0-9-]+)-cars/?$")

    brands = {}
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]  # strip namespace prefix
        if tag != "loc":
            continue
        url = (elem.text or "").strip()
        m = pattern.match(url)
        if not m:
            continue  # skip /hi/ (Hindi) variants and anything else
        slug = m.group(1)
        if slug not in brands:
            brands[slug] = {
                "brand_slug": slug,
                "brand_name": slug_to_name(slug),
                "brand_url": f"{BASE_URL}/{slug}-cars/",
            }

    return list(brands.values())


def main():
    print(f"Fetching {SITEMAP_URL} ...")
    xml_text = fetch(SITEMAP_URL)

    brands = extract_brands(xml_text)
    print(f"Found {len(brands)} brands from CarWale.")

    # Mark all CarWale brands as current
    for b in brands:
        b["status"] = "current"

    # Fallback: if CarWale returns suspiciously few brands, merge CarDekho list
    if len(brands) < 30:
        print("CarWale brand count low — fetching CarDekho fallback list...")
        cd_brands = cardekho_get_brands()
        existing_slugs = {b["brand_slug"] for b in brands}
        added = 0
        for b in cd_brands:
            if b["brand_slug"] not in existing_slugs:
                b["status"] = "current"
                brands.append(b)
                existing_slugs.add(b["brand_slug"])
                added += 1
        print(f"Added {added} brands from CarDekho. Total: {len(brands)}")

    # Merge upcoming + discontinued brands from CarDekho
    existing_slugs = {b["brand_slug"] for b in brands}
    extra = get_extra_brands()
    added = 0
    for b in extra:
        if b["brand_slug"] not in existing_slugs:
            brands.append(b)
            existing_slugs.add(b["brand_slug"])
            added += 1
    print(f"Added {added} extra brands (upcoming/discontinued). Total: {len(brands)}")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["brand_slug", "brand_name", "brand_url", "status"]
        )
        writer.writeheader()
        for b in sorted(brands, key=lambda x: x["brand_name"]):
            writer.writerow(b)

    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()