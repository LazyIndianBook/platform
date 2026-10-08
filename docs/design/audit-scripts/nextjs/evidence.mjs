import { launch, open, sleep, SP } from './lib.mjs';
const b = await launch();
{ // the shop page at 375: the layout is 583 px wide
  const { ctx, page } = await open(b, '/shop/', { width: 375, height: 812, dpr: 1 }); await sleep(800);
  await page.screenshot({ path: SP + '/shots/ev-shop-wide.png', clip: { x: 0, y: 0, width: 583, height: 812 }, captureBeyondViewport: true });
  await ctx.close();
}
{ // the home page at 320: 338 px
  const { ctx, page } = await open(b, '/', { width: 320, height: 700, dpr: 1 }); await sleep(800);
  await page.screenshot({ path: SP + '/shots/ev-home-338.png', clip: { x: 0, y: 0, width: 338, height: 700 }, captureBeyondViewport: true });
  await ctx.close();
}
await b.close();
