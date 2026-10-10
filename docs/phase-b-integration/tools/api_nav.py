"""Rewrite API.md's staff part of the Contents block from the headings in file order (Insights (staff) … Lists)."""
import re, textwrap
from pathlib import Path
p = Path("examleaf-web/API.md"); lines = p.read_text().split("\n")
heads = [l[3:] for l in lines if l.startswith("## ")]
first, last = heads.index("Insights (staff)"), heads.index("Lists")
anchor = lambda h: re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
links = [f"[{h}](#{anchor(h)})" for h in heads[first:last + 1]]
links += ["[Staff API](#staff-api)", "[Errors](#errors)", "[Rate limits](#rate-limits)", "[CORS](#cors)", "[Versioning](#versioning)", "[Operations](#operations)"]
block = textwrap.wrap(" · ".join(links), width=118, break_long_words=False, break_on_hyphens=False)
block = [l + " ·" if i < len(block) - 1 else l for i, l in enumerate(block)]
start = next(i for i, l in enumerate(lines) if l.startswith("[Insights (staff)](#insights-staff)"))
end = next(i for i, l in enumerate(lines) if i > start and l.startswith("[Versioning](#versioning)")) + 1
lines[start:end] = block
p.write_text("\n".join(lines)); print("API.md nav:", len(links), "links,", len(block), "lines")
