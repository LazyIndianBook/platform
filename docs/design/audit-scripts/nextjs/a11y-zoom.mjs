// 200 % zoom proxy (640 px wide), 400 % (320 px): sideways scroll, content off the right edge, clipped text; and WCAG 1.4.12 text spacing.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const PAGES = [
  ['home', '/', 0], ['shop', '/shop/', 0], ['product', '/shop/physics-sample-papers-2027/', 0], ['book', '/books/physics-2027/', 0], ['login', '/account/login/', 0], ['signup', '/account/signup/', 0],
  ['privacy', '/privacy/', 0], ['revision', '/revision/', 0], ['paper-open', '/s/PHY-E01/', 0], ['notfound', '/no-such-page-xyz/', 0], ['contact', '/contact/', 0], ['schoolorders', '/shop/school-orders/', 0],
  ['cart', '/cart/', 1], ['checkout', '/checkout/', 1], ['pay', '/checkout/EL-2026-000003/pay/', 1], ['account', '/account/', 1], ['record', '/account/record/', 1], ['orders', '/account/orders/', 1],
  ['order', '/account/orders/EL-2026-000003/', 1], ['details', '/account/details/', 1], ['addresses', '/account/addresses/', 1], ['security', '/account/security/', 1], ['twofa', '/account/2fa/', 1], ['privacy-acct', '/account/privacy/', 1], ['paper-auth', '/s/PHY-E02/', 1],
];
const out = {};
const b = await launch();
const probe = () => {
  const sel = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/)[0] : '');
  const vw = document.documentElement.clientWidth;
  const o = { vw, scrollW: document.documentElement.scrollWidth, hscroll: document.documentElement.scrollWidth > vw + 1, offenders: [], clipped: [] };
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if ((r.width === 0 && r.height === 0) || cs.display === 'none' || (cs.position === 'fixed' && r.right <= vw) || e.closest('svg') || cs.visibility === 'hidden') continue;
    if (r.right > vw + 1 || r.left < -1) {
      let contained = false;
      for (let q = e.parentElement; q && q !== document.body; q = q.parentElement) { const qs = getComputedStyle(q); if (/(auto|scroll|hidden|clip)/.test(qs.overflowX)) { const qr = q.getBoundingClientRect(); if (qr.right <= vw + 1 && qr.left >= -1) { contained = true; break; } } }
      if (!contained && !e.closest('.sr-only,[data-sonner-toaster],.skip-link') && !e.matches('.sr-only') && o.offenders.length < 8) o.offenders.push(`${sel(e)} right=${Math.round(r.right)} left=${Math.round(r.left)}`);
    }
    if (/(hidden|clip)/.test(cs.overflowX + cs.overflowY) && (e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2) && e.textContent.trim().length > 0 && !e.matches('html,body,.sr-only,.skip-link,[data-sonner-toaster]') && cs.height !== '1px' && o.clipped.length < 8) o.clipped.push(`${sel(e)} sw=${e.scrollWidth}>${e.clientWidth} sh=${e.scrollHeight}>${e.clientHeight} "${e.textContent.trim().slice(0, 30)}"`);
  }
  return o;
};
for (const [id, url, auth] of PAGES) {
  for (const w of [640, 320]) {
    try {
      const { ctx, page } = await open(b, url, { auth: Boolean(auth), width: w, height: 900, dpr: 1 });
      await page.evaluate(() => document.fonts.ready); await sleep(500);
      const r = await page.evaluate(probe);
      out[`${id}@${w}`] = r;
      if (w === 320 && ['home', 'checkout', 'cart', 'product'].includes(id)) await page.screenshot({ path: `${SP}/shots/z320-${id}.png` });
      if (w === 640 && ['home', 'checkout', 'cart'].includes(id)) await page.screenshot({ path: `${SP}/shots/z640-${id}.png` });
      await ctx.close();
    } catch (e) { out[`${id}@${w}`] = { error: String(e).slice(0, 150) }; }
  }
  const a = out[`${id}@640`], c = out[`${id}@320`];
  console.log(id.padEnd(14), '640:', a.error || `${a.hscroll ? 'HSCROLL ' + a.scrollW : 'ok'} off=${a.offenders.length} clip=${a.clipped.length}`, '| 320:', c.error || `${c.hscroll ? 'HSCROLL ' + c.scrollW : 'ok'} off=${c.offenders.length} clip=${c.clipped.length}`);
}
// text spacing
const SPACING = 'html *{line-height:1.5 !important;letter-spacing:.12em !important;word-spacing:.16em !important} p{margin-bottom:2em !important}';
out.spacing = {};
for (const [id, url, auth] of PAGES.filter((p) => ['home', 'login', 'signup', 'product', 'cart', 'checkout', 'account', 'order'].includes(p[0]))) {
  const { ctx, page } = await open(b, url, { auth: Boolean(auth), width: 375, height: 812, dpr: 1 });
  await sleep(400);
  const before = await page.evaluate(probe);
  await page.addStyleTag({ content: SPACING }); await sleep(300);
  const after = await page.evaluate(probe);
  out.spacing[id] = { hscrollBefore: before.hscroll, hscrollAfter: after.hscroll, newClipped: after.clipped.filter((c) => !before.clipped.includes(c)), offenders: after.offenders.slice(0, 3) };
  console.log('spacing', id.padEnd(10), out.spacing[id].hscrollAfter ? 'HSCROLL' : 'ok', 'newClipped', out.spacing[id].newClipped.length, out.spacing[id].newClipped.slice(0, 2).join(' | '));
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-zoom.json', JSON.stringify(out, null, 1));
