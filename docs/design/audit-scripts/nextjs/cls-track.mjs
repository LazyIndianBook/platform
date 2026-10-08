// Track the footer's position (and the placeholder) frame by frame while /account/ loads under the mobile profile.
import fs from 'node:fs';
import { launch, sleep, SP, BASE, cookies } from './lib.mjs';
const b = await launch();
for (let i = 0; i < 8; i++) {
  const ctx = await b.createBrowserContext(); const page = await ctx.newPage(); await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 1.75, isMobile: true, hasTouch: true });
  for (const c of cookies()) await ctx.setCookie({ name: c.name, value: c.value, domain: 'localhost', path: '/', httpOnly: c.httpOnly });
  const client = await page.createCDPSession();
  await client.send('Network.enable'); await client.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await page.evaluateOnNewDocument(() => {
    window.__track = []; let last = '';
    const tick = () => {
      const f = document.querySelector('footer'); const m = document.querySelector('main');
      if (f && m) { const key = `${Math.round(f.getBoundingClientRect().top + scrollY)}|${Math.round(m.getBoundingClientRect().height)}|${document.querySelectorAll('[data-slot=skeleton]').length}`; if (key !== last) { last = key; window.__track.push(`${Math.round(performance.now())}ms footerTop=${key.split('|')[0]} mainH=${key.split('|')[1]} skeletons=${key.split('|')[2]}`); } }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await page.goto(BASE + '/account/', { waitUntil: 'load' }); await sleep(2500);
  const tr = await page.evaluate(() => window.__track);
  console.log('run', i + 1, tr.length > 1 ? 'CHANGES: ' : 'stable: ', tr.join(' -> '));
  await ctx.close();
}
await b.close();
