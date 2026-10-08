// Anonymous server-side calls (publicFetch, 404 lookups) carry no client address, so DRF counts them all against the
// frontend's own address. A burst of lookups for pages that do not exist should show how far that goes.
import fs from 'node:fs';
const SP = process.env.REVIEW_DIR || process.cwd();
const logLen = () => fs.readFileSync(SP + '/django.log', 'utf8').length;
const before = logLen();
const probe = async (path) => { const r = await fetch('http://localhost:3003' + path); const t = await r.text(); const main = t.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, ''); return { status: r.status, text: (/We could not find that page/.test(main) ? '404 page' : /cannot be reached/.test(main) ? 'UNAVAILABLE state' : 'other') }; };
console.log('before the burst  /s/NOPE-before/:', JSON.stringify(await probe('/s/NOPE-before/')));
const N = 320; let next = 0; const codes = {};
const t0 = Date.now();
await Promise.all(Array.from({ length: 20 }, async () => { while (next < N) { const i = next++; const r = await fetch(`http://localhost:3003/s/NOPE-${i}/`); await r.arrayBuffer(); codes[r.status] = (codes[r.status] || 0) + 1; } }));
console.log(`burst: ${N} requests in ${((Date.now() - t0) / 1000).toFixed(1)} s, statuses from the frontend:`, JSON.stringify(codes));
const log = fs.readFileSync(SP + '/django.log', 'utf8').slice(before);
const lines = log.split('\n').filter((l) => /GET \/api\/v1\/qr\/NOPE/.test(l));
const by = {}; for (const l of lines) { const m = / (\d{3}) \d+$/.exec(l); if (m) by[m[1]] = (by[m[1]] || 0) + 1; }
console.log('Django answered the qr lookups:', JSON.stringify(by), '(first 429 after', lines.findIndex((l) => / 429 /.test(l)), 'lookups)');
console.log('right after the burst:');
console.log('  /s/NOPE-after/        ', JSON.stringify(await probe('/s/NOPE-after/')));
console.log('  /shop/no-such-product/', JSON.stringify(await probe('/shop/no-such-product/')));
console.log('  / (cached catalogue)   ', JSON.stringify(await probe('/')));
const r = await fetch('http://localhost:3003/api/v1/config/'); console.log('  a browser API call /api/v1/config/ from the same address:', r.status, r.status === 429 ? (await r.text()).slice(0, 120) : '');
// how long does it last: poll once a few seconds for up to 70 s
let recovered = null; for (let s = 0; s <= 70 && recovered === null; s += 5) { const p = await probe('/s/NOPE-poll-' + s + '/'); if (p.text === '404 page') recovered = s; else await new Promise((r) => setTimeout(r, 5000)); }
console.log('recovered (404 page again) after about', recovered, 's');
