// 复现「上传照片后的卡片」：走真实上传路径（handleFileSelect），看 meta/desc 是否还带时间标注
const { chromium } = require('/Users/chujiangai/repos/sitelog-ai/node_modules/playwright');
const base = process.env.TEST_BASE;

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.TEST_CHROME });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.stack || e.message));
    await page.goto(base + '/sitelog/');
    await page.locator('#login-user').fill('admin');
    await page.locator('#login-pass').fill('Test-admin-initial-12345');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.locator('#login-user').waitFor({ state: 'hidden' });

    await page.locator('#node-input-empty').setInputFiles(['/tmp/p1.png', '/tmp/p2.png', '/tmp/p3.png']);
    await page.waitForTimeout(2500);

    const cards = await page.evaluate(() => Array.from(document.querySelectorAll('#images-container .node-card')).map((c) => ({
      cls: c.className,
      title: (c.querySelector('.node-card-title') || c.querySelector('h3') || {}).textContent || '',
      meta: (c.querySelector('.node-card-meta') || {}).textContent || '',
      desc: (c.querySelector('.node-card-desc') || {}).value ?? (c.querySelector('.node-card-desc') || {}).textContent ?? '',
      html: c.outerHTML.replace(/\s+/g, ' ').slice(0, 260),
    })));
    const reportText = await page.locator('#report-content').innerText();
    console.log(JSON.stringify({
      cardCount: cards.length,
      cards,
      reportHasLabel: /拍摄时间|整理时间/.test(reportText),
      pageErrors: errors,
    }, null, 2));
    await page.locator('#images-container').screenshot({ path: '/tmp/pq-grid.png' });
  } finally { await browser.close(); }
})().catch((e) => { console.error('REPRO_FAILED', e); process.exit(1); });
