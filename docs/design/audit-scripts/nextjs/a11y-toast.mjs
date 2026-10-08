// Toasts (sonner): is the live region there before the message, does the "added to cart" toast survive the navigation,
// what are its roles, can the keyboard reach and dismiss it, does it cover focused elements on a phone.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
import { focusInfo } from './inpage.mjs';
const out = {};
const b = await launch();
const live = (page) => page.evaluate(() => {
  const t = document.querySelector('[data-sonner-toaster]'); if (!t) return null;
  const sec = t.closest('section') || t.parentElement;
  const toasts = [...document.querySelectorAll('[data-sonner-toast]')].map((e) => ({ role: e.getAttribute('role'), ariaLive: e.getAttribute('aria-live'), ariaAtomic: e.getAttribute('aria-atomic'), tabindex: e.getAttribute('tabindex'), text: e.textContent.trim().slice(0, 80), mounted: e.getAttribute('data-mounted'), removed: e.getAttribute('data-removed'), buttons: [...e.querySelectorAll('button')].map((x) => `${x.getAttribute('aria-label') || x.textContent.trim()} ${Math.round(x.getBoundingClientRect().width)}x${Math.round(x.getBoundingClientRect().height)}`) }));
  return { section: { tag: sec.tagName.toLowerCase(), ariaLabel: sec.getAttribute('aria-label'), ariaLive: sec.getAttribute('aria-live'), ariaRelevant: sec.getAttribute('aria-relevant'), ariaAtomic: sec.getAttribute('aria-atomic'), tabindex: sec.getAttribute('tabindex') }, list: { tag: t.tagName.toLowerCase(), position: t.getAttribute('data-y-position') + '/' + t.getAttribute('data-x-position') }, toasts };
});
// A. add to cart (signed in): watch the toast through the navigation
{
  const { ctx, page } = await open(b, '/shop/physics-sample-papers-2027/', { auth: true });
  await sleep(500);
  out.liveBefore = await live(page);
  await page.evaluate(() => {
    window.__ev = []; const t0 = performance.now();
    new MutationObserver((muts) => { for (const m of muts) { for (const n of m.addedNodes) if (n.nodeType === 1 && (n.matches?.('[data-sonner-toast]') || n.querySelector?.('[data-sonner-toast]'))) window.__ev.push(`${Math.round(performance.now() - t0)}ms toast added (${location.pathname})`); for (const n of m.removedNodes) if (n.nodeType === 1 && (n.matches?.('[data-sonner-toast]') || n.querySelector?.('[data-sonner-toast]'))) window.__ev.push(`${Math.round(performance.now() - t0)}ms toast removed (${location.pathname})`); } }).observe(document.body, { childList: true, subtree: true });
    new MutationObserver(() => { const n = document.querySelectorAll('[data-sonner-toast]').length; const last = window.__ev[window.__ev.length - 1] || ''; const s = `count=${n} path=${location.pathname}`; if (!last.endsWith(s)) window.__ev.push(`${Math.round(performance.now() - t0)}ms ${s}`); }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-removed', 'data-mounted'] });
  });
  const btn = await page.evaluateHandle(() => [...document.querySelectorAll('button')].find((e) => /^Add to cart/.test(e.textContent.trim())));
  await btn.asElement().click();
  for (const ms of [150, 300, 600, 1200, 2500]) { await sleep(ms === 150 ? 150 : ms - 0); }
  out.eventsAddToCart = await page.evaluate(() => window.__ev);
  out.afterAddUrl = page.url().replace('http://localhost:3003', '');
  out.liveAfterAdd = await live(page);
  await page.screenshot({ path: SP + '/shots/toast-after-add.png' });
  await ctx.close();
}
// B. a toast that stays: Save my details (signed in), then a Tab walk with the toast showing
{
  const { ctx, page } = await open(b, '/account/details/', { auth: true });
  const client = await page.createCDPSession(); await client.send('Accessibility.enable');
  await sleep(500);
  const btn = await page.evaluateHandle(() => [...document.querySelectorAll('main button')].find((e) => /Save my details/.test(e.textContent)));
  await btn.asElement().click(); await sleep(1500);
  out.liveAfterSave = await live(page);
  out.focusAfterSave = await page.evaluate(() => `${document.activeElement.tagName.toLowerCase()}#${document.activeElement.id}`);
  await page.screenshot({ path: SP + '/shots/toast-details.png' });
  // keyboard: Alt+T (sonner's hotkey) then Tab to the close button, Enter
  await page.keyboard.down('Alt'); await page.keyboard.press('KeyT'); await page.keyboard.up('Alt'); await sleep(200);
  out.afterAltT = await page.evaluate(() => `${document.activeElement.tagName.toLowerCase()}[${document.activeElement.getAttribute('aria-label') || ''}] ${document.activeElement.textContent.trim().slice(0, 30)}`);
  // where does Tab from the page top reach the toast (DOM order)?
  await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
  const order = [];
  for (let i = 0; i < 60; i++) { await page.keyboard.press('Tab'); await sleep(40); const f = await page.evaluate(focusInfo); if (f.none) break; order.push(`${f.sel} "${f.text.slice(0, 22)}" y=${f.rect.y + f.scrollY} cover=${f.fullyCovered ? 'FULL' : f.partlyCovered ? 'part' : '-'}`); }
  out.tabOrderWithToast = order;
  out.coveredStops = order.filter((o) => /cover=(FULL|part)/.test(o));
  const closeBtn = await page.$('[data-sonner-toast] button[aria-label=Dismiss], [data-sonner-toast] [data-close-button]');
  if (closeBtn) { await closeBtn.focus(); out.closeButtonRing = await page.evaluate(focusInfo).then((f) => ({ indicator: f.indicator, outline: f.outline, contrast: f.ringContrast, rect: f.rect })); await page.keyboard.press('Enter'); await sleep(600); out.afterDismiss = await live(page); out.focusAfterDismiss = await page.evaluate(() => `${document.activeElement.tagName.toLowerCase()}#${document.activeElement.id}`); }
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-toast.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
