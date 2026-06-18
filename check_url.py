"""
Standalone URL checker.
Reads a variants CSV (must have a 'variant_url' column), checks each URL's
HTTP status, writes results to output/url_check_results.csv.

Usage:
  python check_urls.py                       (defaults to output/variants1.csv)
  python check_urls.py output/some_file.csv  (custom input)
"""

import csv
import os
import sys
import time
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

DEFAULT_INPUT = "output/variants1.csv"
OUTPUT_FILE = "output/url_check_results.csv"
DELAY = 1.0

OUT_FIELDNAMES = [
    "brand_name", "model_name", "variant_name",
    "variant_url", "status_code", "ok",
]


def check_url(url, retries=2, delay=1):
    """Returns (status_code, ok_bool). status_code -1 if request errored out."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if r.status_code in (403, 405):  # HEAD blocked by server, try GET
                r = requests.get(url, headers=HEADERS, timeout=10)
            return r.status_code, r.status_code == 200
        except requests.RequestException as e:
            print(f"        [retry {attempt}] {e}")
            time.sleep(delay * attempt)
    return -1, False


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT

    if not os.path.exists(input_file):
        print(f"FAILED: input not found -> {input_file}")
        return

    with open(input_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows or "variant_url" not in rows[0]:
        print("FAILED: 'variant_url' column missing from input CSV")
        return

    # rows = rows[101:150]   # TEST ONLY first 20 rows

    print(f"Checking {len(rows)} URLs...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    ok_count = 0
    bad_count = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=OUT_FIELDNAMES)
        writer.writeheader()

        for i, row in enumerate(rows, 1):
            url = row.get("variant_url", "").strip()
            brand = row.get("brand_name", "")
            model = row.get("model_name", "")
            variant = row.get("variant_name", "")

            if not url:
                status, ok = -1, False
            else:
                status, ok = check_url(url)

            ok_count += int(ok)
            bad_count += int(not ok)

            print(f"[{i}/{len(rows)}] {status} {'OK' if ok else 'BAD'} -> {url}")

            writer.writerow({
                "brand_name": brand,
                "model_name": model,
                "variant_name": variant,
                "variant_url": url,
                "status_code": status,
                "ok": ok,
            })
            out_f.flush()
            time.sleep(DELAY)

    print(f"\nDone. Total: {len(rows)}  OK: {ok_count}  BAD: {bad_count}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()