"""
Phase 2 variant URL builder — PARALLEL version.
Guess slug -> HEAD check -> fallback real link scrape.
WORKERS = 10 threads for URL checks (lightweight HEAD requests).
"""

import csv
import os
import re
import time
import difflib
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

from slugify_utils import slugify
from dead_models import is_dead_model

BASE_URL = "https://www.carwale.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

MODELS_FILE   = "output/models.csv"
OUTPUT_FILE   = "output/variants1.csv"
UNRESOLVED_FILE = "output/unresolved_variants.csv"

DELAY         = 0.3   # per-thread delay for HEAD checks
WORKERS       = 10    # parallel URL checkers; drop to 5 if getting blocked

FIELDNAMES = [
    "brand_name", "brand_slug", "model_name", "model_slug",
    "variant_name", "variant_slug", "variant_url",
    "data_source", "source_url", "scraped_at",
]
UNRESOLVED_FIELDNAMES = [
    "brand_name", "model_name", "variant_name", "guessed_url", "model_url",
]

_lock = threading.Lock()

BAD_VARIANTS = {
    "nexon", "punch", "sierra", "tiago", "tiago ev", "harrier", "safari",
    "altroz", "curvv", "avinya", "a4", "a6", "q3", "q5", "rs5", "m4", "m5",
    "seal", "atto 3", "sealion 7", "emax 7", "city", "amaze", "elevate",
    "creta", "venue", "exter", "i20", "aircross-x", "basalt-x", "c3-x",
    "ec3", "c5-aircross", "carens", "carens-clavis", "seltos", "sonet",
    "syros", "2 series gran coupe", "3 series lwb", "m340i", "ix1 lwb",
    "ix3", "i7", "z4", "x1", "x3", "x5", "x7",
}


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


def url_exists(url, retries=3, delay=1):
    time.sleep(DELAY)
    for attempt in range(1, retries + 1):
        try:
            r = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return True
            if r.status_code in (403, 405):
                r2 = requests.get(url, headers=HEADERS, timeout=15)
                return r2.status_code == 200
            if r.status_code == 404:
                return False
        except requests.RequestException as e:
            print(f"        [head-retry {attempt}] {e}")
            time.sleep(delay * attempt)
    return False


def get_version_names(html, model_slug):
    if not html:
        return []
    versions = re.findall(r'"VersionName":"([^"]+)"', html, re.I)
    clean_versions = []
    for v in versions:
        if model_slug in ["ix3", "new-c5-aircross", "basalt-ev", "syros-ev", "ev5"]:
            if v.lower().strip() in BAD_VARIANTS:
                continue
        clean_versions.append(v)
    return sorted(dict.fromkeys(clean_versions))


def get_real_variant_links(html, brand_slug, model_slug):
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
    if not real_links:
        return None
    target = version_name.lower()
    if target in real_links:
        return real_links[target]
    match = difflib.get_close_matches(target, real_links.keys(), n=1, cutoff=0.6)
    return real_links[match[0]] if match else None


def check_variant(args):
    """Per-thread: check one variant URL, return result dict."""
    brand_name, brand_slug, model_name, model_slug, model_url, version_name, real_links_ref = args

    variant_slug = slugify(version_name)
    guessed_url = f"{BASE_URL}/{brand_slug}-cars/{model_slug}/{variant_slug}/"

    if url_exists(guessed_url):
        return {
            "brand_name": brand_name, "brand_slug": brand_slug,
            "model_name": model_name, "model_slug": model_slug,
            "variant_name": version_name, "variant_slug": variant_slug,
            "variant_url": guessed_url, "data_source": "guessed",
            "source_url": model_url,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_status": "guessed",
        }

    # fallback: use pre-scraped real links
    real_links = real_links_ref[0] or {}
    real_url = resolve_real_url(version_name, real_links)
    if real_url:
        return {
            "brand_name": brand_name, "brand_slug": brand_slug,
            "model_name": model_name, "model_slug": model_slug,
            "variant_name": version_name, "variant_slug": variant_slug,
            "variant_url": real_url, "data_source": "scraped_real_link",
            "source_url": model_url,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_status": "scraped",
        }

    return {
        "brand_name": brand_name, "brand_slug": brand_slug,
        "model_name": model_name, "model_slug": model_slug,
        "variant_name": version_name, "variant_slug": variant_slug,
        "variant_url": "", "data_source": "",
        "source_url": model_url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "guessed_url": guessed_url,
        "_status": "unresolved",
    }


# ── main ──────────────────────────────────────────────────────────────────

def main():
    with open(MODELS_FILE, newline="", encoding="utf-8") as f:
        all_models = list(csv.DictReader(f))

    models = all_models
    print(f"Models found: {len(models)}")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    all_tasks = []

    # Phase A: fetch all model pages sequentially (fast, no bottleneck here)
    # then batch all variant URL checks in parallel
    print("Phase A: fetching model pages...")
    for i, model in enumerate(models, 1):
        brand_name = model.get("brand_name", "")
        brand_slug = model.get("brand_slug", "")
        model_name = model.get("model_name", "")
        model_slug = model.get("model_slug", "")
        model_url  = model.get("model_url", "")

        print(f"  [{i}/{len(models)}] {brand_name} {model_name}", end="")

        if is_dead_model(model_slug):
            print(" SKIPPED")
            continue

        html = fetch(model_url)
        if not html:
            print(" FETCH FAILED")
            continue

        versions = get_version_names(html, model_slug)
        if not versions:
            print(" no versions")
            continue

        # parse real links once per model (shared ref for all variants)
        real_links = get_real_variant_links(html, brand_slug, model_slug)
        real_links_ref = [real_links]  # mutable ref passed to threads

        print(f" -> {len(versions)} versions")
        for v in versions:
            all_tasks.append((brand_name, brand_slug, model_name, model_slug, model_url, v, real_links_ref))

    print(f"\nPhase B: checking {len(all_tasks)} variant URLs with {WORKERS} workers...")

    rows = []
    unresolved = []
    guessed_ok = scraped_fallback = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(check_variant, t): t for t in all_tasks}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            done += 1
            status = result.pop("_status")
            guessed_url = result.pop("guessed_url", "")

            if status == "guessed":
                guessed_ok += 1
            elif status == "scraped":
                scraped_fallback += 1
            else:
                unresolved.append({
                    "brand_name": result["brand_name"],
                    "model_name": result["model_name"],
                    "variant_name": result["variant_name"],
                    "guessed_url": guessed_url,
                    "model_url": result["source_url"],
                })
                print(f"  UNRESOLVED: {result['variant_name']}")

            rows.append(result)
            if done % 100 == 0:
                print(f"  ... {done}/{len(all_tasks)} checked")

    # write all at once (order not guaranteed due to parallel)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    if unresolved:
        with open(UNRESOLVED_FILE, "w", newline="", encoding="utf-8") as uf:
            uw = csv.DictWriter(uf, fieldnames=UNRESOLVED_FIELDNAMES)
            uw.writeheader()
            uw.writerows(unresolved)

    print(f"\nDone. Total variants: {len(rows)}")
    print(f"  Guessed-OK: {guessed_ok}")
    print(f"  Scraped-fallback: {scraped_fallback}")
    print(f"  Unresolved: {len(unresolved)}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()