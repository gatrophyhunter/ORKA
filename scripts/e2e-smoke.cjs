// Playwright smoke test for the ORKA UI (fictional test components only).
const { chromium } = require('playwright');
const OUT = process.env.ORKA_E2E_OUT || require('path').join(require('os').tmpdir(), 'orka-e2e');
require('fs').mkdirSync(OUT, { recursive: true });
const URL = process.env.ORKA_E2E_URL || 'http://localhost:4173/';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  const external = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('request', (r) => { const u = r.url(); if (!u.startsWith('http://localhost:4173') && !u.startsWith('data:') && !u.startsWith('blob:')) external.push(u); });
  const step = async (name, fn) => {
    try { await fn(); console.log('PASS', name); }
    catch (e) { console.log('FAIL', name, '-', e.message.split('\n')[0]); await page.screenshot({ path: `${OUT}/fail-${name.replace(/\W+/g, '_')}.png`, fullPage: true }); }
  };
  const fill = async (tid, v) => { const el = page.getByTestId(tid); await el.fill(String(v)); };
  const pick = async (tid, text) => {
    const el = page.getByTestId(tid);
    await el.click();
    await el.fill(text);
    await page.locator('.picker-list [role=option]').filter({ hasText: text }).first().click();
  };

  await page.goto(URL);
  await step('ack modal shown', async () => {
    await page.getByTestId('ack').waitFor({ timeout: 5000 });
    await page.screenshot({ path: `${OUT}/01-ack-1280.png` });
    await page.getByTestId('ack').click();
  });

  await step('custom cartridge', async () => {
    await page.getByTestId('tab-database').click();
    await page.getByTestId('db-sub-cartridges').click();
    await page.getByTestId('db-add-cartridges').click();
    await fill('fc-name', 'Test Cartridge A');
    await fill('fc-dia', '0.308');
    await fill('fc-bore', '0.300');
    await fill('fc-groove', '0.308');
    await fill('fc-trim', '2.005');
    await fill('fc-coal', '2.800');
    await fill('fc-map', '62000');
    await page.getByTestId('fc-save').click();
    await page.getByTestId('db-search-cartridges').fill('Test Cartridge A');
    await page.getByTestId('db-cartridges').getByText('Test Cartridge A').waitFor();
  });

  await step('custom powder', async () => {
    await page.getByTestId('db-sub-powders').click();
    await page.getByTestId('db-add-powders').click();
    await fill('fp-mfr', 'Test Co');
    await fill('fp-name', 'Test Powder A');
    await fill('fp-bulk', '0.9');
    await page.getByTestId('fp-save').click();
    await page.getByTestId('db-search-powders').fill('Test Powder A');
    await page.getByTestId('db-powders').getByText('Test Powder A').waitFor();
    await page.screenshot({ path: `${OUT}/02-database-1280.png`, fullPage: true });
  });

  await step('manual powder params', async () => {
    await page.getByTestId('tab-calibrate').click();
    await pick('cal-powder', 'Test Powder A');
    await page.getByTestId('manual-params').locator('summary').click();
    const vals = { forceJg: 1000, flameTempK: 2900, gamma: 1.24, covolumeCm3g: 1.0, solidDensityGcc: 1.6, beta: 5, n: 1, lambda: 0 };
    for (const [k, v] of Object.entries(vals)) await fill(`mp-${k}`, v);
    await page.getByTestId('save-manual').click();
    await page.getByText('Saved.').waitFor();
  });

  await step('builder + prediction', async () => {
    await page.getByTestId('tab-predict').click();
    await pick('pick-cartridge', 'Test Cartridge A');
    await page.getByTestId('pick-brass').selectOption('measured');
    await fill('in-capacity', '56');
    await fill('in-bweight', '168');
    await fill('in-blen', '1.215');
    await fill('in-barrel', '24');
    await pick('pick-powder', 'Test Powder A');
    await fill('in-charge', '44');
    await page.getByTestId('tile-peak').waitFor({ timeout: 5000 });
    const peak = await page.getByTestId('tile-peak').innerText();
    const vel = await page.getByTestId('tile-velocity').innerText();
    console.log('   peak tile:', peak.replace(/\n/g, ' | '));
    console.log('   vel tile:', vel.replace(/\n/g, ' | '));
    if (!/psi/.test(peak)) throw new Error('no psi in peak tile');
  });

  await step('monte carlo band', async () => {
    await page.getByTestId('run-mc').click();
    await page.getByTestId('mc-results').waitFor({ timeout: 15000 });
    console.log('   mc:', (await page.getByTestId('mc-results').innerText()).replace(/\n/g, ' | '));
    await page.screenshot({ path: `${OUT}/03-predict-1280.png`, fullPage: true });
  });

  await step('ladder + solvers', async () => {
    await page.getByTestId('tab-ladder').click();
    await fill('ladder-start', '40');
    await fill('ladder-end', '48');
    await page.getByTestId('run-ladder').click();
    await page.getByTestId('ladder-table').waitFor({ timeout: 10000 });
    const over = await page.locator('[data-testid=ladder-table] tr.over').count();
    console.log('   ladder rows over limit:', over);
    await page.getByTestId('solve-max').click();
    await page.getByTestId('solve-max-result').waitFor({ timeout: 10000 });
    console.log('   max:', (await page.getByTestId('solve-max-result').innerText()).split('\n')[0]);
    await fill('target-vel', '2600');
    await page.getByTestId('solve-vel').click();
    await page.getByTestId('solve-vel-result').waitFor({ timeout: 10000 });
    await page.screenshot({ path: `${OUT}/04-ladder-1280.png`, fullPage: true });
  });

  await step('parametric search (worker)', async () => {
    await page.getByTestId('tab-search').click();
    await page.getByTestId('run-search').click();
    await page.getByTestId('search-results').waitFor({ timeout: 20000 });
    console.log('   search rows:', await page.locator('[data-testid=search-table] tbody tr').count());
    await page.screenshot({ path: `${OUT}/05-search-1280.png`, fullPage: true });
  });

  await step('calibration fit (worker)', async () => {
    await page.getByTestId('tab-calibrate').click();
    await fill('cal-charge-0', '42');
    await fill('cal-vel-0', '2560');
    await fill('cal-charge-1', '44');
    await fill('cal-vel-1', '2650');
    await fill('cal-charge-2', '46');
    await fill('cal-vel-2', '2740');
    await page.getByTestId('run-cal').click();
    await page.getByTestId('cal-result').waitFor({ timeout: 30000 });
    console.log('   cal:', (await page.getByTestId('cal-result').locator('.tiles').innerText()).replace(/\n/g, ' | '));
    await page.screenshot({ path: `${OUT}/06-calibrate-1280.png`, fullPage: true });
  });

  await step('load book', async () => {
    await page.getByTestId('tab-loads').click();
    await fill('lb-name', 'Test load');
    await page.getByTestId('lb-save').click();
    await page.getByTestId('lb-table').getByText('Test load').waitFor();
  });

  await step('validation + method tabs', async () => {
    await page.getByTestId('tab-validation').click();
    await page.getByTestId('validation-pending').or(page.getByTestId('validation-report')).first().waitFor();
    await page.getByTestId('tab-method').click();
    await page.getByTestId('method').waitFor();
  });

  await step('metric units', async () => {
    await page.getByTestId('units-metric').click();
    await page.getByTestId('tab-predict').click();
    await page.getByTestId('tile-peak').waitFor();
    const peak = await page.getByTestId('tile-peak').innerText();
    console.log('   metric peak tile:', peak.replace(/\n/g, ' | '));
    if (!/MPa/.test(peak)) throw new Error('no MPa');
    const charge = await page.getByTestId('in-charge').inputValue();
    console.log('   metric charge input:', charge);
    await page.screenshot({ path: `${OUT}/07-predict-metric-1280.png`, fullPage: true });
    await page.getByTestId('units-imperial').click();
  });

  await step('dark theme screenshot', async () => {
    await page.getByRole('button', { name: 'dark' }).click();
    await page.screenshot({ path: `${OUT}/08-predict-dark-1280.png`, fullPage: false });
    await page.getByRole('button', { name: 'auto' }).click();
  });

  await step('phone width 390', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const t of ['predict', 'ladder', 'search', 'database']) {
      await page.getByTestId(`tab-${t}`).click();
      await page.waitForTimeout(300);
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      console.log(`   ${t} scrollWidth @390:`, sw);
      if (sw > 390) throw new Error(`horizontal overflow on ${t}: ${sw}`);
      await page.screenshot({ path: `${OUT}/09-${t}-390.png`, fullPage: true });
    }
  });

  await step('builder collapse', async () => {
    await page.getByTestId('tab-predict').click();
    await page.getByTestId('builder-toggle').click();
    const txt = await page.getByTestId('load-builder').innerText();
    console.log('   collapsed summary:', txt.replace(/\n/g, ' | '));
    if (!/Test Cartridge A/.test(txt)) throw new Error('summary missing cartridge');
    await page.screenshot({ path: `${OUT}/10-predict-collapsed-390.png`, fullPage: true });
    await page.getByTestId('builder-toggle').click();
  });

  await step('reload persists state', async () => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.reload();
    await page.getByTestId('tab-predict').click();
    await page.getByTestId('tile-peak').waitFor({ timeout: 5000 });
  });

  console.log('console/page errors:', errors.length ? errors : 'none');
  console.log('external requests:', external.length ? external : 'none');
  await browser.close();
})();
