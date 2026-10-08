// Does the Razorpay window work after the checkout is reached by client-side navigation (the normal path), as after a hard load?
// Razorpay is stubbed (no request leaves the machine): the payment options come from a fake answer, checkout.js is a stub that
// does what the real one does on open() (a frame from api.razorpay.com, a beacon to lumberjack, an image from cdn.razorpay.com).
import fs from 'node:fs';
import { launch, open, sleep, SP, BASE, cookies } from './lib.mjs';
const out = {};
const STUB = `window.Razorpay = function (o) { this.o = o; };
Razorpay.prototype.on = function () {};
Razorpay.prototype.open = function () {
  window.__stubOpened = true;
  const f = document.createElement('iframe'); f.src = 'https://api.razorpay.com/v1/checkout/public?stub=1'; f.onload = () => { window.__frameLoaded = true; }; document.body.appendChild(f);
  fetch('https://lumberjack.razorpay.com/stub', { mode: 'no-cors' }).then(() => { window.__beaconSent = true; }).catch((e) => { window.__beaconError = String(e); });
  const i = new Image(); i.onload = () => { window.__imgLoaded = true; }; i.onerror = () => { window.__imgError = true; }; i.src = 'https://cdn.razorpay.com/stub.png';
};`;
const b = await launch();
async function scenario(label, startUrl, viaClick) {
  const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 1 });
  for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
  const allowedRazorpayRequests = []; const consoleMsgs = [];
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) consoleMsgs.push(`${m.type()}: ${m.text().slice(0, 220)}`); });
  await page.setRequestInterception(true);
  page.on('request', (r) => {
    const u = r.url();
    if (/\/api\/v1\/orders\/EL-2026-000003\/payment\/$/.test(u) && r.method() === 'POST') return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ key: 'rzp_test_stub', order_id: 'order_stub', amount: 33900, currency: 'INR', name: 'ExamLeaf', description: 'Order EL-2026-000003', prefill: {}, notes: {}, theme: {}, test_mode: true }) });
    if (/^https:\/\/checkout\.razorpay\.com\/v1\/checkout\.js/.test(u)) { allowedRazorpayRequests.push('script ' + u); return r.respond({ status: 200, contentType: 'application/javascript', body: STUB }); }
    if (/razorpay\.com/.test(u)) { allowedRazorpayRequests.push(`${r.resourceType()} ${u}`); return r.respond({ status: 200, contentType: r.resourceType() === 'image' ? 'image/png' : 'text/html', headers: { 'access-control-allow-origin': '*' }, body: r.resourceType() === 'image' ? Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64') : '<html></html>' }); }
    r.continue();
  });
  await page.evaluateOnNewDocument(() => { window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI}`)); });
  await page.goto(BASE + startUrl, { waitUntil: 'networkidle0' });
  await page.evaluate(() => { window.__sameDocument = true; });
  const t = (out[label] = { startUrl });
  if (viaClick) {
    await page.evaluate(() => [...document.querySelectorAll('a,button')].find((e) => /Pay now/.test(e.textContent))?.click());
    await sleep(2500);
  }
  t.urlNow = page.url().replace(BASE, '');
  t.softNavigation = await page.evaluate(() => window.__sameDocument === true);
  t.documentNavigationEntries = await page.evaluate(() => performance.getEntriesByType('navigation').length);
  t.payButton = await page.evaluate(() => [...document.querySelectorAll('button')].filter((x) => /^Pay/.test(x.textContent.trim())).map((x) => `${x.textContent.trim()} disabled=${x.disabled} busy=${x.getAttribute('aria-busy')}`));
  t.scriptLoaded = await page.evaluate(() => typeof window.Razorpay);
  t.alerts = await page.evaluate(() => [...document.querySelectorAll('[role=alert],[role=status]')].map((a) => a.textContent.trim().slice(0, 140)));
  await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => /^Pay/.test(x.textContent.trim()))?.click());
  await sleep(2000);
  t.stubOpened = await page.evaluate(() => Boolean(window.__stubOpened));
  t.afterOpen = await page.evaluate(() => ({ frameLoaded: !!window.__frameLoaded, frameInDom: !!document.querySelector('iframe[src*="razorpay"]'), beaconSent: !!window.__beaconSent, beaconError: window.__beaconError || null, imgLoaded: !!window.__imgLoaded, imgError: !!window.__imgError }));
  t.cspViolations = await page.evaluate(() => window.__csp);
  t.allowedRazorpayRequests = allowedRazorpayRequests;
  t.console = consoleMsgs.filter((m) => /Content Security Policy|Refused/.test(m)).map((m) => m.slice(0, 200));
  await ctx.close();
}
await scenario('A_soft_navigation_from_order_page', '/account/orders/EL-2026-000003/', true);
await scenario('B_hard_load_of_pay_page', '/checkout/EL-2026-000003/pay/', false);
await b.close();
fs.writeFileSync(SP + '/sec-razorpay.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
