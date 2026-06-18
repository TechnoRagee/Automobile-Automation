import csv

from variants_specs import scrape_variant

INPUT_FILE = "output/variants_specs.csv"
OUTPUT_FILE = "output/updated_variants_specs.csv"

IMPORTANT_FIELDS = [
    "price",
    "fuel_type",
    "engine",
    "power",
    "torque",
]


def main():

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

        # rows = rows[:100]

    total_retry = 0

    for i, row in enumerate(rows, 1):

        needs_retry = any(
            not row.get(field, "").strip()
            for field in IMPORTANT_FIELDS
        )

        if not needs_retry:
            continue

        variant_url = row.get("variant_url", "").strip()
        if "dbs20072012" not in variant_url:
            continue

        if not variant_url:
            continue

        if "/ix3/" in variant_url and "2-series-gran-coupe" in variant_url:
            print("BAD URL:", variant_url)
            continue

        total_retry += 1

        print(
            f"[{total_retry}] Retrying -> "
            f"{row.get('brand_name','')} "
            f"{row.get('model_name','')}"
        )

        try:
            print(
            row.get("brand_name", ""),
            row.get("model_name", ""),
            row.get("variant_name", ""),
            row.get("variant_url", "")
            )
            new_data = scrape_variant(variant_url)

            if not new_data:
                continue

            # Fill only blank values
            for field in [
                        "price",
                        "fuel_type",
                        "transmission",
                        "engine",
                        "mileage",
                        "power",
                        "torque",
                        "seating_capacity",
                        "airbags",
                        "body_type",
            ]:

                value = new_data.get(field, "")

    # Always update power and torque
                if field in ["power", "torque"]:
                    if value:
                        row[field] = value
                        print(f"updated {field} = {value}")

    # Fill other fields only if blank
                elif not row.get(field, "").strip():
                    if value:
                        row[field] = value
                        print(f"filled {field} = {value}")

        except Exception as e:
            print(
                f"ERROR: {variant_url}"
            )
            print(e)

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as out_f:

        writer = csv.DictWriter(
            out_f,
            fieldnames=rows[0].keys()
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"TOTAL ROWS LOADED: {len(rows)}")
    print(f"Rows retried: {total_retry}")
    print(f"Saved -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()