import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
import { focusInfo } from './inpage.mjs';
const out = {};
const b = await launch();
{
  const { ctx, page } = await open(b, '/account/details/', { auth: true });
  await sleep(500);
  out.sectionBeforeAnyToast = await page.evaluate(() => { const s = document.querySelector('section[aria-live]'); return s ? { tag: s.tagName, ariaLabel: s.getAttribute('aria-label'), ariaLive: s.getAttribute('aria-live'), parent: s.parentElement.tagName.toLowerCase(), indexInBody: [...document.body.children].indexOf(s.closest('body > *') || s), bodyChildren: [...document.body.children].map((e) => e.tagName.toLowerCase()).join(',') } : null; });
  const btn = await page.evaluateHandle(() => [...document.querySelectorAll('main button')].find((e) => /Save my details/.test(e.textContent)));
  await btn.asElement().click(); await sleep(1500);
  await page.mouse.click(5, 300); await sleep(100); // reset the focus navigation starting point to the top of the page
  await page.evaluate(() => { document.activeElement.blur(); scrollTo(0, 0); });
  const order = []; let covered = [];
  for (let i = 0; i < 70; i++) {
    await page.keyboard.press('Tab'); await sleep(45);
    let f = await page.evaluate(focusInfo);
    for (let k = 0; k < 6 && !f.none; k++) { await sleep(45); const g = await page.evaluate(focusInfo); const same = g.sel === f.sel && g.rect.y === f.rect.y && g.scrollY === f.scrollY; f = g; if (same) break; }
    if (f.none) break;
    order.push(`${f.sel.slice(0, 30)} "${f.text.slice(0, 22)}" y=${f.rect.y + f.scrollY} vy=${f.rect.y} cover=${f.fullyCovered ? 'FULL' : f.partlyCovered ? 'part' : '-'} off=${f.partlyOffscreen}`);
    if (f.fullyCovered || f.partlyCovered) covered.push(`${f.sel} "${f.text}" by ${f.coveredBy.join(',')}`);
  }
  out.tabStopsWithToast = order.length; out.firstFive = order.slice(0, 5); out.lastFive = order.slice(-5); out.covered = covered;
  out.toastPositionWhileWalking = await page.evaluate(() => { const t = document.querySelector('[data-sonner-toast]'); if (!t) return null; const r = t.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight, scrollPaddingBottom: getComputedStyle(document.documentElement).scrollPaddingBottom }; });
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/a11y-toast2.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
