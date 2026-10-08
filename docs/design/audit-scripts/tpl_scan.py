"""Static scan of templates/ against the vocabulary of docs/design/direction.md section 3 (see the matrix, 'Method')."""
import json, os, re, sys
ROOT = "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12/examleaf-web/templates"
SCR = os.path.dirname(os.path.abspath(__file__))
css = json.load(open(f"{SCR}/css-classes.json"))
NEW, LEGACY = set(css["new"]), set(css["legacy"])
VOCAB = set("""btn btn-primary btn-secondary btn-ghost btn-destructive btn-accent btn-sm btn-lg btn-block field field-help field-error input select textarea checkbox radio switch otp card card-header card-body card-footer card-interactive badge badge-easy badge-medium badge-hard badge-gold badge-muted alert alert-info alert-success alert-warning alert-error toast dialog tabs accordion skeleton table-wrap table breadcrumb pagination stepper step step-done step-current tile tile-physics tile-chemistry tile-maths tile-biology band band-night stage stage-cover marker price price-now price-mrp price-save empty timeline timeline-item qr-card nav nav-toggle nav-menu footer""".split())
LAYOUT = {"section", "container", "prose", "lead", "narrow", "row", "stack", "grid", "two-col", "main-col", "form-col", "form-grid"}

def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()

def strip(src):
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
    src = re.sub(r"\{% comment %\}.*?\{% endcomment %\}", "", src, flags=re.S)
    return src

def class_tokens(src):
    toks = set()
    for m in re.finditer(r'class="([^"]*)"', strip(src)):
        v = re.sub(r"\{\{.*?\}\}", " ", m.group(1))
        v = re.sub(r"\{%.*?%\}", " ", v)
        toks.update(t for t in v.split() if re.fullmatch(r"[A-Za-z_][\w-]*", t))
    # classes the templates build with {% render_field ... class="x" %}, |attr, add_class
    for m in re.finditer(r'class="([\w\- ]+)"', re.sub(r"<[^>]*>", "", strip(src))):
        toks.update(m.group(1).split())
    return toks

def refs(src):
    src = strip(src)
    inc = re.findall(r'\{%\s*include\s+"([^"]+)"', src)
    ext = re.findall(r'\{%\s*extends\s+"([^"]+)"', src)
    return inc, ext

def bare(src):
    """Controls without the vocabulary: <button> without btn, raw {{ form }} / form.as_*"""
    s = strip(src)
    buttons = re.findall(r"<button\b[^>]*>", s)
    bare_btn = [b for b in buttons if "btn" not in b and "link-button" not in b and "nav-link" not in b]
    raw_form = len(re.findall(r"\{\{\s*form\s*\}\}|form\.as_(?:p|div|ul|table)", s))
    return len(bare_btn), raw_form

rows = {}
files = []
for dp, _, fns in os.walk(ROOT):
    for fn in fns:
        rel = os.path.relpath(os.path.join(dp, fn), ROOT)
        files.append(rel)
files.sort()
own = {}
for rel in files:
    if rel.endswith((".txt", ".js")):
        continue
    src = read(rel)
    inc, ext = refs(src)
    own[rel] = {"tokens": class_tokens(src), "inc": inc, "ext": ext, "bare": bare(src), "lines": src.count("\n") + 1,
                "self_contained": "<html" in src}

def closure(rel, seen=None, chain="inc"):
    seen = seen or set()
    if rel in seen or rel not in own:
        return set()
    seen.add(rel)
    t = set(own[rel]["tokens"])
    for i in own[rel]["inc"]:
        t |= closure(i, seen)
    return t

def parents(rel):
    out, cur = [], rel
    while cur in own and own[cur]["ext"]:
        cur = own[cur]["ext"][0]
        out.append(cur)
    return out

res = {}
for rel, d in own.items():
    toks = closure(rel)
    vocab = sorted(toks & VOCAB)
    legacy = sorted(toks & LEGACY)
    unknown = sorted(t for t in toks if t not in NEW and t not in VOCAB and t not in LEGACY)
    res[rel] = {"lines": d["lines"], "vocab": vocab, "legacy": legacy, "unknown": unknown,
                "bare_buttons": d["bare"][0], "raw_form": d["bare"][1], "extends": parents(rel),
                "includes": d["inc"], "layout": sorted(toks & LAYOUT)}
json.dump(res, open(f"{SCR}/tpl-scan.json", "w"), indent=1)
for rel, r in res.items():
    print(f"{rel:48} v={len(r['vocab']):2} L={len(r['legacy'])} u={len(r['unknown'])} bare={r['bare_buttons']} raw={r['raw_form']} ext={r['extends'][:1]}")
