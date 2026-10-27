// Capture loading posters from the current Hand Studio renderer and materials.
// Run against a local HTTP server; these JPEGs are previews, never physics assets.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const out = path.join(root, 'assets/images/studio/posters');
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.STUDIO_URL || 'http://127.0.0.1:8766/#hand-studio');
    await page.locator('#hand-studio').scrollIntoViewIfNeeded();
    const records = await page.evaluate(async () =>
      (await (await fetch('assets/models/studio/catalog.json')).json()).records);
    const selected = new Set((process.env.POSTER_MODELS || '').split(',').filter(Boolean));
    fs.mkdirSync(out, { recursive: true });
    for (const record of records.filter(record => !selected.size || selected.has(record.id))) {
      await page.locator('#studio-category').selectOption(record.category);
      await page.locator('#studio-model').selectOption(record.id);
      await page.waitForFunction(name => {
        const title = document.querySelector('#studio-name');
        const loading = document.querySelector('#studio-loading');
        return title?.textContent === name && loading?.hidden;
      }, record.name, { timeout: 60000 });
      if (record.category === 'manipulator') await page.locator('#studio-eef').selectOption('none');
      await page.waitForTimeout(150);
      const target = path.join(out, `${record.id}.jpg`);
      await page.locator('#studio-viewport').screenshot({ path: target, type: 'jpeg', quality: 90 });
      console.log(`${record.id}: ${target}`);
    }
    if (errors.length) throw new Error(errors.join('\n'));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
