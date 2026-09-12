const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PNG } = require('pngjs');
const jsQR = require('jsqr');
const base = process.env.TEST_BASE;
const production = base === 'https://cj-az.cn' && process.env.PRODUCTION_TEST_CONFIRM === 'sitelog-synthetic-accounts-only';
if (!base || (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base) && !production)) throw Error('测试目标未明确配置');
const out = process.env.TEST_OUTPUT;
const adminUsername = process.env.TEST_ADMIN_USERNAME || 'admin';
const workerUsername = process.env.TEST_WORKER_USERNAME || 'worker01';
const adminInitial = process.env.TEST_ADMIN_PASSWORD || 'Test-admin-initial-12345';
const adminReady = process.env.TEST_ADMIN_NEXT || 'Test-admin-ready-12345';
const workerInitial = process.env.TEST_WORKER_PASSWORD || 'Test-worker-initial-12345';
const workerReady = process.env.TEST_WORKER_NEXT || 'Test-worker-ready-12345';
if (production && (!adminUsername.startsWith('e2e-') || !workerUsername.startsWith('e2e-'))) throw Error('正式站点只能使用独立验收账号');
const errors = [];
let browser;
async function login(page, user, password) {
  await page.locator('#login-user').fill(user);
  await page.locator('#login-pass').fill(password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
}
async function changePassword(page, oldPassword, newPassword) {
  await page.locator('#password-current').fill(oldPassword);
  await page.locator('#password-next').fill(newPassword);
  await page.locator('#password-confirm').fill(newPassword);
  await page.getByRole('button', { name: '保存新密码', exact: true }).click();
  await page.locator('#login-user').waitFor({ state: 'visible' });
}
async function capture(page, name) { await page.screenshot({ path: path.join(out, name + '.png'), fullPage: false, animations: 'disabled' }); }

(async () => {
  browser = await chromium.launch({ headless: true, executablePath: process.env.TEST_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const admin = await adminContext.newPage();
  admin.on('pageerror', e => errors.push(e.message));
  await admin.goto(base + '/sitelog/');
  await capture(admin, '01-员工登录');
  await login(admin, adminUsername, adminInitial);
  await changePassword(admin, adminInitial, adminReady);
  await login(admin, adminUsername, adminReady);
  await admin.locator('#login-user').waitFor({ state: 'hidden' });
  await admin.getByRole('button', { name: /账号/ }).first().click();
  await admin.getByRole('button', { name: '员工与公司设置', exact: true }).click();
  await admin.getByLabel('新增员工姓名').fill('验收员工');
  await admin.getByLabel('新增员工账号').fill(workerUsername);
  await admin.getByLabel('新增员工初始密码').fill(workerInitial);
  await admin.getByRole('button', { name: '创建员工账号', exact: true }).click();
  await admin.getByText('员工账号已创建。', { exact: false }).waitFor();
  await capture(admin, '02-管理员建员工');
  console.log('通过：管理员首次改密、重新登录、页面创建员工。');

  const workerContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const worker = await workerContext.newPage();
  let staleAI = process.env.TEST_REAL_AI === '1';
  if (staleAI) await worker.route('**/api/share/auth/me', async route => {
    const response = await route.fetch();
    if (!response.ok() || !staleAI) return route.fulfill({ response });
    const data = await response.json(); data.ai = { configured: false, provider: 'qwen' };
    await route.fulfill({ response, json: data });
  });
  worker.on('pageerror', e => errors.push(e.message));
  await worker.goto(base + '/sitelog/');
  await login(worker, workerUsername, workerInitial);
  await changePassword(worker, workerInitial, workerReady);
  await login(worker, workerUsername, workerReady);
  await worker.locator('#login-user').waitFor({ state: 'hidden' });
  await worker.getByPlaceholder('项目名称', { exact: true }).fill('公司登录端到端验收工程');
  const image = new PNG({ width: 128, height: 128 });
  image.data.fill(220);
  for (let i = 3; i < image.data.length; i += 4) image.data[i] = 255;
  await worker.locator('input[type=file]').first().setInputFiles({ name: '施工照片.png', mimeType: 'image/png', buffer: PNG.sync.write(image) });
  await worker.locator('#report-content img').first().waitFor({ state: 'visible' });
  if (process.env.TEST_REAL_AI === '1') {
    await worker.locator('#report-content [contenteditable=true]').first().fill('审核备注保留验证');
    staleAI = false;
    const aiResponse = worker.waitForResponse(r => r.url().endsWith('/ai/analyze'), { timeout: 120000 });
    await worker.getByRole('button', { name: /AI 一键整理/ }).click();
    const response = await aiResponse;
    assert.equal(response.status(), 200);
    assert.ok((await response.json()).choices[0].message.content);
    await worker.getByRole('button', { name: /AI 一键整理/ }).waitFor({ state: 'visible', timeout: 120000 });
    assert.equal(await worker.getByPlaceholder('项目名称', { exact: true }).inputValue(), '公司登录端到端验收工程');
    assert.equal(await worker.locator('#report-content img').count(), 1);
    await worker.getByText('审核备注保留验证', { exact: true }).waitFor();
    await capture(worker, '03-AI在线恢复与真实识别');
    console.log('通过：旧状态在线恢复、腾讯云真实图片识别、照片和人工备注保留，无需重新登录。');
  }
  await worker.locator('#report-content [contenteditable=true]').first().fill('人工审核通过：固定点和密封情况均已核对。');
  await worker.getByRole('button', { name: /确认完成.*生成分享码/ }).first().click();
  await worker.getByRole('button', { name: '✅ 确认完成，生成分享码', exact: true }).click();
  await worker.getByRole('heading', { name: '🎉 分享码已生成', exact: true }).waitFor({ timeout: 30000 });
  const downloadPromise = worker.waitForEvent('download');
  await worker.getByRole('button', { name: '💾 保存分享卡', exact: true }).click();
  const download = await downloadPromise;
  const pngFile = path.join(out, '03-实际下载二维码.png');
  await download.saveAs(pngFile);
  const decodedImage = PNG.sync.read(fs.readFileSync(pngFile));
  const qr = jsQR(new Uint8ClampedArray(decodedImage.data), decodedImage.width, decodedImage.height);
  assert.ok(qr, '下载的分享卡必须可扫码');
  assert.ok(qr.data.startsWith(base + '/s/'));
  await capture(worker, '04-员工生成分享卡');
  const visitorContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const visitor = await visitorContext.newPage();
  const viewed = await visitor.goto(qr.data);
  assert.equal(viewed.status(), 200);
  await visitor.getByText('人工审核通过：固定点和密封情况均已核对。').waitFor();
  await capture(visitor, '05-手机免登录查看');
  console.log('通过：员工上传照片、人工审核、生成分享、真实下载 PNG、解码扫码、手机免登录读取审核内容。');

  const secondDevice = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const second = await secondDevice.newPage();
  await second.goto(base + '/sitelog/');
  await login(second, workerUsername, workerReady);
  await second.locator('#login-user').waitFor({ state: 'hidden' });
  await second.getByRole('button', { name: /分享管理/ }).click();
  await second.getByText('公司登录端到端验收工程 施工归档', { exact: true }).waitFor();
  await capture(second, '06-另一设备查看同账号记录');
  const cookies = await secondDevice.cookies();
  assert.ok(cookies.find(c => c.name === 'cj_sitelog_session' && c.httpOnly && c.sameSite === 'Lax' && (!production || c.secure)));
  assert.ok(!(await second.evaluate(() => document.cookie)).includes('cj_sitelog_session'));
  console.log('通过：第二设备直接登录同一员工账号，查看相同记录，未导入任何配置文件。');

  // 通过管理页面停用账号，原设备下一次请求必须立刻失效。
  await admin.getByRole('button', { name: '管理账号', exact: true }).last().click();
  await admin.getByLabel('启用账号', { exact: true }).uncheck();
  await admin.getByRole('button', { name: '保存账号修改', exact: true }).click();
  await admin.getByText('账号已更新，该员工的旧登录已失效。', { exact: true }).waitFor();
  await second.getByRole('button', { name: '🔄 刷新清单', exact: true }).click();
  await second.locator('#login-user').waitFor({ state: 'visible' });
  assert.deepEqual(errors, [], '浏览器不得出现脚本错误');
  console.log('通过：管理员页面停用账号后，第二设备旧登录立即失效。');
  fs.writeFileSync(path.join(out, '浏览器验收结果.json'), JSON.stringify({ passed: true, browserErrors: errors, flows: ['管理员改密建员工', '员工首次改密登录', '上传审核分享', '下载二维码并解码', '手机扫码', '多设备登录', '停用即时生效'] }, null, 2));
})().catch(async error => {
  console.error(error);
  if (browser) {
    let n = 0;
    for (const context of browser.contexts()) for (const page of context.pages()) {
      try { await capture(page, '失败-' + ++n); } catch {}
    }
  }
  process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); });
