import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from cdp import Chrome, viewport, load, screenshot, network_summary, console_issues

SCR = os.path.dirname(os.path.abspath(__file__))
PAGES = [  # slug, path
    ("home", "/"),
    ("shop", "/shop/"),
    ("product-physics", "/shop/physics-sample-papers-2027/"),
    ("cart-empty", "/cart/"),
    ("login", "/account/login/"),
    ("signup", "/account/signup/"),
    ("solutions-logged-out", "/s/PHY-E01/"),
    ("404", "/this-page-does-not-exist/"),
]
VIEWS = [(375, 812, 2, True), (1280, 900, 1, False)]
SERVERS = {"before": "http://[::1]:8070", "after": "http://[::1]:8060"}


def run(out_root, variants, only=None, full_root=None):
    chrome = Chrome(os.path.join(SCR, "chrome-profile"))
    print("Chrome", chrome.version())
    report = []
    try:
        for variant in variants:
            os.makedirs(os.path.join(out_root, variant), exist_ok=True)
            if full_root:
                os.makedirs(os.path.join(full_root, variant), exist_ok=True)
            for slug, path in PAGES:
                if only and slug not in only:
                    continue
                for w, h, dpr, mobile in VIEWS:
                    tab = chrome.new_tab()
                    try:
                        viewport(tab, w, h, dpr, mobile)
                        ok = load(tab, SERVERS[variant] + path)
                        name = f"{slug}-{w}-{variant}.jpg"
                        size = screenshot(tab, os.path.join(out_root, variant, name), quality=80)
                        info = tab.js("({title: document.title, h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
                        row = {"variant": variant, "page": slug, "path": path, "view": f"{w}x{h}@{dpr}", "loaded": ok,
                               "file": name, "bytes": size, **info, "issues": console_issues(tab)}
                        report.append(row)
                        print(json.dumps({k: v for k, v in row.items() if k != "issues"}), len(row["issues"]), "console issues")
                    finally:
                        tab.close()
                    if full_root:  # the whole page, at 1x, for the analysis (not part of the deliverable set)
                        tab = chrome.new_tab()
                        try:
                            viewport(tab, w, h, 1, mobile)
                            load(tab, SERVERS[variant] + path)
                            screenshot(tab, os.path.join(full_root, variant, name), quality=65, full=True)
                        finally:
                            tab.close()
    finally:
        chrome.quit()
    return report


if __name__ == "__main__":
    out = sys.argv[1]
    variants = sys.argv[2].split(",")
    only = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else None
    full_root = sys.argv[4] if len(sys.argv) > 4 else None
    rep = run(out, variants, only, full_root)
    json.dump(rep, open(os.path.join(out, f"report-{'-'.join(variants)}.json"), "w"), indent=1)
