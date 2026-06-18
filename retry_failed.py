import csv
from datetime import datetime

from fallback import cardekho_fallback
import re

INPUT_FILE = "output/failed_urls.csv"
OUTPUT_FILE = "output/fixed_failed.csv"


def slugify(text):
    text = (text or "").lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def main():
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # TEST ONLY FIRST 10
    rows = rows[:3]

    fixed_rows = []

    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row.get('brand_name','')} {row.get('model_name','')}")

        data = {
            "price": "",
            "fuel_type": "",
            "transmission": "",
            "engine": "",
            "mileage": "",
            "power": "",
            "torque": "",
            "seating_capacity": "",
            "airbags": "",
            "body_type": "",
        }

        brand_slug = slugify(row.get("brand_name", ""))
        model_slug = slugify(row.get("model_name", ""))

        data = cardekho_fallback(
            data,
            brand_slug,
            model_slug
        )

        fixed_rows.append({
            "brand_name": row.get("brand_name", ""),
            "model_name": row.get("model_name", ""),
            "variant_name": row.get("variant_name", ""),
            "variant_url": row.get("variant_url", ""),
            "price": data.get("price", ""),
            "fuel_type": data.get("fuel_type", ""),
            "transmission": data.get("transmission", ""),
            "engine": data.get("engine", ""),
            "mileage": data.get("mileage", ""),
            "power": data.get("power", ""),
            "torque": data.get("torque", ""),
            "seating_capacity": data.get("seating_capacity", ""),
            "airbags": row.get("airbags", "") or data.get("airbags", ""),
            "body_type": data.get("body_type", ""),
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    if fixed_rows:
        with open(
            OUTPUT_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as out_f:

            writer = csv.DictWriter(
                out_f,
                fieldnames=list(fixed_rows[0].keys())
            )

            writer.writeheader()
            writer.writerows(fixed_rows)

        print(f"\nSaved -> {OUTPUT_FILE}")
    else:
        print("No rows fixed.")


if __name__ == "__main__":
    main()