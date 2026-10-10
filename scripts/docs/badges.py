#!/usr/bin/env python3
"""The documents' badges: local SVG files drawn from docs/assets/badges/badges.json (no external service, so every
document renders offline and never calls out). Usage: python scripts/docs/badges.py  (writes the SVGs; idempotent)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "docs" / "assets" / "badges"
COLOURS = {
    "slate": "#475569", "green": "#15803d", "amber": "#b45309", "red": "#b91c1c", "blue": "#1d4ed8",
    "violet": "#6d28d9", "teal": "#0f766e", "ink": "#0b2a5b", "grey": "#555555",
}
FAMILY = {"component": "slate", "tests": "blue", "audience": "violet", "law": "teal", "phase": "green", "status": "green"}
CHAR = 6.4  # the average glyph width of the badge's font at 11 px, for a width close to the text's


def width(text):
    return int(len(text) * CHAR) + 12


def badge(label, value, colour):
    left, right = width(label), width(value)
    total = left + right
    fill = COLOURS.get(colour, colour)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#fff" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <clipPath id="r"><rect width="{total}" height="20" rx="4" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{left}" height="20" fill="#2f3542"/>
    <rect x="{left}" width="{right}" height="20" fill="{fill}"/>
    <rect width="{total}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{left / 2:.1f}" y="14" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{left / 2:.1f}" y="13">{label}</text>
    <text x="{left + right / 2:.1f}" y="14" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{left + right / 2:.1f}" y="13">{value}</text>
  </g>
</svg>
"""


def main():
    spec = json.loads((HERE / "badges.json").read_text())
    written = 0
    for name, entry in spec.items():
        family = name.split("-", 1)[0]
        colour = entry.get("colour") or FAMILY.get(family, "grey")
        (HERE / f"{name}.svg").write_text(badge(entry["label"], entry["value"], colour))
        written += 1
    print(f"{written} badges written to {HERE.relative_to(Path.cwd()) if HERE.is_relative_to(Path.cwd()) else HERE}")


if __name__ == "__main__":
    main()
