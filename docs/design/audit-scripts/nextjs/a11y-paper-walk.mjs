import { launch, open, sleep } from './lib.mjs';
import { focusInfo } from './inpage.mjs';
const b = await launch();
for (const [label, url, auth] of [['/s/PHY-E01/ anonymous', '/s/PHY-E01/', false], ['/s/PHY-E02/ signed in', '/s/PHY-E02/', true], ['/s/PHY-E01/ signed in', '/s/PHY-E01/', true]]) {
  const { ctx, page } = await open(b, url, { auth }); await sleep(600);
  const order = []; let none = 0;
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press('Tab'); await sleep(70);
    let f = await page.evaluate(focusInfo);
    if (f.none) { none++; if (none > 1) break; order.push('(browser UI / wrap)'); continue; }
    for (let k = 0; k < 6; k++) { await sleep(60); const g = await page.evaluate(focusInfo); const same = g.sel === f.sel && g.rect.y === f.rect.y && g.scrollY === f.scrollY; f = g; if (same) break; }
    order.push(`${f.sel.slice(0, 26)} "${f.text.slice(0, 24)}" ring=${f.ringContrast} cover=${f.fullyCovered ? 'FULL' : f.partlyCovered ? 'part' : '-'} off=${f.partlyOffscreen}`);
    if (order.length > 1 && order[order.length - 1] === order[0]) break;
  }
  console.log(label, 'stops until the walk wraps:', order.length, '| issues:', order.filter((o) => /cover=(FULL|part)|ring=null|off=true/.test(o)).slice(0, 4));
  console.log('   first 9:', order.slice(0, 9).map((o) => o.split(' ring')[0]).join(' | '));
  await ctx.close();
}
await b.close();
