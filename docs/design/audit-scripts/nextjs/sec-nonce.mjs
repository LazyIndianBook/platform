import fs from 'node:fs';
const SP = process.env.REVIEW_DIR || process.cwd();
const cookies = JSON.parse(fs.readFileSync(SP + '/cookies.json', 'utf8')); const COOKIE = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
const ROUTES = [['/', 0], ['/shop/physics-sample-papers-2027/', 0], ['/s/PHY-E01/', 0], ['/account/login/', 0], ['/privacy/', 0], ['/no-such-page-xyz/', 0], ['/account/', 1], ['/cart/', 1], ['/checkout/EL-2026-000003/pay/', 1], ['/s/PHY-E02/', 1]];
const nonces = new Set();
for (const [path, auth] of ROUTES) {
  const r = await fetch('http://localhost:3003' + path, { headers: auth ? { Cookie: COOKIE } : {} });
  const html = await r.text(); const csp = r.headers.get('content-security-policy') || '';
  const nonce = (csp.match(/'nonce-([^']+)'/) || [])[1]; nonces.add(nonce);
  const scripts = [...html.matchAll(/<script\b([^>]*)>/g)].map((m) => m[1]);
  const withoutNonce = scripts.filter((a) => !/\bnonce="/.test(a) && !/type="application\/ld\+json"/.test(a));
  const wrongNonce = scripts.filter((a) => /\bnonce="/.test(a) && !a.includes(`nonce="${nonce}"`));
  const inlineHandlers = (html.match(/\son(click|load|error|submit|focus|mouseover)=["']/gi) || []).length;
  const javascriptUrls = (html.match(/(href|src|action)=["']javascript:/gi) || []).length;
  const links = [...html.matchAll(/<link\b([^>]*)>/g)].map((m) => m[1]).filter((a) => /rel="preload"|rel="modulepreload"/.test(a));
  const linksNoNonce = links.filter((a) => /as="script"/.test(a) && !/nonce=/.test(a));
  const extHosts = [...new Set([...html.matchAll(/(?:src|href|action)="(https?:\/\/[^"/]+)/g)].map((m) => m[1]))].filter((h) => !h.startsWith('http://localhost:3003'));
  console.log(path.padEnd(34), auth ? 'auth' : 'anon', `scripts=${scripts.length} noNonce=${withoutNonce.length} wrongNonce=${wrongNonce.length} inlineHandlers=${inlineHandlers} javascript:urls=${javascriptUrls} scriptPreloadNoNonce=${linksNoNonce.length} externalHosts=${JSON.stringify(extHosts)}`);
}
console.log('distinct nonces over', ROUTES.length, 'requests:', nonces.size);
// the same URL twice
const a = (await fetch('http://localhost:3003/privacy/')).headers.get('content-security-policy'), b = (await fetch('http://localhost:3003/privacy/')).headers.get('content-security-policy');
console.log('same URL twice, different nonce:', a !== b);
