"""
Phase 2: For each brand in brands.csv, extract all car models -> models.csv

A brand page (e.g. /tata-cars/) lists current models, upcoming models,
and discontinued models, all as links of the form:
    /{brand-slug}-cars/{model-slug}/

The page ALSO contains many other links we must exclude:
    - /{brand-slug}-cars/{model-slug}/expert-reviews/...
    - /{brand-slug}-cars/{model-slug}/images/
    - /{brand-slug}-cars/{model-slug}/price-in-{city}/
    - /{brand-slug}-cars/videos/, /news/, /expert-reviews/, /upcoming/
    - /compare-cars/...
    - links to OTHER brands (similar brands / popular brands sections)
    - /used/{brand}-{model}/ (used car listings)

We only keep links of the exact form /{brand-slug}-cars/{model-slug}/
with no further path segments, and model-slug not in a small exclude list.

Run locally (requires network access to carwale.com):
    pip install requests
    python 02_extract_models.py
"""

import csv
import os
import re
import time
import requests
from fallback import cardekho_get_models

BASE_URL = "https://www.carwale.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

BRANDS_FILE = "output/brands.csv"
OUTPUT_FILE = "output/models.csv"
DELAY_SECONDS = 1.5  # be polite between requests

# Path segments that are NOT model slugs - reserved/section pages on a brand site
EXCLUDED_SLUGS = {
    "videos", "news", "expert-reviews", "upcoming", "images",
    "dealers", "reviews", "compare-cars", "deals", "offers",
    "specifications", "specs", "features", "colours", "colors",
    "mileage", "brochure", "360-view", "service-cost", "accessories",
    "price", "emi-calculator", "on-road-price",
}

# Slugs ending with these suffixes are sub-pages, not root model pages
EXCLUDED_SUFFIXES = (
    "-facelift",
    "-amg", "-maybach", "-cabriolet", "-roadster",
    "-2020", "-2021", "-2022", "-2023", "-2024", "-2025", "-2026",
)

# Slugs matching these patterns are old/discontinued generation pages
EXCLUDED_PATTERNS = re.compile(
    r'(-\d{4}-\d{4}$)'   # year range e.g. glb-2022-2025
    r'|(^old-generation-)'  # old-generation-v-class-2019
    r'|(-\d{4}$)'          # single year suffix e.g. cla-2026
)


def fetch(url, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    [retry {attempt}/{retries}] {url} -> {e}")
            time.sleep(delay * attempt)
    print(f"    FAILED: {url}")
    return None


def load_brands():
    brands = []
    with open(BRANDS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            brands.append(row)
    return brands


def extract_models(html, brand_slug):
    """
    Find all hrefs matching /{brand_slug}-cars/{model_slug}/ (exactly one
    path segment after '-cars/', optional trailing slash, no query string).
    """
    pattern = re.compile(
        r'href="(?:https://www\.carwale\.com)?/'
        + re.escape(brand_slug)
        + r'-cars/([a-z0-9-]+)/?(?:["#?])'
    )

    models = {}
    for m in pattern.finditer(html):
        slug = m.group(1)
        if slug in EXCLUDED_SLUGS:
            continue
        if any(slug.endswith(sfx) for sfx in EXCLUDED_SUFFIXES):
            continue
        if EXCLUDED_PATTERNS.search(slug):
            continue
        if slug not in models:
            models[slug] = {
                "model_slug": slug,
                "model_url": f"{BASE_URL}/{brand_slug}-cars/{slug}/",
            }
    return list(models.values())


def main():
    brands = load_brands()
    print(f"Loaded {len(brands)} brands.")

    # Only scrape models for CURRENT brands
    # Discontinued brands have no active models to sell
    # Upcoming brands have no CarWale pages yet
    current_brands = [b for b in brands if b.get("status", "current") == "current"]
    skipped = len(brands) - len(current_brands)
    print(f"Scraping {len(current_brands)} current brands (skipping {skipped} discontinued/upcoming).")

    all_rows = []
    for i, brand in enumerate(current_brands, 1):
        brand_slug = brand["brand_slug"]
        brand_name = brand["brand_name"]
        url = brand["brand_url"]

        print(f"[{i}/{len(current_brands)}] {brand_name} -> {url}")
        html = fetch(url)
        if html is None:
            continue

        models = extract_models(html, brand_slug)
        print(f"    found {len(models)} models from CarWale")

        source = "carwale"
        if not models:
            print(f"    0 models from CarWale — trying CarDekho fallback...")
            cd_models = cardekho_get_models(brand_slug)
            for m in cd_models:
                models.append({
                    "model_slug": m["model_slug"],
                    "model_url":  m["model_url"],
                })
            source = "cardekho"
            print(f"    found {len(models)} models from CarDekho")

        for model in models:
            all_rows.append({
                "brand_slug":   brand_slug,
                "brand_name":   brand_name,
                "model_slug":   model["model_slug"],
                "model_name":   model["model_slug"].replace("-", " ").title(),
                "model_url":    model["model_url"],
                "model_source": source,
            })

        time.sleep(DELAY_SECONDS)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["brand_slug", "brand_name", "model_slug", "model_name", "model_url", "model_source"],
        )
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    print(f"\nTotal models found: {len(all_rows)}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()