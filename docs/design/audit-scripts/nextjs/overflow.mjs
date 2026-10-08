// widest elements at a given width: node overflow.mjs <width> <paths...>
import { launch, open } from './lib.mjs';
const width = Number(process.argv[2]);
const browser = await launch();
for (const url of process.argv.slice(3)) {
  const { page } = await open(browser, url, { width, height: 800, dpr: 1, auth: process.env.AUTH === '1' });
  const out = await page.evaluate((vw) => {
    const doc = document.documentElement.scrollWidth;
    const wide = [...document.querySelectorAll('body *')].map((el) => ({ el, r: el.getBoundingClientRect() }))
      .filter(({ r }) => r.right > vw + 0.5 && r.width > 0)
      .map(({ el, r }) => `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
    return { doc, wide: wide.slice(0, 8) };
  }, width);
  console.log(width, url, 'scrollWidth', out.doc); for (const w of out.wide) console.log('   ', w);
}
await browser.close();
