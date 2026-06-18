"""
Shared slugify(). Import this everywhere instead of redefining per-script.
Fixes:
  - decimal point hyphenated, not merged: "4.0 V8" -> "4-0-v8" (was "40-v8")
  - parens hyphenated, not deleted: "Plus(O)" -> "plus-o" (was "pluso")
"""
import re


def slugify(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r'(\d)\.(\d)', r'\1-\2', s)
    s = re.sub(r"[\(\)]", "-", s)
    s = s.replace("/", "-")
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s