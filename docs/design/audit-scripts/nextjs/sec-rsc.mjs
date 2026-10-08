// What the browser really sends for client-side navigation and prefetch (captured), replayed with and without the session.
import fs from 'node:fs';
import { launch, open, sleep, SP } from './lib.mjs';
const cookies = JSON.parse(fs.readFileSync(SP + '/cookies.json', 'utf8'));
const COOKIE = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
const MARKERS = ['nx-review-temp@example.com', 'Review Temp', 'EL-2026-000003'];
const b = await launch();
const captured = [];
const { ctx, page } = await open(b, '/account/', { auth: true, wait: 'networkidle0' });
page.on('request', (r) => { if (r.url().includes('_rsc=')) captured.push({ url: r.url(), headers: r.headers(), phase: 'later', method: r.method() }); });
// requests made during load are not in `captured` (listener added after goto): reload with listener first
await page.close();
const page2 = await ctx.newPage(); await page2.setViewport({ width: 375, height: 812 });
const seen = [];
page2.on('request', (r) => { if (r.url().includes('_rsc=')) seen.push({ url: r.url(), headers: r.headers() }); });
await page2.goto('http://localhost:3003/account/', { waitUntil: 'networkidle0' }); await sleep(1500);
const prefetches = seen.slice();
// a real navigation: click "My orders" in the account nav
seen.length = 0;
await page2.evaluate(() => [...document.querySelectorAll('nav a')].find((a) => a.getAttribute('href') === '/account/orders/')?.click()); await sleep(2000);
const nav = seen.filter((s) => !/next-router-prefetch/i.test(Object.keys(s.headers).join(',')));
console.log('prefetch requests during load:', prefetches.length, '| requests after click:', seen.length, '| non-prefetch after click:', nav.length);
console.log('sample prefetch headers:', JSON.stringify(Object.fromEntries(Object.entries(prefetches[0].headers).filter(([k]) => /^(rsc|next-|purpose|sec-purpose|accept|cookie)/i.test(k)).map(([k, v]) => [k, k === 'cookie' ? '<cookie>' : String(v).slice(0, 90)]))));
if (nav[0]) console.log('sample navigation headers:', JSON.stringify(Object.fromEntries(Object.entries(nav[0].headers).filter(([k]) => /^(rsc|next-|purpose|sec-purpose|accept|cookie)/i.test(k)).map(([k, v]) => [k, k === 'cookie' ? '<cookie>' : String(v).slice(0, 90)]))), nav[0].url);
const replay = async (req, cookie) => {
  const headers = { ...req.headers }; delete headers.cookie; delete headers.host; delete headers['accept-encoding']; delete headers.connection; delete headers['content-length']; delete headers.referer; delete headers['sec-fetch-site']; delete headers['sec-fetch-mode']; delete headers['sec-fetch-dest']; delete headers['user-agent'];
  if (cookie) headers.cookie = COOKIE;
  const r = await fetch(req.url, { headers, redirect: 'manual' });
  const body = await r.text();
  return { status: r.status, cache: r.headers.get('cache-control'), vary: (r.headers.get('vary') || '').slice(0, 80), ct: r.headers.get('content-type'), size: body.length, personal: MARKERS.filter((m) => body.includes(m)), csp: !!r.headers.get('content-security-policy'), location: r.headers.get('location') };
};
const out = { prefetch: [], navigation: [] };
const uniq = new Map(); for (const p of prefetches) uniq.set(p.url.split('?')[0], p);
for (const [path, req] of uniq) { out.prefetch.push({ path: path.replace('http://localhost:3003', ''), anon: await replay(req, false), auth: await replay(req, true), prefetchHeader: req.headers['next-router-prefetch'], segmentPrefetch: req.headers['next-router-segment-prefetch'] }); }
for (const req of nav) out.navigation.push({ path: req.url.split('?')[0].replace('http://localhost:3003', ''), anon: await replay(req, false), auth: await replay(req, true) });
fs.writeFileSync(SP + '/sec-rsc.json', JSON.stringify(out, null, 1));
for (const p of out.prefetch) console.log('PREFETCH', p.path.padEnd(28), 'anon:', p.anon.status, p.anon.cache, 'size', p.anon.size, 'personal', p.anon.personal.length, '| auth:', p.auth.status, p.auth.cache, 'size', p.auth.size, 'personal', p.auth.personal.length, '| prefetch hdr', p.prefetchHeader, p.segmentPrefetch ? 'segment ' + p.segmentPrefetch.slice(0, 30) : '');
for (const p of out.navigation) console.log('NAVIGATE', p.path.padEnd(28), 'anon:', p.anon.status, p.anon.cache, 'size', p.anon.size, 'personal', p.anon.personal.length, p.anon.location || '', '| auth:', p.auth.status, p.auth.cache, 'size', p.auth.size, 'personal', p.auth.personal.length, '| vary', p.auth.vary);
await ctx.close(); await b.close();
