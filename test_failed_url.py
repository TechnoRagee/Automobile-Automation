from collections import Counter
import csv

counter = Counter()

with open(
    "output/updated_variants_specs.csv",
    newline="",
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for row in reader:
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
            if not row.get(field, "").strip():
                counter[field] += 1

print(counter)