"""
Models confirmed to have no real CarWale spec page — pages exist but
VersionName JSON pulls from a "related models" widget instead of the
model's own data, producing garbage variant rows that all 404.

Use in 02_extract_models.py: skip any model whose slug is in this set
BEFORE it ever reaches Phase 3 variant scraping.
"""

DEAD_MODEL_SLUGS = {
    "new-c5-aircross",
    "basalt-ev",
    "basalt",
    # add more here as discovered via check_urls.py output
    # (pattern: ALL variants for a model 404 + variant names match
    # other unrelated model names -> add slug here)
}


def is_dead_model(model_slug: str) -> bool:
    return model_slug in DEAD_MODEL_SLUGS