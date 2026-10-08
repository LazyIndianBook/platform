// What shifts on /account/: layout-shift entries with their sources, under the mobile profile (slow 4G, 4x CPU).
import fs from 'node:fs';
import { launch, sleep, SP, BASE, cookies } from './lib.mjs';
const b = await launch();
const results = [];
for (const path of ['/account/', '/account/orders/', '/account/record/']) for (let i = 0; i < 4; i++) {
  const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 1.75, isMobile: true, hasTouch: true });
  for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
  const client = await page.createCDPSession();
  await client.send('Network.enable'); await client.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await page.evaluateOnNewDocument(() => {
    window.__ls = [];
    const name = (n) => (n ? n.nodeName.toLowerCase() + (n.id ? '#' + n.id : '') + '.' + String(n.className || '').split(' ')[0] : '?');
    const po = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        window.__ls.push({ t: Math.round(e.startTime), value: Number(e.value.toFixed(4)), hadInput: e.hadRecentInput, sources: (e.sources || []).map((s) => ({ node: name(s.node), prev: [Math.round(s.previousRect.y), Math.round(s.previousRect.height)], cur: [Math.round(s.currentRect.y), Math.round(s.currentRect.height)] })) });
      }
    });
    po.observe({ type: 'layout-shift', buffered: true });
  });
  await page.goto(BASE + path, { waitUntil: 'load' }); await sleep(2500);
  const ls = await page.evaluate(() => window.__ls);
  const total = ls.filter((e) => !e.hadInput).reduce((s, e) => s + e.value, 0);
  results.push({ path, run: i + 1, total: Number(total.toFixed(3)), entries: ls });
  console.log(path, 'run', i + 1, 'CLS', total.toFixed(3), JSON.stringify(ls.map((e) => ({ t: e.t, v: e.value, src: e.sources.map((s) => `${s.node} y ${s.prev[0]}->${s.cur[0]} h ${s.prev[1]}->${s.cur[1]}`) }))).slice(0, 420));
  await ctx.close();
}
await b.close();
fs.writeFileSync(SP + '/cls-account.json', JSON.stringify(results, null, 1));
