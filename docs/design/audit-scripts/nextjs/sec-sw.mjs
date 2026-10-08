// Service worker and browser storage after a signed-in session: what is kept, and does anything personal end up there?
import fs from 'node:fs';
import { launch, sleep, SP, BASE, cookies } from './lib.mjs';
const out = {};
const b = await launch();
const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 375, height: 812 });
for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
await sleep(2500);
out.registration = await page.evaluate(async () => { const r = await navigator.serviceWorker.getRegistration(); return r ? { scope: r.scope, active: r.active && r.active.state, script: r.active && r.active.scriptURL.replace(location.origin, '') } : null; });
await page.reload({ waitUntil: 'networkidle0' }); await sleep(800);
out.controlled = await page.evaluate(() => Boolean(navigator.serviceWorker.controller));
for (const path of ['/shop/', '/account/', '/cart/', '/checkout/EL-2026-000003/pay/', '/s/PHY-E02/', '/s/PHY-E01/', '/revision/', '/account/orders/EL-2026-000003/', '/orders/lookup/', '/no-such-page-xyz/']) { await page.goto(BASE + path, { waitUntil: 'networkidle0' }); await sleep(400); }
out.caches = await page.evaluate(async () => { const r = {}; for (const k of await caches.keys()) { const c = await caches.open(k); r[k] = (await c.keys()).map((q) => new URL(q.url).pathname); } return r; });
out.cachedDocumentsOrPersonal = Object.values(out.caches).flat().filter((p) => !/^\/_next\/static\//.test(p) && !['/offline/', '/icon.svg', '/icon-192.png'].includes(p));
out.storage = await page.evaluate(async () => ({ localStorage: Object.keys(localStorage), sessionStorage: Object.keys(sessionStorage), indexedDB: (indexedDB.databases ? (await indexedDB.databases()).map((d) => d.name) : 'n/a'), documentCookie: document.cookie.split('; ').map((c) => c.split('=')[0]) }));
out.cookies = (await page.cookies()).map((c) => ({ name: c.name, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite, path: c.path, session: c.session }));
// offline behaviour: the shell page when the network is gone (a navigation), and nothing personal in it
await page.setOfflineMode(true);
const resp = await page.goto(BASE + '/account/', { waitUntil: 'domcontentloaded' }).catch((e) => String(e).slice(0, 80));
out.offlineAccount = typeof resp === 'string' ? resp : { status: resp.status(), title: await page.title(), text: (await page.evaluate(() => document.body.innerText)).replace(/\s+/g, ' ').slice(0, 160) };
await page.setOfflineMode(false);
await ctx.close(); await b.close();
fs.writeFileSync(SP + '/sec-sw.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
