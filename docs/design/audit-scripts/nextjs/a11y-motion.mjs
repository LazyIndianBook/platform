// prefers-reduced-motion: what runs with and without the preference (idle, on hover/focus, and across a soft navigation).
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const PAGES = [['home', '/', 0], ['shop', '/shop/', 0], ['product', '/shop/physics-sample-papers-2027/', 0], ['login', '/account/login/', 0], ['cart', '/cart/', 1], ['checkout', '/checkout/', 1], ['account', '/account/', 1], ['paper-open', '/s/PHY-E01/', 0], ['notfound', '/no-such-page-xyz/', 0]];
const out = {};
const b = await launch();
const probe = (page) => page.evaluate(() => {
  const sel = (e) => !e ? '?' : (e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/)[0] : ''));
  const anims = document.getAnimations().map((a) => `${a.animationName || a.transitionProperty || 'anim'}${a.effect && a.effect.pseudoElement ? ' ' + a.effect.pseudoElement : ''} on ${a.effect && a.effect.target ? sel(a.effect.target) : '?'} (${a.constructor.name}, ${a.playState})`);
  const styled = new Set();
  for (const e of document.querySelectorAll('body *')) { const cs = getComputedStyle(e); const an = cs.animationName !== 'none' && parseFloat(cs.animationDuration) > 0; const tr = cs.transitionProperty !== 'none' && cs.transitionDuration.split(',').some((d) => parseFloat(d) > 0); if (an || tr) styled.add(`${sel(e)}${an ? ' [animation ' + cs.animationName + ']' : ''}${tr ? ' [transition ' + cs.transitionProperty.split(',').slice(0, 2).join('/') + ']' : ''}`); }
  return { matchReduce: matchMedia('(prefers-reduced-motion: reduce)').matches, running: anims.slice(0, 8), runningCount: anims.length, styledCount: styled.size, styled: [...styled].slice(0, 8), scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior, hasViewTransitionCss: [...document.styleSheets].some((s) => { try { return [...s.cssRules].some((r) => /view-transition/.test(r.cssText) || (r.cssRules && [...r.cssRules].some((q) => /view-transition/.test(q.cssText)))); } catch { return false; } }) };
});
for (const [id, url, auth] of PAGES) {
  out[id] = {};
  for (const reduce of [false, true]) {
    const { ctx, page } = await open(b, url, { auth: Boolean(auth), reduce });
    await sleep(500);
    const idle = await probe(page);
    const hover = [];
    for (const s of ['.stage-cover', '.tile', 'a[data-slot=card]', 'button, .btn, a[class*="rounded-btn"]']) { const h = await page.$(s); if (!h) continue; try { await h.hover(); await sleep(60); hover.push(`${s.slice(0, 22)}: ${await page.evaluate(() => document.getAnimations().length)} animations while hovered`); } catch {} }
    out[id][reduce ? 'reduce' : 'no-preference'] = { idle, hover };
    await ctx.close();
  }
  const a = out[id]['no-preference'].idle, r = out[id].reduce.idle;
  console.log(id.padEnd(11), 'no-pref: running', a.runningCount, 'styled', a.styledCount, '| reduce: running', r.runningCount, 'styled', r.styledCount, r.styled.slice(0, 2).join(' ; '));
}
// soft navigation with a morph: home tile -> book page; and product card -> product page; count view-transition animations
for (const reduce of [false, true]) {
  const { ctx, page } = await open(b, '/', { reduce });
  await sleep(600);
  await page.evaluate(() => { window.__vt = { calls: 0, anims: [] }; const orig = document.startViewTransition?.bind(document); if (orig) document.startViewTransition = (...a) => { window.__vt.calls++; const t = orig(...a); t.ready.then(() => { window.__vt.anims.push(...document.getAnimations().map((x) => (x.effect && x.effect.pseudoElement) || x.animationName || 'anim').slice(0, 6)); }).catch(() => {}); return t; }; });
  await page.evaluate(() => document.querySelector('a.tile, a.stage-cover').click());
  await sleep(1500);
  out['softnav-' + (reduce ? 'reduce' : 'no-preference')] = { url: page.url().replace('http://localhost:3003', ''), vt: await page.evaluate(() => window.__vt), supportsVT: await page.evaluate(() => typeof document.startViewTransition) };
  await ctx.close();
}
// Menu drawer and Escape, spinner: busy button under reduce
{
  const { ctx, page } = await open(b, '/account/login/', { reduce: true });
  await sleep(300);
  await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((e) => /Text me a code/.test(e.textContent)); b.setAttribute('aria-busy', 'true'); });
  out.busySpinnerReduce = await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((e) => /Text me a code/.test(e.textContent)); const cs = getComputedStyle(b, '::before'); return { animationName: cs.animationName, animationDuration: cs.animationDuration }; });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-motion.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify({ softNavNo: out['softnav-no-preference'], softNavReduce: out['softnav-reduce'], spinner: out.busySpinnerReduce }));
