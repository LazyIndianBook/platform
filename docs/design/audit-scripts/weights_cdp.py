"""Page weights as headless Chrome fetches them: cold cache, load + 1.5 s, then scrolled to the bottom (lazy images)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Chrome, viewport, load, network_summary

SCR = os.path.dirname(os.path.abspath(__file__))
PAGES = [("/", "home"), ("/shop/", "shop"), ("/shop/physics-sample-papers-2027/", "product"), ("/s/PHY-E01/", "solutions (logged out)"), ("/account/login/", "login")]
VIEWS = [("desktop 1280x900@1", 1280, 900, 1, False), ("phone 375x812@2", 375, 812, 2, True)]
SERVERS = {"before": "http://[::1]:8070", "after": "http://[::1]:8060"}


def kind(r):
    t = (r["type"] or "").lower()
    return {"document": "html", "stylesheet": "css", "script": "js", "font": "font", "image": "image", "manifest": "other"}.get(t, "other")


def summarise(reqs):
    out = {k: {"n": 0, "bytes": 0} for k in ("html", "css", "js", "font", "image", "other")}
    for r in reqs:
        if r["status"] is None or r["url"].startswith("data:"):
            continue
        k = kind(r)
        out[k]["n"] += 1
        out[k]["bytes"] += r["body"]
    out["total"] = {"n": sum(v["n"] for v in out.values()), "bytes": sum(v["bytes"] for v in out.values())}
    return out


chrome = Chrome(os.path.join(SCR, "chrome-profile-weights"), port=9334)
rows = []
try:
    for variant in sys.argv[1].split(","):
        for path, name in PAGES:
            for vname, w, h, dpr, mobile in VIEWS:
                tab = chrome.new_tab()
                try:
                    viewport(tab, w, h, dpr, mobile)
                    load(tab, SERVERS[variant] + path, settle=1.5)
                    first = summarise(network_summary(tab))
                    height = tab.js("document.documentElement.scrollHeight")
                    y = 0
                    while y < height:
                        y += h // 2
                        tab.js(f"window.scrollTo(0, {y}); 1")
                        tab.pump(0.25)
                        height = tab.js("document.documentElement.scrollHeight")
                    tab.pump(1.0)
                    scrolled = summarise(network_summary(tab))
                    files = sorted({(r["url"].rsplit("/", 1)[-1][:60], kind(r), r["body"]) for r in network_summary(tab) if r["status"] and kind(r) in ("font", "image")}, key=lambda x: (x[1], x[0]))
                    rows.append({"variant": variant, "page": name, "path": path, "view": vname, "initial": first, "scrolled": scrolled, "assets": files})
                    print(variant, name, vname, "initial", first["total"], "scrolled", scrolled["total"], flush=True)
                finally:
                    tab.close()
finally:
    chrome.quit()
json.dump(rows, open(os.path.join(SCR, "weights-cdp-%s.json" % sys.argv[1].replace(",", "-")), "w"), indent=1)
