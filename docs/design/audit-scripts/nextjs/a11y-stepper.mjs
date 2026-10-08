// The cart's copies stepper with the keyboard: does focus stay on the button after a step is sent?
import { launch, open, sleep, SP } from './lib.mjs';
const b = await launch();
const { ctx, page } = await open(b, '/cart/', { auth: true, width: 375, height: 812, dpr: 2 });
const desc = () => page.evaluate(() => { const a = document.activeElement; return `${a.tagName.toLowerCase()}${a.id ? '#' + a.id : ''} "${(a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 40)}" disabled=${a.disabled}`; });
await page.evaluate(() => { document.activeElement.blur(); });
// Tab to "One copy more"
for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); await sleep(40); if (/One copy more/.test(await desc())) break; }
console.log('focused:', await desc());
// watch focus and disabled state through the request
await page.evaluate(() => { window.__log = []; const f = () => window.__log.push(`${Math.round(performance.now())} active=${document.activeElement.tagName.toLowerCase()}${document.activeElement.getAttribute('aria-label') ? ':' + document.activeElement.getAttribute('aria-label').slice(0, 20) : ''}`); document.addEventListener('focusin', f); document.addEventListener('focusout', f); });
const before = await page.$eval('input[type=number]', (e) => e.value);
await page.keyboard.press('Enter');
await sleep(1500);
console.log('copies', before, '->', await page.$eval('input[type=number]', (e) => e.value));
console.log('focus after the step:', await desc());
console.log('focus events:', await page.evaluate(() => window.__log));
// again with Space; then step back down with the keyboard (Shift+Tab to "fewer")
await page.keyboard.press('Space'); await sleep(1200);
console.log('after Space:', await desc(), 'copies', await page.$eval('input[type=number]', (e) => e.value));
// restore: use the mouse to step down twice
await page.evaluate(() => { document.activeElement.blur?.(); });
for (let k = 0; k < 2; k++) { const btn = await page.evaluateHandle(() => [...document.querySelectorAll('button')].find((x) => /One copy fewer/.test(x.getAttribute('aria-label') || ''))); await btn.asElement().click(); await sleep(1000); }
console.log('restored copies', await page.$eval('input[type=number]', (e) => e.value));
await ctx.close(); await b.close();
