"""
Resolve unresolved variants via CarWale search API.
Reads output/unresolved_variants.csv, searches CarWale for each variant,
finds real URL, patches output/variants1.csv with found URLs.
"""

import csv
import json
import os
import re
import time
import requests

UNRESOLVED_FILE = "output/unresolved_variants.csv"
VARIANTS_FILE   = "output/variants1.csv"
STILL_FAILED    = "output/still_unresolved.csv"
DELAY           = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
}

SEARCH_URL = "https://www.carwale.com/api/suggest/?q={query}&count=10"


def search_carwale(brand_name, model_name, variant_name):
    """Search CarWale, return best matching variant URL or None."""
    query = f"{brand_name} {model_name} {variant_name}".strip()
    url = SEARCH_URL.format(query=requests.utils.quote(query))
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        # CarWale suggest returns list of dicts with 'URL' or 'Url' key
        for item in (data if isinstance(data, list) else data.get("data", [])):
            item_url = item.get("URL") or item.get("Url") or item.get("url") or ""
            title    = item.get("Title") or item.get("title") or item.get("Name") or ""
            if not item_url:
                continue
            # must be a variant page (4 path segments: /brand-cars/model/variant/)
            parts = [p for p in item_url.strip("/").split("/") if p]
            if len(parts) == 3:
                full = item_url if item_url.startswith("http") else f"https://www.carwale.com{item_url}"
                return full
    except Exception as e:
        print(f"    search error: {e}")
    return None


def verify_url(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            return True
        if r.status_code in (403, 405):
            r2 = requests.get(url, headers=HEADERS, timeout=10)
            return r2.status_code == 200
    except Exception:
        pass
    return False


def main():
    if not os.path.exists(UNRESOLVED_FILE):
        print(f"NOT FOUND: {UNRESOLVED_FILE}")
        return

    with open(UNRESOLVED_FILE, newline="", encoding="utf-8") as f:
        unresolved = list(csv.DictReader(f))

    print(f"Unresolved to fix: {len(unresolved)}")

    # build lookup key -> real url
    resolved_map = {}  # key=(brand_name, model_name, variant_name) -> url
    still_failed = []

    for i, row in enumerate(unresolved, 1):
        brand = row.get("brand_name", "")
        model = row.get("model_name", "")
        variant = row.get("variant_name", "")
        key = (brand, model, variant)

        print(f"[{i}/{len(unresolved)}] {brand} {model} | {variant}")

        found_url = search_carwale(brand, model, variant)
        if found_url and verify_url(found_url):
            print(f"  FOUND: {found_url}")
            resolved_map[key] = found_url
        else:
            print(f"  STILL FAILED")
            still_failed.append(row)

        time.sleep(DELAY)

    print(f"\nResolved: {len(resolved_map)}  Still failed: {len(still_failed)}")

    # patch variants1.csv
    with open(VARIANTS_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = f.fieldnames if hasattr(f, 'fieldnames') else list(rows[0].keys())

    # re-read fieldnames properly
    with open(VARIANTS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    patched = 0
    for row in rows:
        if row.get("variant_url"):
            continue
        key = (row.get("brand_name",""), row.get("model_name",""), row.get("variant_name",""))
        if key in resolved_map:
            row["variant_url"] = resolved_map[key]
            row["source_url"]  = resolved_map[key]
            row["data_source"] = "search_resolved"
            patched += 1

    with open(VARIANTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Patched {patched} rows in {VARIANTS_FILE}")

    if still_failed:
        with open(STILL_FAILED, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(still_failed[0].keys()))
            writer.writeheader()
            writer.writerows(still_failed)
        print(f"Still unresolved -> {STILL_FAILED}")


if __name__ == "__main__":
    main()