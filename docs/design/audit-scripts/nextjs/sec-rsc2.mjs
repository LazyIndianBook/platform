// Response headers of the browser's own client-side navigation requests (not replays): public pages, signed in and out.
import { launch, open, sleep, BASE } from './lib.mjs';
const b = await launch();
for (const [label, auth] of [['anonymous', false], ['signed in', true]]) {
  const { ctx, page } = await open(b, '/', { auth });
  await sleep(1500);
  const seen = [];
  page.on('response', (r) => { const q = r.request(); if (q.url().includes('_rsc=') && !q.headers()['next-router-prefetch']) seen.push({ url: q.url().replace(BASE, '').split('?')[0], status: r.status(), cache: r.headers()['cache-control'], vary: (r.headers().vary || '').slice(0, 50), csp: Boolean(r.headers()['content-security-policy']), type: r.headers()['content-type'] }); });
  for (const href of ['/shop/', '/privacy/', auth ? '/account/' : '/account/login/', '/cart/']) {
    await page.evaluate((h) => (document.querySelector(`a[href="${h}"]`) || (() => { const a = document.createElement('a'); a.href = h; document.body.appendChild(a); return a; })()).click(), href); await sleep(1500);
    await page.goto(BASE + '/', { waitUntil: 'networkidle0' }); await sleep(500);
  }
  console.log(label); for (const s of seen) console.log('  ', JSON.stringify(s));
  await ctx.close();
}
await b.close();
