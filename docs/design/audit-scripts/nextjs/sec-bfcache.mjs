// After Log out, does Back show the signed-in page from the back/forward cache?
import { launch, open, sleep, BASE } from './lib.mjs';
const b = await launch();
const { ctx, page } = await open(b, '/shop/', { auth: true, width: 1280, height: 800, dpr: 1 });
await sleep(1500);
await page.evaluate(() => { window.__marker = 'page-before-logout'; });
const header = () => page.evaluate(() => ({ marker: window.__marker || null, headerText: document.querySelector('header').innerText.replace(/\s+/g, ' ').trim(), url: location.pathname }));
console.log('signed in /shop/:', JSON.stringify(await header()));
await page.evaluate(() => [...document.querySelectorAll('header button, header a')].find((e) => /Log out/.test(e.textContent))?.click());
await sleep(2500);
console.log('after Log out   :', JSON.stringify(await header()));
await page.goBack({ waitUntil: 'load' }).catch(() => {}); await sleep(1500);
const nav = await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type);
console.log('after Back      :', JSON.stringify(await header()), 'nav type:', nav);
await page.evaluate(() => { window.__probe = 1; });
// a personal page after logout: Back to /account/ from the home page
await b.close();
