// JavaScript a page loads (Chrome, 412 px, until the network is idle): every script response, gzipped at level 6 as
// Next's compression sends it, summed per route. node jsload.mjs [auth] -- paths…  (AUTH=1 for the signed-in cookies)
import { gzipSync } from 'node:zlib';
import { launch, open } from './lib.mjs';
const paths = process.argv.slice(2);
const browser = await launch();
const rows = [];
for (const path of paths) {
  const seen = new Map();
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 1.75 });
  if (process.env.AUTH === '1') for (const c of JSON.parse((await import('node:fs')).readFileSync(process.env.REVIEW_DIR + '/cookies.json', 'utf8'))) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/' });
  page.on('response', async (response) => {
    if (response.request().resourceType() !== 'script') return;
    try { const body = await response.buffer(); seen.set(response.url(), gzipSync(body, { level: 6 }).length); } catch {}
  });
  const answer = await page.goto(process.env.BASE + path, { waitUntil: 'networkidle0', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 500));
  const total = [...seen.values()].reduce((a, b) => a + b, 0);
  rows.push({ path, status: answer.status(), scripts: seen.size, gzipKB: +(total / 1024).toFixed(1) });
  await ctx.close();
}
console.table(rows);
console.log(JSON.stringify(rows));
await browser.close();
