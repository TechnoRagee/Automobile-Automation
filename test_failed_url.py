from collections import Counter
import csv

counter = Counter()

with open("output/failed_urls.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        for field in row["missing_fields"].split(";"):
            if field:
                counter[field] += 1

print(counter)