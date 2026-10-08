// Places one (unpaid, Razorpay not configured) order for the temporary student through the checkout form, to have an order page.
import { launch, open, sleep, SP } from './lib.mjs';
const b = await launch();
const { ctx, page, errors } = await open(b, '/checkout/', { auth: true, width: 375, height: 812, dpr: 2 });
console.log(await page.$$eval('input,select,textarea', (els) => els.map((e) => `${e.tagName.toLowerCase()}#${e.id}[name=${e.name}][type=${e.type}] required=${e.required} autocomplete=${e.getAttribute('autocomplete')}`)));
const fill = async (sel, text) => { await page.click(sel); await page.keyboard.type(text, { delay: 20 }); };
await fill('#name', 'Review Temp');
await fill('#phone', '9864012345');
await fill('#line1', '1 Test Lane');
await fill('#pin', '781001');
await sleep(1500);
console.log('city/district after PIN:', await page.$eval('#city', (e) => e.value).catch(() => null), await page.$eval('#district', (e) => e.value).catch(() => null));
if (!(await page.$eval('#city', (e) => e.value))) await fill('#city', 'Guwahati');
if (!(await page.$eval('#district', (e) => e.value))) await fill('#district', 'Kamrup Metro');
await page.screenshot({ path: SP + '/shots/checkout-filled.png', fullPage: true });
const btn = (await page.$$('button')).find(Boolean);
for (const bt of await page.$$('button')) { const t = await bt.evaluate((e) => e.textContent.trim()); if (/Continue to payment/.test(t)) { await bt.click(); break; } }
await sleep(4000);
console.log('url', page.url());
await page.screenshot({ path: SP + '/shots/after-order.png', fullPage: true });
console.log(errors);
await b.close();
