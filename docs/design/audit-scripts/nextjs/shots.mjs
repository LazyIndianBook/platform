// The ten pages of the Django after-craft set, at 375x812 (2x) and 1280x800 (1x), viewport only, PNG.
import { launch, open, sleep } from './lib.mjs';
const OUT = process.env.SHOTS_OUT || process.cwd() + '/screenshots-nextjs';
const PAGES = [
  { name: 'home', url: '/', auth: false },
  { name: 'shop', url: '/shop/', auth: false },
  { name: 'product', url: '/shop/physics-sample-papers-2027/', auth: false },
  { name: 'login', url: '/account/login/', auth: false },
  { name: '404', url: '/this-page-does-not-exist/', auth: false },
  { name: 'account', url: '/account/', auth: true },
  { name: 'cart', url: '/cart/', auth: true },
  { name: 'checkout', url: '/checkout/', auth: true },
  { name: 'order', url: '/account/orders/EL-2026-000003/', auth: true },
  { name: 'solutions', url: '/s/PHY-E01/', auth: true },
];
const b = await launch();
for (const p of PAGES) for (const w of [375, 1280]) {
  const { ctx, page, status, errors } = await open(b, p.url, { auth: p.auth, width: w, height: w === 375 ? 812 : 800, dpr: w === 375 ? 2 : 1 });
  await page.evaluate(() => document.fonts.ready);
  await sleep(1500);
  await page.screenshot({ path: `${OUT}/${p.name}-${w}.png` });
  console.log(p.name, w, status, errors.length ? errors : '');
  await ctx.close();
}
await b.close();
