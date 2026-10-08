#!/usr/bin/env python3
"""ExamLeaf atlas, part 2: the PDF. Reads manifest.json and the PNGs of capture.mjs and renders, with WeasyPrint,
A4 landscape pages: a cover, the contents (by area), one or more pages for each capture with its caption, and an
appendix (the parity document's rows, the Django-only routes, the API's endpoints).

    examleaf-web/.venv/bin/python build.py --manifest <out>/manifest.json --repo <checkout> --out atlas.pdf

How a capture is placed (a full-page screenshot is taller than a page):
  * desktop (1280 px): scaled to the page's width; a capture taller than one page continues on the next pages, cut
    where a row of the picture is blank (so that a line of text is not cut in two); one a little taller than a page is
    shrunk to fit it;
  * phone (390 px): two columns to a page, each with its own caption; a capture's parts run down the left column and
    on into the right one, and the next capture starts in the next free column of the same scene (a new scene starts a
    new page);
  * a very tall page was kept by capture.mjs as its first screens and its last two: the caption says so.
Pictures are JPEG (quality 75, at most 1600 px wide), shrunk step by step until the file is under --budget-mb.
"""

import argparse
import html
import json
import math
import re
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--manifest", default="manifest.json")
ap.add_argument("--root", help="folder the manifest's file names are relative to (default: the manifest's folder)")
ap.add_argument("--repo", default=str(HERE.parents[2]), help="checkout holding docs/design/parity-nextjs.md and examleaf-web/API.md")
ap.add_argument("--out", default="examleaf-pages.pdf")
ap.add_argument("--work", help="folder for the JPEG strips (default: next to the PDF)")
ap.add_argument("--budget-mb", type=float, default=58.0)
ap.add_argument("--date", default="9 October 2026")
ap.add_argument("--limit", type=int, help="only the first N captures (to try the layout)")
ap.add_argument("--quality", type=int, default=75)
ap.add_argument("--max-width", type=int, default=1600, help="widest picture, in pixels")
args = ap.parse_args()

MANIFEST = Path(args.manifest).resolve()
ROOT = Path(args.root).resolve() if args.root else MANIFEST.parent
REPO = Path(args.repo).resolve()
OUT = Path(args.out).resolve()
WORK = Path(args.work).resolve() if args.work else OUT.parent / (OUT.stem + "-work")
WORK.mkdir(parents=True, exist_ok=True)
manifest = json.loads(MANIFEST.read_text())
captures = manifest["captures"][: args.limit] if args.limit else manifest["captures"]
areas = list(manifest["areas"].values())

# ---------------------------------------------------------------------------------------------------- page geometry (mm)
PAGE_W, PAGE_H = 297.0, 210.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 8.0, 6.0, 9.0
BODY_W = PAGE_W - 2 * MARGIN_X  # 281
BODY_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM  # 195
CAP_H = 13.0  # a caption
GAP = 7.0  # between the two phone columns
COL_W = (BODY_W - GAP) / 2  # 137
DESK_IMG_H = BODY_H - CAP_H - 2.0
PHONE_IMG_H = BODY_H - CAP_H - 2.0
FIT = 1.2  # a capture up to this much taller than a page is shrunk to it instead of cut


def esc(text):
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------------------------------- pictures
def blank_row(image, y, tolerance=6):
    """Whether row y of the picture is one flat colour (a gap between blocks): a safe place to cut."""
    box = image.crop((0, y, image.width, y + 1)).getextrema()
    return all(hi - lo <= tolerance for lo, hi in box)


def cut_points(image, count, window):
    """count-1 rows that divide the picture into count strips of about the same height, each moved to the nearest blank
    row within `window` rows."""
    height = image.height
    points = []
    last = 0
    for k in range(1, count):
        target = round(k * height / count)
        best = None
        for delta in range(0, window + 1):
            for y in (target - delta, target + delta):
                if last + 20 < y < height - 20 and blank_row(image, y):
                    best = y
                    break
            if best is not None:
                break
        points.append(max(best if best is not None else target, last + 20))
        last = points[-1]
    return points


def strips_of(png, viewport, scale, quality, tag):
    """The picture as a list of (jpeg path, width mm, height mm): one page's worth each, per the layout above. A strip
    already made at this scale and quality (a file of this tag) is read back, not made again."""
    col_w = BODY_W if viewport == "desktop" else COL_W
    body_h = DESK_IMG_H if viewport == "desktop" else PHONE_IMG_H
    made = sorted(WORK.glob(f"{tag}-*.jpg"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
    if made and (WORK / f"{tag}.done").exists():
        files = made
        parts = []
        for name in files:
            with Image.open(name) as part:
                parts.append((name, part.width, part.height))
        mm_per_px = col_w / parts[0][1]
    else:
        for old in made:
            old.unlink()
        image = Image.open(png).convert("RGB")
        scale = min(scale, args.max_width / image.width)
        if scale != 1.0:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        mm_per_px = col_w / image.width  # the width of the page (or column) is the picture's width
        body_px = body_h / mm_per_px
        count = max(1, math.ceil(image.height / body_px * 0.97))
        if count == 1 or image.height <= body_px * FIT:
            count, points = 1, []
        else:
            points = cut_points(image, count, window=round(body_px * 0.12))
        bounds = [0, *points, image.height]
        parts = []
        for index in range(len(bounds) - 1):
            part = image.crop((0, bounds[index], image.width, bounds[index + 1])) if count > 1 else image
            name = WORK / f"{tag}-{index + 1}.jpg"
            part.save(name, "JPEG", quality=quality, optimize=True)
            parts.append((name, part.width, part.height))
        (WORK / f"{tag}.done").write_text("ok")
    result = []
    for name, width_px, height_px in parts:
        width_mm, height_mm = width_px * mm_per_px, height_px * mm_per_px
        if height_mm > body_h:  # a little too tall (the 20 % allowance): shrunk to fit
            width_mm, height_mm = width_mm * body_h / height_mm, body_h
        result.append((name, width_mm, height_mm))
    return result


# ---------------------------------------------------------------------------------------------------- the manifest as parts
def scene_key(capture):
    return re.sub(r"^\d+-|-(desktop|phone)$", "", capture["id"])


def area_rank(capture):
    return areas.index(capture["area"]) if capture["area"] in areas else len(areas)


def group_key(capture):
    return (capture["area"], capture.get("scene", ""), scene_key(capture))


first_seen = {}
for capture in captures:
    key = group_key(capture)
    first_seen[key] = min(first_seen.get(key, 10**9), capture.get("seq", 0))
# by area, by scene in the order the scenes are written, then each picture of a scene with its phone twin after it
captures = sorted(
    captures,
    key=lambda c: (area_rank(c), c.get("order", 0), first_seen[group_key(c)], 0 if c["viewport"] == "desktop" else 1, c.get("seq", 0)),
)


def parts_of(capture):
    """(label, file, note) for each picture of a capture: one, or the first screens and the end of a long page."""
    if "truncated" in capture:
        t = capture["truncated"]
        return [
            ("first screens", capture["file"], f"the first {t['top_css']:,} px of {capture['page_height_css']:,}"),
            ("end of the page", t["tail_file"], f"the last {t['tail_css']:,} px; {t['omitted_css']:,} px between are left out"),
        ]
    return [("", capture["file"], "")]


def prepare(desktop_scale, phone_scale, quality):
    """Cut every capture into its strips at these scales; returns {capture id: [(label, note, [(jpg, w, h)])]} and the
    size of all the JPEG files."""
    total = 0
    cut = {}
    for capture in captures:
        scale = desktop_scale if capture["viewport"] == "desktop" else phone_scale
        items = []
        for number, (label, file, note) in enumerate(parts_of(capture)):
            tag = f"v2-{capture['id']}-{number}-{int(scale * 100)}-q{quality}"
            png = ROOT / file
            items.append((label, note, strips_of(png, capture["viewport"], scale, quality, tag)))
        cut[capture["id"]] = items
        total += sum(p.stat().st_size for _, _, strips in items for p, _, _ in strips)
    return cut, total


budget = args.budget_mb * 1024 * 1024
# desktop first: it is the larger picture of the two to read; the phone's pictures are 2x and give way first
attempts = [(1.0, 1.0), (1.0, 0.85), (1.0, 0.75), (1.0, 0.65), (1.0, 0.55), (0.9, 0.55), (0.85, 0.5), (0.8, 0.45), (0.7, 0.4)]
overhead = 3 * 1024 * 1024  # fonts, text, the tables
for desktop_scale, phone_scale in attempts:
    print(f"strips at desktop x{desktop_scale}, phone x{phone_scale}, JPEG q{args.quality} ...", flush=True)
    cut, size = prepare(desktop_scale, phone_scale, args.quality)
    print(f"  {size / 1048576:.1f} MB of pictures", flush=True)
    if size + overhead <= budget:
        break

# ---------------------------------------------------------------------------------------------------- caption and pages
VIEWPORT_WORDS = {"desktop": "desktop 1280 px", "phone": "phone 390 px"}
WHO = {"anonymous": "not signed in", "student": "signed in as a student", "staff": "signed in as staff"}


def caption(capture, label, note, index, count, compact=False, first=False):
    route = esc(capture["route"])
    pattern = f' <span class="pat">({esc(capture["pattern"])})</span>' if capture.get("pattern") and capture["pattern"] != capture["route"] else ""
    where = f"part {index} of {count}" if count > 1 else ""
    bits = [VIEWPORT_WORDS[capture["viewport"]], WHO.get(capture.get("who", "anonymous"), capture.get("who", ""))]
    if label:
        bits.append(f"{label}: {note}")
    if where:
        bits.append(where)
    title = capture.get("title") or ""
    status = capture.get("status")
    return (
        f'<div class="cap{" compact" if compact else ""}{" first" if first else ""}">'
        f'<div class="l1"><span class="route">{route}</span>{pattern}<span class="dash"> — </span><span class="state">{esc(capture["state"])}</span></div>'
        f'<div class="l2">{esc(" · ".join(bits))}'
        f'{f" · page title “{esc(title)}”" if title else ""}{f" · HTTP {status}" if status and status != 200 else ""}</div>'
        f"</div>"
    )


def anchor(capture):
    return f"c-{capture['id']}"


pages = []  # HTML of every capture page, in order
page_of = {}  # capture id -> first page (filled while building)
area_open = None
phone_buffer = []  # (capture, label, note, index, count, strip) waiting for a column


def flush_phone():
    global phone_buffer
    while phone_buffer:
        two = phone_buffer[:2]
        phone_buffer = phone_buffer[2:]
        columns = []
        for capture, label, note, index, count, (jpg, w, h), first in two:
            ident = f' id="{anchor(capture)}"' if first else ""
            columns.append(
                f'<div class="col"{ident}>{caption(capture, label, note, index, count, compact=True, first=first)}'
                f'<div class="img"><img src="{jpg.as_uri()}" style="width:{w:.2f}mm;height:{h:.2f}mm"></div></div>'
            )
        pages.append(f'<section class="pg phone">{"".join(columns)}</section>')


def area_marker(area):
    ident = re.sub(r"\W+", "-", area.lower()).strip("-")
    return f'<h1 class="area" id="area-{ident}">{esc(area)}</h1>'


for capture in captures:
    if capture["area"] != area_open:
        flush_phone()
        pages.append(area_marker(capture["area"]))
        area_open = capture["area"]
    if capture["viewport"] == "desktop":
        flush_phone()
        pieces = cut[capture["id"]]
        total = sum(len(strips) for _, _, strips in pieces)
        index = 0
        for label, note, strips in pieces:
            for jpg, w, h in strips:
                index += 1
                ident = f' id="{anchor(capture)}"' if index == 1 else ""
                pages.append(
                    f'<section class="pg desk"{ident}>{caption(capture, label, note, index, total, first=index == 1)}'
                    f'<div class="img"><img src="{jpg.as_uri()}" style="width:{w:.2f}mm;height:{h:.2f}mm"></div></section>'
                )
    else:
        pieces = cut[capture["id"]]
        total = sum(len(strips) for _, _, strips in pieces)
        index = 0
        for label, note, strips in pieces:
            for strip in strips:
                index += 1
                phone_buffer.append((capture, label, note, index, total, strip, index == 1))
flush_phone()

# ---------------------------------------------------------------------------------------------------- contents
rows_by_area = {}
for capture in captures:
    rows_by_area.setdefault(capture["area"], {}).setdefault(scene_key(capture), {})[capture["viewport"]] = capture


def toc_rows():
    out = []
    for area in areas:
        scenes = rows_by_area.get(area)
        if not scenes:
            continue
        ident = re.sub(r"\W+", "-", area.lower()).strip("-")
        out.append(f'<tr class="area"><th colspan="4"><a href="#area-{ident}">{esc(area)}</a></th></tr>')
        for key, by_view in scenes.items():
            first = by_view.get("desktop") or by_view.get("phone")
            cells = []
            for view in ("desktop", "phone"):
                if view in by_view:
                    cells.append(f'<td class="pg-no"><a class="ref" href="#{anchor(by_view[view])}"></a></td>')
                else:
                    cells.append('<td class="pg-no">·</td>')
            out.append(
                f'<tr><td class="route"><code>{esc(first["route"])}</code></td><td class="state">{esc(first["state"])}</td>{cells[0]}{cells[1]}</tr>'
            )
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------- appendix
def inline(text):
    """A table cell of the Markdown documents: `code` and plain text."""
    text = esc(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def tables_of(markdown):
    """[(heading, rows)] for each pipe table under a '## ' heading; rows are lists of cell texts (header first)."""
    result, heading, rows = [], "", []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if rows:
                result.append((heading, rows))
            heading, rows = line[3:].strip(), []
        elif line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            rows.append(cells)
        elif rows and not line.strip().startswith("|"):
            if line.strip():
                continue
    if rows:
        result.append((heading, rows))
    return result


def norm(route):
    route = route.split("?")[0].split("#")[0].strip().lower()
    route = re.sub(r"<[^>]+>(?:-<[^>]+>)+", "*", route)
    route = re.sub(r"<[^>]+>", "*", route)
    return route


captured = {}
for capture in captures:
    for part in [capture["route"], *(capture.get("pattern") or "").split()]:
        captured.setdefault(norm(part), []).append(capture)


def refs_for(routes):
    """The captures of any of these routes, as links with page numbers."""
    found = {}
    for route in routes:
        for capture in captured.get(norm(route), []):
            found.setdefault(scene_key(capture), {})[capture["viewport"]] = capture
    links = []
    for key, by_view in found.items():
        for view in ("desktop", "phone"):
            if view in by_view:
                links.append(f'<a class="ref v-{view}" href="#{anchor(by_view[view])}"></a>')
    return links


parity_md = (REPO / "docs/design/parity-nextjs.md").read_text()
api_md = (REPO / "examleaf-web/API.md").read_text()
parity_rows = []
for heading, rows in tables_of(parity_md):
    if not rows or rows[0][:1] != ["Django route"]:
        continue
    for cells in rows[1:]:
        if len(cells) >= 4:
            parity_rows.append((heading, *cells[:4]))
# sections A to F have their own heading; G, H and I share one
django_only = [row for row in parity_rows if row[3].strip().lower().startswith("django")]
api_rows = [row for row in parity_rows if row[3].strip().lower() == "api"]
api_endpoints = []
for heading, rows in tables_of(api_md):
    if heading == "Endpoints" and rows and rows[0][:2] == ["Method", "Path"]:
        api_endpoints = rows[1:]
stays = re.search(r"## Django-only routes that stay\s+(.+)", parity_md, re.S)
stays_text = stays.group(1).strip().split("\n\n")[0] if stays else ""


def section_of(heading):
    found = re.match(r"^([A-I])\.", heading)
    return "G–I" if heading.startswith("G.") else (found.group(1) if found else "")


def parity_table():
    out = []
    for heading, django_route, next_route, status, notes in parity_rows:
        routes = re.findall(r"`([^`]+)`", django_route)
        kind = status.strip().lower()
        if kind.startswith("built"):
            links = refs_for(routes)
            note = " ".join(links) if links else "built, not captured"
        elif kind.startswith("redirect"):
            target = re.findall(r"`([^`]+)`", next_route) or re.findall(r"→\s*(\S+)", next_route)
            links = refs_for(target)
            note = f"redirects to {inline(next_route.lstrip('→ ').strip())} " + " ".join(links)
        elif kind == "api":
            note = f"a form post of the Django page: the API ({inline(notes)})"
        elif kind.startswith("django"):
            note = "answered by Django (see the table of Django-only routes)"
        else:
            note = "not built"
        out.append(
            f'<tr><td class="sec">{esc(section_of(heading))}</td><td>{inline(django_route)}</td><td>{inline(next_route)}</td><td class="st st-{re.sub("[^a-z]", "", kind)}">{esc(status)}</td><td>{note}</td></tr>'
        )
    return "\n".join(out)


def simple_table(head, rows, widths=None):
    cols = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = "\n".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="plain"><thead><tr>{cols}</tr></thead><tbody>{body}</tbody></table>'


failure_rows = "".join(
    f"<tr><td><code>{esc(f.get('url') or f['id'])}</code></td><td>{esc(f['id'])} {esc(f.get('viewport', ''))}</td><td>{esc(f['error'][:200])}</td></tr>"
    for f in manifest.get("failures", [])
)

# ---------------------------------------------------------------------------------------------------- the document
meta = manifest.get("meta", {})
count_scenes = sum(len(v) for v in rows_by_area.values())
css = f"""
@page {{ size: {PAGE_W}mm {PAGE_H}mm; margin: {MARGIN_TOP}mm {MARGIN_X}mm {MARGIN_BOTTOM}mm;
  @bottom-left {{ content: string(area); font: 7.5pt "Helvetica Neue", Helvetica, Arial, sans-serif; color: #5d6675; vertical-align: top; padding-top: 2mm; }}
  @bottom-center {{ content: "ExamLeaf — every page, {esc(args.date)}"; font: 7.5pt "Helvetica Neue", Helvetica, Arial, sans-serif; color: #8a93a3; vertical-align: top; padding-top: 2mm; }}
  @bottom-right {{ content: counter(page); font: 7.5pt "Helvetica Neue", Helvetica, Arial, sans-serif; color: #5d6675; vertical-align: top; padding-top: 2mm; }} }}
@page cover {{ margin: 0; background: #0b2a5b; @bottom-left {{ content: none }} @bottom-center {{ content: none }} @bottom-right {{ content: none }} }}
html {{ font: 9pt/1.35 "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1c2430; }}
code {{ font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 0.92em; }}
h1.area {{ string-set: area content(); bookmark-level: 1; bookmark-label: content(); height: 0; margin: 0; overflow: hidden; font-size: 0; line-height: 0; }}
.cover {{ page: cover; height: {PAGE_H}mm; width: {PAGE_W}mm; padding: 28mm 26mm; box-sizing: border-box; color: #fff; page-break-after: always; position: relative; }}
.cover .leaf {{ width: 18mm; height: 18mm; border-radius: 4mm; background: #48c164; display: block; margin-bottom: 14mm; }}
.cover h1 {{ font-size: 40pt; line-height: 1.08; margin: 0 0 8mm; letter-spacing: -0.5pt; }}
.cover h1 em {{ font-style: normal; color: #6fd68c; }}
.cover p {{ font-size: 13pt; max-width: 190mm; color: #cfd8ea; margin: 0 0 4mm; }}
.cover .stats {{ position: absolute; left: 26mm; bottom: 24mm; font-size: 10pt; color: #9fb0d0; }}
.cover .stats b {{ color: #fff; font-size: 20pt; display: block; line-height: 1.1; }}
.cover .stats span {{ display: inline-block; margin-right: 14mm; }}
.sheet {{ page-break-after: always; }}
.sheet h2 {{ font-size: 18pt; margin: 0 0 4mm; color: #0b2a5b; bookmark-level: 1; bookmark-label: content(); }}
.sheet h3 {{ font-size: 11pt; margin: 5mm 0 1.5mm; color: #0b2a5b; }}
.sheet p, .sheet li {{ font-size: 9pt; max-width: 250mm; }}
.sheet ul {{ margin: 0 0 2mm 4mm; padding: 0; }}
.toc table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
.toc td, .toc th {{ padding: 0.9mm 1.5mm; border-bottom: 0.2mm solid #e2e6ee; text-align: left; vertical-align: top; }}
.toc tr {{ break-inside: avoid; }}
.toc tr.area th {{ background: #0b2a5b; color: #fff; font-size: 9pt; padding: 1.2mm 2mm; border: 0; }}
.toc tr.area th a {{ color: #fff; text-decoration: none; }}
.toc td.route {{ width: 62mm; }}
.toc td.pg-no {{ width: 17mm; text-align: right; white-space: nowrap; }}
.toc thead th {{ background: #eef1f7; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .4pt; color: #5d6675; }}
a {{ color: inherit; text-decoration: none; }}
a.ref::after {{ content: target-counter(attr(href url), page); color: #1a5fb4; font-weight: 600; }}
a.ref.v-desktop::before {{ content: "d "; color: #8a93a3; font-size: 0.85em; }}
a.ref.v-phone::before {{ content: "p "; color: #8a93a3; font-size: 0.85em; }}
td a.ref + a.ref {{ margin-left: 2mm; }}
.pg {{ height: {BODY_H}mm; width: {BODY_W}mm; page-break-after: always; overflow: hidden; position: relative; }}
.pg.phone {{ display: flex; gap: {GAP}mm; align-items: flex-start; }}
.col {{ width: {COL_W}mm; }}
.cap {{ height: {CAP_H}mm; box-sizing: border-box; padding: 1.2mm 2.5mm 0; background: #eef1f7; border-left: 1.2mm solid #0b2a5b; margin-bottom: 2mm; overflow: hidden; }}
.cap .l1 {{ font-size: 9.5pt; font-weight: 700; color: #0b2a5b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.cap .route {{ font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 9pt; }}
.cap .pat {{ font-weight: 400; color: #5d6675; font-size: 8pt; }}
.cap .dash {{ font-weight: 400; color: #8a93a3; }}
.cap .state {{ font-weight: 600; color: #1c2430; }}
.cap .l2 {{ font-size: 7.3pt; color: #5d6675; margin-top: 0.6mm; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.cap.first .l1 {{ bookmark-level: 2; bookmark-label: content(); }}
.cap.compact {{ padding: 1mm 2mm 0; }}
.cap.compact .l1 {{ font-size: 8pt; white-space: normal; max-height: 8mm; line-height: 1.15; }}
.cap.compact .route {{ font-size: 7.5pt; }}
.cap.compact .pat {{ display: none; }}
.cap.compact .l2 {{ font-size: 6.4pt; white-space: normal; max-height: 5mm; line-height: 1.15; }}
.img {{ text-align: center; }}
.img img {{ display: block; margin: 0 auto; box-shadow: 0 0 0 0.25mm #c9cfdb; }}
table.plain {{ width: 100%; border-collapse: collapse; font-size: 7.6pt; margin-bottom: 3mm; }}
table.plain th {{ background: #eef1f7; text-align: left; padding: 1mm 1.5mm; font-size: 7.3pt; text-transform: uppercase; letter-spacing: .3pt; color: #5d6675; }}
table.plain td {{ padding: 0.8mm 1.5mm; border-bottom: 0.2mm solid #e2e6ee; vertical-align: top; }}
table.plain tr {{ break-inside: avoid; }}
table.plain thead {{ display: table-header-group; }}
td.sec {{ font-weight: 700; color: #0b2a5b; width: 8mm; }}
td.st {{ white-space: nowrap; font-weight: 600; }}
td.st-built {{ color: #1a7a38; }} td.st-redirected {{ color: #8a5a00; }} td.st-api {{ color: #1a5fb4; }} td.st-django {{ color: #6b2fa3; }} td.st-notbuilt {{ color: #b3261e; }}
"""

body = []
body.append(
    f"""<section class="cover"><span class="leaf"></span>
<h1>ExamLeaf &mdash; <em>every page</em>, {esc(args.date)}</h1>
<p>All the pages of the Next.js website and of the Django admin, at 1280 px and at 390 px, signed out and signed in, in the states that
matter: gated and open, empty and full, an error, no connection.</p>
<p>Taken from a production build of the frontend on a fresh database, with temporary accounts that were deleted afterwards.</p>
<div class="stats"><span><b>{len(captures)}</b>captures</span><span><b>{count_scenes}</b>pages and states</span><span><b>{{PAGES}}</b>pages in this file</span></div></section>"""
)
notes = [
    ("What was run", [
        f"The frontend: <code>npm run build</code> and <code>npm start</code> (Next.js, production) at <code>{esc(meta.get('base', ''))}</code>; Django 8108 behind it, <code>DEBUG=0</code>, collected static files, a fresh SQLite database, console email, no SMS gateway, no Razorpay keys, cash on delivery off, the shop open.",
        f"Commit of the checkout: <code>{esc((meta.get('commit') or 'unknown')[:12])}</code> (<code>origin/main</code>). Taken with headless Chromium (Playwright): desktop 1280 x 900 at 1x, phone 390 x 844 at 2x with touch, reduced motion on (entry animations are off, so nothing is half drawn).",
        "Signed in through the real pages: the student with the password, the staff user with the password and then the authenticator app's code, computed from the secret of its TOTP device. Both accounts, and the others made for the pages (a minor, a teacher, sales, editor, support, a reviewer, two registrations), had emails that start with <code>atlas-</code> and were deleted afterwards.",
        "Seeded so that pages have something to show: shelves, collections, three pictures on a book, reviews (shown, waiting, rejected), an automatic offer, PIN codes of Assam, the revision course's first chapters with clips in every processing state, seven orders of the student in every status, six saved attempts, learning progress, book codes (one redeemed), a school's quotation request.",
    ]),
    ("How to read it", [
        "Each capture has a caption: the route, what state the page is in, the width, who is signed in and the page's title. The contents list every page once with the page of its desktop and its phone capture; the appendix says which rows of the parity document are pages and which are redirects, API calls or Django's.",
        "A full-page screenshot is taller than a page. A desktop capture is scaled to the page's width and goes on over the next pages (cut at a blank row); a phone capture runs down two columns. A page over fourteen screens (the solutions of a paper) is kept as its first nine screens and its last two, and says so.",
        "Not here: Razorpay's own window (it is not set up), the SMS log-in and the phone card of My account (SMS is off without a gateway), cash on delivery and the closed shop (settings), the passkey prompt (a browser dialog), the PDF files (invoices, quotations: the admin's lists link them).",
    ]),
]
body.append('<section class="sheet notes"><h2>About this atlas</h2>' + "".join(
    f"<h3>{esc(title)}</h3><ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>" for title, items in notes) + "</section>")
body.append(
    '<section class="sheet toc"><h2>Contents</h2><table><thead><tr><th>Route</th><th>State</th><th style="text-align:right">Desktop</th><th style="text-align:right">Phone</th></tr></thead><tbody>'
    + toc_rows() + "</tbody></table></section>"
)
body.extend(pages)
appendix = f"""<section class="sheet app"><h2 id="appendix">Appendix A: every row of the parity document</h2>
<p>The routes of the old Django site and where the Next.js frontend answers them (<code>docs/design/parity-nextjs.md</code>). <b>built</b>: a page, with the page of its capture; <b>redirected</b>: a redirect in <code>next.config.ts</code>; <b>API</b>: a form post of the Django page, now an API call; <b>Django</b>: still answered by Django behind Caddy; <b>not built</b>: with the reason in the parity document. Sections G to I share one table there.</p>
<table class="plain"><thead><tr><th>§</th><th>Django route</th><th>Next.js route</th><th>Status</th><th>In this atlas</th></tr></thead><tbody>{parity_table()}</tbody></table></section>
<section class="sheet app"><h2>Appendix B: the Django-only routes</h2>
<p>{inline(stays_text) if stays_text else ""} (<code>DJANGO_PREFIXES</code> in <code>src/lib/site.ts</code>.)</p>
{simple_table(["Django route", "Answered by", "Notes"], [[r[1], r[2] or "Django", r[4]] for r in django_only])}
<h3>Form posts of Django pages, now API calls</h3>
{simple_table(["Django route", "API", "Notes"], [[r[1], r[2] or "API", r[4]] for r in api_rows])}</section>
<section class="sheet app"><h2>Appendix C: the API and headless endpoints</h2>
<p>From <code>examleaf-web/API.md</code>, "Endpoints": paths are under <code>/api/v1/</code> except the last two rows. The website and the app use them; the website's own pages call them from the browser and from the server.</p>
{simple_table(["Method", "Path", "Who", "What"], api_endpoints)}</section>"""
if failure_rows:
    appendix += f'<section class="sheet app"><h2>Appendix D: not captured</h2><table class="plain"><thead><tr><th>URL</th><th>Scene</th><th>Why</th></tr></thead><tbody>{failure_rows}</tbody></table></section>'
body.append(appendix)

document = (
    f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ExamLeaf \u2014 every page, {esc(args.date)}</title>'
    f'<meta name="author" content="ExamLeaf"><meta name="description" content="Full-page captures of every page of the ExamLeaf website and admin">'
    f"<style>{css}</style></head><body>{''.join(body)}</body></html>"
)

# ---------------------------------------------------------------------------------------------------- render
(WORK / "atlas.html").write_text(document.replace("{PAGES}", "…"))
from weasyprint import HTML  # noqa: E402

print("rendering with WeasyPrint ...", flush=True)
rendered = HTML(string=document, base_url=str(WORK)).render()
pages_total = len(rendered.pages)
# the cover's count of pages is known only now: render again with it (layout does not depend on it)
document = document.replace("{PAGES}", str(pages_total))
rendered = HTML(string=document, base_url=str(WORK)).render()
OUT.parent.mkdir(parents=True, exist_ok=True)
rendered.write_pdf(str(OUT))
size = OUT.stat().st_size
print(f"{OUT}: {len(rendered.pages)} pages, {size / 1048576:.1f} MB, {len(captures)} captures", flush=True)
