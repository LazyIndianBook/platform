// Pixel-sampled text contrast (what axe cannot decide over gradients and images): hide all text, screenshot the page,
// then for every text node compare its computed colour with the pixels behind its line boxes. Worst case and median.
import fs from 'node:fs';
import sharp from 'sharp';
import { launch, open, sleep, SP } from './lib.mjs';
const PAGES = [['home', '/', 0, [375, 1280]], ['shop', '/shop/', 0, [375, 1280]], ['product', '/shop/physics-sample-papers-2027/', 0, [375, 1280]], ['book', '/books/physics-2027/', 0, [375]], ['login', '/account/login/', 0, [375]], ['signup', '/account/signup/', 0, [375]], ['revision', '/revision/', 0, [375]], ['notfound', '/no-such-page-xyz/', 0, [375]],
  ['cart', '/cart/', 1, [375]], ['checkout', '/checkout/', 1, [375]], ['pay', '/checkout/EL-2026-000003/pay/', 1, [375]], ['account', '/account/', 1, [375, 1280]], ['order', '/account/orders/EL-2026-000003/', 1, [375]], ['security', '/account/security/', 1, [375]]];
const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
const out = {};
const b = await launch();
for (const [id, url, auth, widths] of PAGES) for (const w of widths) {
  const { ctx, page } = await open(b, url, { auth: Boolean(auth), width: w, height: 900, dpr: 1 });
  await page.evaluate(() => document.fonts.ready); await sleep(800);
  const texts = await page.evaluate(() => {
    const res = []; const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (!t) continue;
      const p = n.parentElement; if (!p || p.closest('script,style,noscript,svg,[data-sonner-toaster]')) continue;
      const cs = getComputedStyle(p); if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      const rects = [...range.getClientRects()].filter((r) => r.width > 1 && r.height > 1).map((r) => [r.left + scrollX, r.top + scrollY, r.width, r.height]);
      if (!rects.length) continue;
      if (p.closest('.sr-only') || getComputedStyle(p).clip !== 'auto' && cs.position === 'absolute' && parseFloat(cs.width) <= 1) continue;
      let op = 1; for (let q = p; q; q = q.parentElement) op *= parseFloat(getComputedStyle(q).opacity);
      res.push({ text: t.slice(0, 40), color: cs.color, size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight), opacity: op, rects, tag: p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className ? '.' + p.className.trim().split(/\s+/)[0] : '') });
    }
    return res;
  });
  await page.addStyleTag({ content: '*,*::before,*::after{color:transparent !important;-webkit-text-fill-color:transparent !important;text-shadow:none !important;caret-color:transparent !important} input::placeholder,textarea::placeholder{color:transparent !important}' });
  await sleep(300);
  const png = await page.screenshot({ fullPage: true });
  const img = sharp(png); const meta = await img.metadata(); const raw = await img.removeAlpha().raw().toBuffer();
  const W = meta.width, H = meta.height;
  const fails = []; let checked = 0;
  for (const t of texts) {
    const m = t.color.match(/rgba?\(([^)]+)\)/); if (!m) continue; const parts = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); const fg = parts.slice(0, 3); const alpha = (parts.length > 3 ? parts[3] : 1) * t.opacity;
    const large = t.size >= 24 || (t.size >= 18.66 && t.weight >= 700); const need = large ? 3 : 4.5;
    let worst = Infinity; const samples = [];
    for (const [x, y, rw, rh] of t.rects) {
      const x0 = Math.max(0, Math.floor(x)), y0 = Math.max(0, Math.floor(y)), x1 = Math.min(W - 1, Math.ceil(x + rw)), y1 = Math.min(H - 1, Math.ceil(y + rh));
      const stepX = Math.max(1, Math.floor((x1 - x0) / 24)), stepY = Math.max(1, Math.floor((y1 - y0) / 8));
      for (let yy = y0; yy <= y1; yy += stepY) for (let xx = x0; xx <= x1; xx += stepX) { const i = (yy * W + xx) * 3; const bg = [raw[i], raw[i + 1], raw[i + 2]]; const eff = fg.map((c, k) => Math.round(c * alpha + bg[k] * (1 - alpha))); const r = ratio(eff, bg); samples.push(r); if (r < worst) worst = r; }
    }
    if (!samples.length) continue; checked++;
    samples.sort((a, c) => a - c); const median = samples[Math.floor(samples.length / 2)];
    if (worst < need) fails.push({ text: t.text, tag: t.tag, color: t.color, size: t.size, weight: t.weight, need, worst: Number(worst.toFixed(2)), median: Number(median.toFixed(2)) });
  }
  out[`${id}@${w}`] = { checked, fails: fails.sort((a, c) => a.worst - c.worst).slice(0, 12), failCount: fails.length };
  console.log(`${id}@${w}`.padEnd(14), 'text nodes', checked, 'below minimum (worst pixel):', fails.length, fails.slice(0, 3).map((f) => `"${f.text}" ${f.worst}:${f.need} (median ${f.median})`).join(' | '));
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/contrast.json', JSON.stringify(out, null, 1));
