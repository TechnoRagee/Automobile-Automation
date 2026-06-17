"""
TEST: Phase 3 variant scraper — Tata brand only
Reads models.csv, filters Tata, scrapes variants -> test_tata_variants.csv
"""

import csv
import os
import re
import time
from datetime import datetime
import requests


# ── adjust this import if fallback.py not in same dir ─────────────────────
try:
    from fallback import cardekho_fallback
except ImportError:
    pass
    
BASE_URL = "https://www.carwale.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

MODELS_FILE = "output/models.csv"
OUTPUT_FILE = "output/variants1.csv"
DELAY       = 1.5




FIELDNAMES = (
    [
        "brand_name",
        "brand_slug",
        "model_name",
        "model_slug",
        "variant_name",
        "variant_slug",
        "variant_url",
        "data_source",
        "source_url",
        "scraped_at",
    ]
)


# ── helpers ───────────────────────────────────────────────────────────────

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

BAD_VARIANTS ={ # TEMPORARY
                    "nexon",
                    "punch",
                    "sierra",
                    "tiago",
                    "tiago ev",
                    "harrier",
                    "safari",
                    "altroz",
                    "curvv",
                    "avinya",
                }

def get_version_names(html):
    if not html:
        return []

    versions = re.findall(r'"VersionName":"([^"]+)"', html, re.I)
    clean_versions = []
    
    for v in versions:
        if v.lower().strip() in BAD_VARIANTS:
            continue
        clean_versions.append(v)
    return sorted(set(clean_versions))


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        all_models = list(csv.DictReader(f))

    # ── FILTER: Tata only ─────────────────────────────────────────────────
    models = all_models
    print(f" Models found: {len(models)}")


    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    total = 0

    def slugify(name: str) -> str:
        s = (name or "").lower()
        s = re.sub(r'(\d)\.(\d)', r'\1\2', s)
        s = re.sub(r"[\(\)]", "", s)
        s = s.replace("/", "-")
        s = re.sub(r"[^a-z0-9\-]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return s

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, model in enumerate(models, 1):
            brand_name = model.get("brand_name", "")
            brand_slug = model.get("brand_slug","")
            model_name = model.get("model_name", "")
            model_slug = model.get("model_slug", "")
            model_url = model.get("model_url", "")

            print(f"[{i}/{len(models)}] {brand_name} {model_name}")

            html = fetch(model_url)
            if html is None:
                print("  fetch failed, skipping")
                continue

            versions = get_version_names(html)
            if not versions:
                print("No versions Found")
                continue
            
            print(f"  Versions found: {len(versions)}")
            
            

            for version_name in versions:
                
                if version_name.lower().strip() in BAD_VARIANTS:
                    continue
                variant_slug = slugify(version_name)
                variant_url = (
                f"{BASE_URL}/{brand_slug}-cars/{model_slug}/{variant_slug}/"
              )
                writer.writerow({
                    "brand_name": brand_name,
                    "brand_slug": brand_slug,
                    "model_name": model_name,
                    "model_slug":model_slug,
                    "variant_name": version_name,
                    "variant_slug": slugify(version_name),
                    "variant_url":variant_url,
                    "data_source":"carwale_versions",
                    "source_url": model_url,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            total += len(versions)

    print(f"\nDone. Total variants scraped: {total}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()