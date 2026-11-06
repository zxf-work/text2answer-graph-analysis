// Screenshots of the demo UI for the write-up. Usage: node demo/shoot.js http://127.0.0.1:8765 out_dir [sceneIndex]
const { chromium } = require('playwright');
(async () => {
  const [base, out, idx] = [process.argv[2] || 'http://127.0.0.1:8765', process.argv[3] || '.', process.argv[4]];
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 });
  page.on('pageerror', (e) => console.log('pageerror', e.message));
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.evaluate(() => { try { localStorage.setItem('t2a_help_seen', '1'); } catch {} });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.ds');
  // 1. landing with a dataset picked
  await page.click('.ds:has-text("trust")');
  await page.waitForSelector('.stat');
  await page.screenshot({ path: `${out}/01_graph_profile.png` });
  // 2. a replayed scene
  const scenes = await page.evaluate(async () => (await (await fetch('/api/scenes')).json()).length);
  if (scenes) {
    await page.click('#btn-scenes'); await page.waitForSelector('.scene');
    await page.screenshot({ path: `${out}/02_guided_demo.png` });
    await page.click(`.scene >> nth=${idx || 0}`);
    await page.waitForSelector('#result:not(.hidden) .big, #result:not(.hidden) .pill, #result:not(.hidden) .clarify');
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${out}/03_result.png`, fullPage: true });
    const n = await page.evaluate(() => document.querySelectorAll('.scene').length);
    for (let i = 1; i < n; i++) {
      await page.click('#btn-scenes'); await page.click(`.scene >> nth=${i}`); await page.waitForTimeout(500);
      await page.screenshot({ path: `${out}/scene_${i + 1}.png`, fullPage: true });
    }
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
