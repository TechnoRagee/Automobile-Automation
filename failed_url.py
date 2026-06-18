"""
Find failed/empty variant rows from output/variants_specs.csv.
A row counts as failed if:
  - variant_url empty, OR
  - all SPEC_FIELDS empty (fetch likely failed / page had no data)
Writes failed rows to output/failed_urls.csv
"""

import csv
import os

INPUT_FILE = "output/variants_specs.csv"
OUTPUT_FILE = "output/failed_urls.csv"

SPEC_FIELDS = [
    "price", "fuel_type", "transmission", "engine", "mileage",
    "power", "torque", "seating_capacity", "airbags", "body_type",
]
IMPORTANT_FIELDS = [
    "price",
    "fuel_type",
    "engine",
    "power",
    "torque",
]

OUT_FIELDNAMES = [
    "brand_name",
    "brand_slug",
    "model_name",
    "model_slug",
    "variant_name",
    "variant_url",
    "missing_fields",
]


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"FAILED: input not found -> {INPUT_FILE}")
        return

    failed = []

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("variant_url", "").strip()
            missing = [k for k in SPEC_FIELDS if not row.get(k, "").strip()]

            important_missing = [
                k for k in IMPORTANT_FIELDS
                if not row.get(k,"").strip()
            ]

            if (
                not url
                or len(missing) == len(SPEC_FIELDS)
                or important_missing
                ):
                failed.append({
                    "brand_name": row.get("brand_name", ""),
                    "model_name": row.get("model_name", ""),
                    "variant_name": row.get("variant_name", ""),
                    "variant_url": url,
                    "missing_fields": ";".join(missing),
                    "brand_slug": row.get("brand_slug", ""),
                    "model_slug": row.get("model_slug", ""),
                })

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=OUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(failed)

    print(f"Total rows checked: {sum(1 for _ in open(INPUT_FILE, encoding='utf-8')) - 1}")
    print(f"Failed/empty rows: {len(failed)}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()