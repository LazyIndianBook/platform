"""Page weights from curl-style fetches (urllib, no browser): the HTML, then every asset the HTML refers to, and the
fonts and images the stylesheet refers to. Raw bytes, plus gzip -9 (Caddy's encode gzip is what production sends)."""
import gzip, json, re, sys, urllib.parse, urllib.request
from html.parser import HTMLParser

BASE = sys.argv[1]
PAGES = [("/", "home"), ("/shop/", "shop"), ("/shop/physics-sample-papers-2027/", "product"), ("/s/PHY-E01/", "solutions (logged out)"), ("/account/login/", "login")]
cache = {}


def get(url):
    if url not in cache:
        req = urllib.request.Request(url, headers={"User-Agent": "weights/1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                cache[url] = (r.status, data, r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            cache[url] = (e.code, e.read(), e.headers.get("Content-Type", ""))
    return cache[url]


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.css, self.js, self.fonts, self.icons, self.imgs, self.other, self.pictures = [], [], [], [], [], [], []
        self.in_picture = False
        self.picture_srcs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link":
            rel = (a.get("rel") or "").lower()
            href = a.get("href")
            if not href:
                return
            if "stylesheet" in rel:
                self.css.append(href)
            elif "preload" in rel and a.get("as") == "font":
                self.fonts.append(href)
            elif "icon" in rel:
                self.icons.append(href)
            elif "manifest" in rel:
                self.other.append(href)
            elif "preload" in rel and a.get("as") == "image":
                self.imgs.append(("preload", href))
        elif tag == "script" and a.get("src"):
            self.js.append(a["src"])
        elif tag == "picture":
            self.in_picture, self.picture_srcs = True, []
        elif tag == "source" and self.in_picture:
            self.picture_srcs.append((a.get("type", ""), a.get("srcset", "")))
        elif tag == "img":
            if self.in_picture:
                self.pictures.append((self.picture_srcs, a.get("src", ""), a.get("srcset", "")))
            else:
                self.imgs.append(("img", a.get("src", ""), a.get("srcset", "")))

    def handle_endtag(self, tag):
        if tag == "picture":
            self.in_picture = False


def candidates(srcset):
    out = []
    for part in srcset.split(","):
        part = part.strip()
        if part:
            bits = part.split()
            out.append((bits[0], bits[1] if len(bits) > 1 else "1x"))
    return out


def size(url):
    status, data, _ = get(url)
    return (len(data), status)


def page(path):
    url = urllib.parse.urljoin(BASE, path)
    status, html, ctype = get(url)
    refs = Refs()
    refs.feed(html.decode("utf-8", "ignore"))
    absu = lambda h: urllib.parse.urljoin(url, h)
    out = {"path": path, "status": status, "html": len(html), "html_gz": len(gzip.compress(html, 9))}
    css_urls = [absu(h) for h in refs.css if urllib.parse.urlparse(absu(h)).netloc == urllib.parse.urlparse(BASE).netloc]
    ext_css = [h for h in refs.css if h not in [h2 for h2 in refs.css if absu(h2) in css_urls]]
    css_bytes = css_gz = 0
    font_decl, img_css = {}, {}
    for cu in css_urls:
        _, data, _ = get(cu)
        css_bytes += len(data)
        css_gz += len(gzip.compress(data, 9))
        text = data.decode("utf-8", "ignore")
        for block in re.findall(r"@font-face\s*\{[^}]*\}", text):
            m = re.search(r'url\(["\']?([^)"\']+)', block)
            if m and "local(" not in m.group(1):
                furl = urllib.parse.urljoin(cu, m.group(1))
                font_decl[furl] = "unicode-range" in block
        for m in re.finditer(r"url\(\s*[\"']?([^)\"']+)", re.sub(r"@font-face\s*\{[^}]*\}", "", text)):
            u = m.group(1)
            if not u.startswith("data:") and not u.startswith("#"):
                img_css[urllib.parse.urljoin(cu, u)] = 1
    js_urls = [absu(h) for h in refs.js]
    ext_js = [u for u in js_urls if urllib.parse.urlparse(u).netloc != urllib.parse.urlparse(BASE).netloc]
    js_urls = [u for u in js_urls if u not in ext_js]
    out["css"] = {"files": len(css_urls), "bytes": css_bytes, "gz": css_gz, "external": ext_css}
    out["js"] = {"files": len(js_urls), "bytes": sum(size(u)[0] for u in js_urls), "gz": sum(len(gzip.compress(get(u)[1], 9)) for u in js_urls), "external": ext_js}
    preloaded = [absu(h) for h in refs.fonts]
    out["fonts"] = {
        "declared_files": len(font_decl), "declared_bytes": sum(size(u)[0] for u in font_decl),
        "preloaded_files": len(preloaded), "preloaded_bytes": sum(size(u)[0] for u in preloaded),
        "latin_only_files": len([u for u, ur in font_decl.items() if not ur]), "latin_only_bytes": sum(size(u)[0] for u, ur in font_decl.items() if not ur),
        "list": sorted(u.rsplit("/", 1)[1] for u in font_decl),
    }
    icon_urls = [absu(h) for h in refs.icons]
    manifest = [absu(h) for h in refs.other]
    out["icons"] = {"files": len(icon_urls), "bytes_all": sum(size(u)[0] for u in icon_urls), "bytes_one": min([size(u)[0] for u in icon_urls] or [0])}
    # images: <img> alone: its src; <picture>: the avif source's candidates, the webp ones, and the fallback img
    img_rows = []
    for kind, *rest in refs.imgs:
        src, srcset = (rest[0], rest[1] if len(rest) > 1 else "")
        urls = [absu(c[0]) for c in candidates(srcset)] or ([absu(src)] if src else [])
        img_rows.append({"kind": "img", "urls": urls})
    for sources, src, srcset in refs.pictures:
        for stype, sset in sources:
            img_rows.append({"kind": stype or "source", "urls": [absu(c[0]) for c in candidates(sset)]})
        img_rows.append({"kind": "img fallback", "urls": [absu(c[0]) for c in candidates(srcset)] or ([absu(src)] if src else [])})
    seen_all = {}
    first_candidate = {}
    for row in img_rows:
        for u in row["urls"]:
            seen_all[u] = size(u)[0]
    # what a browser that reads AVIF fetches: per <picture>, its smallest AVIF candidate (a 2x phone: the largest); each
    # distinct file once, as the browser's cache has it
    pick_small, pick_large = {}, {}
    for sources, src, srcset in refs.pictures:
        avif = [c for t, ss in sources if "avif" in t for c in candidates(ss)]
        pool = [absu(c[0]) for c in (avif or candidates(srcset) or [(src, "")]) if c[0]]
        sizes = {u: size(u)[0] for u in pool}
        if sizes:
            pick_small[min(sizes, key=sizes.get)] = min(sizes.values())
            pick_large[max(sizes, key=sizes.get)] = max(sizes.values())
    for kind, *rest in refs.imgs:
        src, srcset = (rest[0], rest[1] if len(rest) > 1 else "")
        pool = [absu(c[0]) for c in (candidates(srcset) or [(src, "")]) if c[0]]
        sizes = {u: size(u)[0] for u in pool}
        if sizes:
            pick_small[min(sizes, key=sizes.get)] = min(sizes.values())
            pick_large[max(sizes, key=sizes.get)] = max(sizes.values())
    smallest, largest = sum(pick_small.values()), sum(pick_large.values())
    n_img_modern = len(pick_small)
    out["images"] = {
        "img_elements": len(refs.imgs) + len(refs.pictures), "pictures": len(refs.pictures),
        "distinct_files_referenced": len(seen_all), "bytes_all_candidates": sum(seen_all.values()),
        "bytes_modern_smallest": smallest, "bytes_modern_largest": largest,
        "css_background_urls": len(img_css), "css_background_bytes": sum(size(u)[0] for u in img_css),
        "png_in_markup": sorted({u.rsplit('/', 1)[1] for u in seen_all if u.lower().endswith('.png')}),
    }
    out["manifest"] = {"files": len(manifest), "bytes": sum(size(u)[0] for u in manifest)}
    # request count of the inventory: html + css + js + preloaded fonts (+ the fonts the stylesheet makes the browser take
    # when text uses them: approximated by preloaded) + 1 icon + manifest + images (one candidate each)
    out["requests_inventory"] = 1 + len(css_urls) + len(js_urls) + len(preloaded) + 1 + len(manifest) + n_img_modern
    out["external_hosts"] = sorted({urllib.parse.urlparse(u).netloc for u in ext_js + [absu(h) for h in ext_css]})
    return out


results = [page(p) | {"name": n} for p, n in PAGES]
json.dump(results, open(sys.argv[2], "w"), indent=1)
for r in results:
    print(r["name"], r["status"], "html", r["html"], "gz", r["html_gz"], "| css", r["css"]["bytes"], "gz", r["css"]["gz"], "| js", r["js"]["bytes"], "| fonts decl", r["fonts"]["declared_bytes"], "pre", r["fonts"]["preloaded_bytes"], "| imgs", r["images"]["bytes_modern_smallest"], "-", r["images"]["bytes_modern_largest"], "n", r["images"]["img_elements"], "| req≈", r["requests_inventory"], "| ext", r["external_hosts"])
