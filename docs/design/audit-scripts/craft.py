"""Measured facts about each page as laid out (headless Chrome): type, spacing, repeated card shapes, small targets."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Chrome, viewport, load

SCR = os.path.dirname(os.path.abspath(__file__))
PAGES = [("home", "/"), ("book", "/books/physics-2027/"), ("shop", "/shop/"), ("product", "/shop/physics-sample-papers-2027/"), ("cart (empty)", "/cart/"),
         ("login", "/account/login/"), ("signup", "/account/signup/"), ("solutions (logged out)", "/s/PHY-E01/"), ("404", "/this-page-does-not-exist/"),
         ("privacy", "/privacy/"), ("order lookup", "/orders/lookup/"), ("school orders", "/shop/school-orders/")]
SERVERS = {"before": "http://[::1]:8070", "after": "http://[::1]:8060"}
JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const first = (sel) => Array.from(document.querySelectorAll(sel)).find(vis);
  const h1 = first('main h1') || first('h1');
  const header = first('header');
  const out = {};
  const bs = getComputedStyle(document.body);
  out.bodyFont = bs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
  out.bodySize = bs.fontSize + '/' + bs.lineHeight;
  if (h1) {
    const hs = getComputedStyle(h1), hr = h1.getBoundingClientRect();
    out.h1 = h1.textContent.trim().slice(0, 50);
    out.h1Font = hs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + hs.fontSize + ' w' + hs.fontWeight;
    out.headerToH1 = header ? Math.round(hr.top - header.getBoundingClientRect().bottom) : null;
    let next = h1.nextElementSibling; while (next && !vis(next)) next = next.nextElementSibling;
    out.h1ToNext = next ? Math.round(next.getBoundingClientRect().top - hr.bottom) : null;
  }
  const sizes = new Set(); document.querySelectorAll('main *').forEach((e) => { if (vis(e) && e.childNodes.length && Array.from(e.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) sizes.add(getComputedStyle(e).fontSize); });
  out.distinctFontSizes = sizes.size;
  const cards = Array.from(document.querySelectorAll('.card')).filter(vis);
  out.cards = cards.length;
  out.cardShapes = new Set(cards.map((c) => { const r = c.getBoundingClientRect(); return Math.round(r.width / 10) * 10 + 'x' + Math.round(r.height / 20) * 20; })).size;
  const imgs = Array.from(document.querySelectorAll('main img')).filter(vis);
  out.images = imgs.length; out.imagesEmptyAlt = imgs.filter((i) => i.getAttribute('alt') === '').length;
  out.h2 = Array.from(document.querySelectorAll('main h2')).filter(vis).length;
  const small = Array.from(document.querySelectorAll('a, button, summary, input:not([type=hidden]), select, textarea, label.checkbox')).filter(vis).filter((e) => {
    if (e.closest('p, li, dd, .prose, .field-help, .footer-col') && e.tagName === 'A' && getComputedStyle(e).display === 'inline') return false;
    const r = e.getBoundingClientRect(); return r.height < 43.5 || r.width < 43.5; });
  out.smallTargets = small.length;
  out.smallTargetSamples = small.slice(0, 5).map((e) => (e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '') + ' "' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 18) + '" ' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height)));
  out.overflowX = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  const ft = document.querySelector('footer'); const mn = document.querySelector('main');
  out.footerHeight = ft ? Math.round(ft.getBoundingClientRect().height) : null; out.mainHeight = mn ? Math.round(mn.getBoundingClientRect().height) : null;
  const bar = document.querySelector('.bento-big .tier-bar'); if (bar && bar.previousElementSibling) out.bentoGap = Math.round(bar.getBoundingClientRect().top - bar.previousElementSibling.getBoundingClientRect().bottom);
  out.words = (document.querySelector('main') || document.body).innerText.split(/\s+/).filter(Boolean).length;
  out.docHeight = document.documentElement.scrollHeight;
  out.ctaFirstFold = Array.from(document.querySelectorAll('.btn-primary, .btn-accent, .btn-lg')).filter(vis).filter((e) => e.getBoundingClientRect().top < innerHeight && !e.closest('header')).length;
  return out;
})()
"""
chrome = Chrome(os.path.join(SCR, "chrome-profile-craft"), port=9335)
rows = []
try:
    for variant in sys.argv[1].split(","):
        for name, path in PAGES:
            for w, h, dpr, mobile in [(375, 812, 2, True), (1280, 900, 1, False)]:
                tab = chrome.new_tab()
                try:
                    viewport(tab, w, h, dpr, mobile)
                    load(tab, SERVERS[variant] + path, settle=1.2)
                    info = tab.js(JS)
                    rows.append({"variant": variant, "page": name, "width": w, **info})
                finally:
                    tab.close()
finally:
    chrome.quit()
json.dump(rows, open(os.path.join(SCR, "craft-%s.json" % sys.argv[1].replace(",", "-")), "w"), indent=1)
for r in rows:
    print(r["variant"], r["page"][:22].ljust(22), r["width"], "|", r.get("bodyFont"), r.get("bodySize"), "| h1", r.get("h1Font"), "| hdr→h1", r.get("headerToH1"), "h1→next", r.get("h1ToNext"), "| cards", r["cards"], "shapes", r["cardShapes"], "| sizes", r["distinctFontSizes"], "| small", r["smallTargets"], "| overflow", r["overflowX"], "| h", r["docHeight"])
