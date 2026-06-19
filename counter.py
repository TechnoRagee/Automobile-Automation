import csv
from collections import Counter

with open("output/variants1.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

bad = Counter()
total = Counter()
for r in rows:
    total[r["model_slug"]] += 1
    if not r["variant_url"]:
        bad[r["model_slug"]] += 1

for slug, t in total.items():
    if bad[slug] == t:
        print(slug)