// CSP and Cache-Control per route, anonymous and signed in, for the HTML request, the client navigation's RSC request
// (?_rsc= with RSC: 1) and the router's prefetch (Next-Router-Prefetch: 1): headers and what the body holds.
import fs from 'node:fs';
const SP = process.env.REVIEW_DIR || process.cwd();
const BASE = 'http://localhost:3003';
const cookies = JSON.parse(fs.readFileSync(SP + '/cookies.json', 'utf8'));
const COOKIE = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
const PERSONAL_MARKERS = ['nx-review-temp@example.com', 'Review Temp', 'EL-2026-000003'];
const ROUTES = ['/', '/shop/', '/shop/physics-sample-papers-2027/', '/books/physics-2027/', '/privacy/', '/about/', '/revision/', '/s/PHY-E01/', '/s/PHY-E02/', '/account/login/', '/account/signup/', '/orders/lookup/', '/contact/', '/no-such-page-xyz/',
  '/account/', '/account/orders/', '/account/orders/EL-2026-000003/', '/account/security/', '/cart/', '/checkout/', '/checkout/EL-2026-000003/pay/', '/checkout/EL-2026-000003/done/', '/orders/t/bogus-token/', '/c/bogus-token/', '/orders/', '/offline/', '/api/health/', '/sitemap.xml', '/robots.txt', '/manifest.webmanifest', '/sw.js', '/icon.svg', '/favicon-32.png'];
const out = [];
async function get(path, { cookie, rsc, prefetch } = {}) {
  const headers = { Accept: rsc ? 'text/x-component' : 'text/html', 'Accept-Encoding': 'identity' };
  if (cookie) headers.Cookie = COOKIE;
  if (rsc) { headers.RSC = '1'; }
  if (prefetch) { headers['Next-Router-Prefetch'] = '1'; headers['Next-Router-State-Tree'] = encodeURIComponent(JSON.stringify(['', { children: ['__PAGE__', {}] }, null, null, true])); }
  const url = BASE + path + (rsc || prefetch ? (path.includes('?') ? '&' : '?') + '_rsc=abc12' : '');
  const r = await fetch(url, { headers, redirect: 'manual' });
  const body = await r.text();
  const h = (n) => r.headers.get(n);
  const csp = h('content-security-policy');
  return { status: r.status, location: h('location'), ct: (h('content-type') || '').split(';')[0], cache: h('cache-control'), vary: h('vary'), etag: h('etag'), csp, xRobots: h('x-robots-tag'), size: body.length, personal: PERSONAL_MARKERS.filter((m) => body.includes(m)), robotsMeta: (body.match(/<meta name="robots" content="([^"]*)"/g) || []).map((s) => s.replace(/.*content="/, '').replace('"', '')), body };
}
const cspFacts = (csp) => {
  if (!csp) return null;
  const dir = Object.fromEntries(csp.split(';').map((s) => s.trim()).filter(Boolean).map((s) => { const [n, ...v] = s.split(/\s+/); return [n, v]; }));
  const script = dir['script-src'] || [];
  return { nonce: script.some((v) => /^'nonce-/.test(v)), strictDynamic: script.includes("'strict-dynamic'"), unsafeInlineScript: script.includes("'unsafe-inline'"), unsafeEval: script.includes("'unsafe-eval'"), razorpay: /razorpay/.test(csp), turnstile: /challenges\.cloudflare\.com/.test(csp), frameAncestors: (dir['frame-ancestors'] || []).join(' '), scriptHosts: script.filter((v) => /^https?:/.test(v)), connect: (dir['connect-src'] || []).join(' '), img: (dir['img-src'] || []).join(' ') };
};
for (const path of ROUTES) {
  for (const cookie of [false, true]) {
    for (const mode of ['html', 'rsc', 'prefetch']) {
      const isFile = /\.(xml|txt|webmanifest|js|svg|png)$/.test(path) || path.startsWith('/api/');
      if (isFile && mode !== 'html') continue;
      try {
        const r = await get(path, { cookie, rsc: mode === 'rsc', prefetch: mode === 'prefetch' });
        out.push({ path, auth: cookie, mode, status: r.status, location: r.location, ct: r.ct, cache: r.cache, vary: r.vary && r.vary.slice(0, 60), etag: r.etag, csp: cspFacts(r.csp), hasCsp: Boolean(r.csp), size: r.size, personal: r.personal, robotsMeta: r.robotsMeta, xRobots: r.xRobots });
      } catch (e) { out.push({ path, auth: cookie, mode, error: String(e).slice(0, 100) }); }
    }
  }
}
fs.writeFileSync(SP + '/sec-headers.json', JSON.stringify(out, null, 1));
for (const r of out) console.log(`${r.path.padEnd(38)} ${r.auth ? 'auth' : 'anon'} ${r.mode.padEnd(8)} ${String(r.status).padEnd(4)} cache=${(r.cache || '-').padEnd(52)} csp=${r.hasCsp ? 'y' : 'n'}${r.csp ? (r.csp.razorpay ? ' RZP' : '') + (r.csp.turnstile ? ' TS' : '') : ''} personal=${(r.personal || []).length} robots=${(r.robotsMeta || []).join('|') || '-'}${r.location ? ' -> ' + r.location : ''}`);
