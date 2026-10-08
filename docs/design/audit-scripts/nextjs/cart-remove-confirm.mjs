import { launch, open, sleep } from './lib.mjs';
const b = await launch();
const { ctx, page } = await open(b, '/cart/', { auth: true, width: 375, height: 812, dpr: 2 }); await sleep(600);
const act = () => page.evaluate(() => `${document.activeElement.tagName.toLowerCase()} "${(document.activeElement.getAttribute('aria-label') || document.activeElement.textContent || '').trim().slice(0, 30)}"`);
// keyboard: Tab to Remove, Enter, Tab to the destructive Remove, Enter
await page.evaluate(() => { document.activeElement.blur(); });
for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); if (/^button "Remove"/.test(await act())) break; }
await page.keyboard.press('Enter'); await sleep(400);
console.log('dialog open, focus on:', await act());
await page.keyboard.press('Tab'); console.log('Tab ->', await act());
await page.keyboard.press('Enter'); await sleep(2500);
console.log('after the confirmed Remove, focus on:', await act(), '| cart text:', await page.evaluate(() => document.querySelector('main').innerText.replace(/\s+/g, ' ').slice(0, 80)));
console.log('toast:', await page.evaluate(() => [...document.querySelectorAll('[data-sonner-toast]')].map((t) => t.textContent.trim().slice(0, 60))));
await b.close();
