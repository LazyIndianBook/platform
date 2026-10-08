import { launch, open, sleep, SP } from './lib.mjs';
const browser = await launch();
const { ctx, page, errors } = await open(browser, '/shop/physics-sample-papers-2027/', { auth: true });
await page.screenshot({ path: SP + '/shots/product-auth.png' });
const btn = await page.$$eval('button', (bs) => bs.map((b) => b.textContent.trim()));
console.log(btn);
for (const b of await page.$$('button')) { const t = await b.evaluate((e) => e.textContent.trim()); if (/^Add to cart/i.test(t)) { await b.click(); console.log('clicked', t); break; } }
await sleep(2500);
await page.screenshot({ path: SP + '/shots/product-added.png' });
console.log(await page.evaluate(() => [...document.querySelectorAll('[role=status],[aria-live],li[data-sonner-toast]')].map((e) => e.textContent.trim().slice(0, 100))));
console.log(errors);
await ctx.close();
await browser.close();
