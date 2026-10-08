// node lh.mjs <tag> [onlyIds]  -> Lighthouse over the page list (mobile x2; desktop x1 for home and product). json/<tag>-<id>-<form>-<n>.report.{json,html}
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, appendFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const ROOT = process.env.REVIEW_DIR || process.cwd();
const CLI = ROOT + '/node_modules/lighthouse/cli/index.js';
const [tag, onlyArg] = process.argv.slice(2);
const only = onlyArg ? onlyArg.split(',') : null;
const BASE = process.env.BASE || 'http://localhost:3003';
const cookies = JSON.parse(readFileSync(ROOT + '/cookies.json', 'utf8'));
const COOKIE = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
const log = path.join(ROOT, `run-${tag}.log`);
const say = (m) => { const l = `${new Date().toISOString()} ${m}\n`; appendFileSync(log, l); process.stdout.write(l); };
const PAGES = [
  { id: 'home', url: '/', auth: false },
  { id: 'shop', url: '/shop/', auth: false },
  { id: 'product', url: '/shop/physics-sample-papers-2027/', auth: false },
  { id: 'cart', url: '/cart/', auth: true },
  { id: 'checkout', url: '/checkout/', auth: true },
  { id: 'paperopen', url: '/s/PHY-E01/', auth: false },
  { id: 'paperauth', url: '/s/PHY-E02/', auth: true },
  { id: 'account', url: '/account/', auth: true },
  { id: 'login', url: '/account/login/', auth: false },
  { id: 'revision', url: '/revision/', auth: false },
  { id: 'privacy', url: '/privacy/', auth: false },
  { id: 'notfound', url: '/no-such-page-xyz/', auth: false, ignoreStatus: true },
];
const JOBS = [];
for (const p of PAGES) JOBS.push({ ...p, form: 'mobile', n: 1 }, { ...p, form: 'mobile', n: 2 });
for (const id of ['home', 'product']) JOBS.push({ ...PAGES.find((p) => p.id === id), form: 'desktop', n: 1 });
function run(job) {
  const out = path.join(ROOT, 'json', `${tag}-${job.id}-${job.form}-${job.n}`);
  const args = [CLI, BASE + job.url, '--quiet', '--chrome-flags=--headless=new', '--only-categories=performance,accessibility,best-practices,seo', '--output=json', '--output=html', `--output-path=${out}`];
  if (job.form === 'desktop') args.push('--preset=desktop');
  if (job.auth) args.push('--extra-headers', JSON.stringify({ Cookie: COOKIE }));
  if (job.ignoreStatus) args.push('--ignore-status-code');
  for (let attempt = 1; attempt <= 3; attempt++) {
    const t0 = Date.now();
    const res = spawnSync('node', args, { env: { ...process.env, CHROME_PATH: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' }, encoding: 'utf8', timeout: 200000 });
    const file = `${out}.report.json`;
    let note = '';
    if (existsSync(file)) {
      const r = JSON.parse(readFileSync(file, 'utf8'));
      if (!r.runtimeError) {
        const s = Object.fromEntries(Object.entries(r.categories).map(([k, c]) => [k.slice(0, 4), Math.round(c.score * 100)]));
        say(`OK  ${tag} ${job.id} ${job.form} #${job.n} attempt ${attempt} ${((Date.now() - t0) / 1000).toFixed(0)}s ${JSON.stringify(s)} LCP=${r.audits['largest-contentful-paint'].displayValue} TBT=${r.audits['total-blocking-time'].displayValue} CLS=${r.audits['cumulative-layout-shift'].displayValue} bench=${Math.round(r.environment.benchmarkIndex)} final=${r.finalDisplayedUrl}`);
        return true;
      }
      note = `${r.runtimeError.code}`;
    } else note = (res.stderr || '').slice(0, 200);
    say(`ERR ${tag} ${job.id} ${job.form} #${job.n} attempt ${attempt}: ${note}`);
  }
  return false;
}
say(`start ${tag} ${BASE} jobs=${JOBS.length}`);
for (const job of JOBS) { if (only && !only.includes(job.id)) continue; run(job); }
writeFileSync(path.join(ROOT, `done-${tag}`), new Date().toISOString());
say('finished');
