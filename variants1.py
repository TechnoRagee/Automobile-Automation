"""
TEST: Phase 3 variant scraper — Tata brand only
Reads models.csv -> scrapes variants -> test_tata_variants.csv

URL CORRECTNESS:
  1. Guess variant_url via slugify(VersionName).
  2. HEAD-check guessed URL. If 200 -> use it (data_source=guessed).
  3. If not 200 -> parse model page HTML for real <a href> variant links,
     fuzzy-match against VersionName, use that real link instead
     (data_source=scraped_real_link).
  4. If no match found either -> leave url blank, log to unresolved list.
"""

import csv
import os
import re
import time
import difflib
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from slugify_utils import slugify
from dead_models import is_dead_model

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
UNRESOLVED_FILE = "output/unresolved_variants.csv"
DELAY       = 1.5

FIELDNAMES = [
    "brand_name", "brand_slug", "model_name", "model_slug",
    "variant_name", "variant_slug", "variant_url",
    "data_source", "source_url", "scraped_at",
]
UNRESOLVED_FIELDNAMES = [
    "brand_name", "model_name", "variant_name", "guessed_url", "model_url",
]


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


def url_exists(url, retries=4, delay=2):
    """HEAD check; fall back to GET if server blocks HEAD."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                return True
            if r.status_code in (403, 405):  # HEAD blocked, try GET
                r2 = requests.get(url, headers=HEADERS, timeout=20)
                return r2.status_code == 200
            if r.status_code == 404:
                return False
        except requests.RequestException as e:
            print(f"        [head-retry {attempt}] {e}")
            time.sleep(delay * attempt)
    return False


BAD_VARIANTS = {  # TEMPORARY
    "nexon", "punch", "sierra", "tiago", "tiago ev", "harrier", "safari",
    "altroz", "curvv", "avinya", "a4", "a6", "q3", "q5", "rs5", "m4", "m5",
    "seal", "atto 3", "sealion 7", "emax 7", "city", "amaze", "elevate",
    "creta", "venue", "exter", "i20", "aircross-x", "basalt-x", "c3-x",
    "ec3", "c5-aircross", "carens", "carens-clavis", "seltos", "sonet",
    "syros", "2 series gran coupe", "3 series lwb", "m340i", "ix1 lwb",
    "ix3", "i7", "z4", "x1", "x3", "x5", "x7",
}


def get_version_names(html, model_slug):
    if not html:
        return []
    versions = re.findall(r'"VersionName":"([^"]+)"', html, re.I)
    clean_versions = []
    for v in versions:
        if model_slug in ["ix3", "new-c5-aircross", "basalt-ev", "syros-ev", "ev5"]:
            clean_v = v.lower().strip()
            if clean_v in BAD_VARIANTS:
                print("SKIPPED:", v)
                continue
        clean_versions.append(v)
    return sorted(dict.fromkeys(clean_versions))


def get_real_variant_links(html, brand_slug, model_slug):
    """
    Parse model page for actual variant hrefs.
    Returns dict: {link_text_lower: full_url}
    """
    s = BeautifulSoup(html, "html.parser")
    pattern = re.compile(rf'/{re.escape(brand_slug)}-cars/{re.escape(model_slug)}/[a-z0-9\-]+/?$', re.I)
    links = {}
    for a in s.find_all("a", href=True):
        href = a["href"]
        if pattern.search(href):
            full_url = href if href.startswith("http") else BASE_URL + href
            text = a.get_text(strip=True)
            if text:
                links[text.lower()] = full_url
    return links


def resolve_real_url(version_name, real_links):
    """Fuzzy-match VersionName against scraped link texts. Returns url or None."""
    if not real_links:
        return None
    target = version_name.lower()
    if target in real_links:
        return real_links[target]
    match = difflib.get_close_matches(target, real_links.keys(), n=1, cutoff=0.6)
    if match:
        return real_links[match[0]]
    return None


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        all_models = list(csv.DictReader(f))

    models = all_models
    print(f" Models found: {len(models)}")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    total = 0
    guessed_ok = 0
    scraped_fallback = 0
    unresolved = []

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, model in enumerate(models, 1):
            brand_name = model.get("brand_name", "")
            brand_slug = model.get("brand_slug", "")
            model_name = model.get("model_name", "")
            model_slug = model.get("model_slug", "")
            model_url = model.get("model_url", "")

            print(f"[{i}/{len(models)}] {brand_name} {model_name}")

            if is_dead_model(model_slug):
                print(f"  SKIPPED (dead model): {model_slug}")
                continue

            html = fetch(model_url)
            if html is None:
                print("  fetch failed, skipping")
                continue

            versions = get_version_names(html, model_slug)
            if not versions:
                print("  No versions found")
                continue

            real_links = None  # lazy-parsed only if a guess fails

            for version_name in versions:
                variant_slug = slugify(version_name)
                guessed_url = f"{BASE_URL}/{brand_slug}-cars/{model_slug}/{variant_slug}/"

                final_url = None
                source = ""

                if url_exists(guessed_url):
                    final_url = guessed_url
                    source = "guessed"
                    guessed_ok += 1
                else:
                    if real_links is None:
                        real_links = get_real_variant_links(html, brand_slug, model_slug)
                    real_url = resolve_real_url(version_name, real_links)
                    if real_url:
                        final_url = real_url
                        source = "scraped_real_link"
                        scraped_fallback += 1
                    else:
                        unresolved.append({
                            "brand_name": brand_name,
                            "model_name": model_name,
                            "variant_name": version_name,
                            "guessed_url": guessed_url,
                            "model_url": model_url,
                        })
                        print(f"  UNRESOLVED: {version_name}")

                writer.writerow({
                    "brand_name": brand_name,
                    "brand_slug": brand_slug,
                    "model_name": model_name,
                    "model_slug": model_slug,
                    "variant_name": version_name,
                    "variant_slug": variant_slug,
                    "variant_url": final_url or "",
                    "data_source": source,
                    "source_url": model_url,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                out_f.flush()
                total += 1
                time.sleep(DELAY)

    if unresolved:
        with open(UNRESOLVED_FILE, "w", newline="", encoding="utf-8") as uf:
            uw = csv.DictWriter(uf, fieldnames=UNRESOLVED_FIELDNAMES)
            uw.writeheader()
            uw.writerows(unresolved)

    print(f"\nDone. Total variants: {total}")
    print(f"  Guessed-OK: {guessed_ok}")
    print(f"  Scraped-fallback: {scraped_fallback}")
    print(f"  Unresolved: {len(unresolved)}")
    print(f"Saved -> {OUTPUT_FILE}")
    if unresolved:
        print(f"Unresolved log -> {UNRESOLVED_FILE}")


if __name__ == "__main__":
    main()