'use strict';
// =====================================================================
// 客户签认 —— 业主签认页「本地成功态」端到端验收（真机 + --wsgi）
// =====================================================================
//
// 这条线后端单测 / HTTP 测都测不到：它验证的是「业主签完之后，
// 再打开同一个链接会不会被一句『链接已失效』误导」。这完全是浏览器里
// localStorage 的行为，只有真实 Chrome 跑一遍才作数（npm test / CI 全绿
// 也测不到这条路径）。
//
// 由 `test_browser_server.py --script test-signoff-owner-page.cjs --wsgi` 拉起：
//   · 后端临时库 + 种好「客户甲 / 框架施工」留档（与 test-signoff.cjs 同套脚手架）；
//   · 前端静态挂在 /sitelog/ 下；
//   · 端口随机，通过 TEST_BASE 传入。
//
// 覆盖：
//   1 登录 → 员工接口生成 stage 签认令牌
//   2 打开 /sign/<token> 业主页，UI 填表 + 手写签名 + 提交
//   3 断言出现「签认完成」
//   4 刷新页面（同一链接）→ 仍显示「签认完成」，**不**显示「链接已失效」，
//     且这次刷新根本没有再打 /api/signoff/<token> 的 GET（命中本机记录）

const { chromium } = require('playwright');
const { PNG } = require('pngjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const base = process.env.TEST_BASE;
const out = process.env.TEST_OUTPUT;

const REPORT = out ? require('path').join(out, '客户签认业主页本地成功态.json') : null;
const report = { script: 'test-signoff-owner-page.cjs', mode: 'unknown', base, passed: false, steps: [], errors: [] };

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage();
  const requests = [];
  page.on('request', (req) => { requests.push(req.url()); });

  const step = async (name, fn) => {
    const started = Date.now();
    try { await fn(); report.steps.push({ name, ok: true, ms: Date.now() - started }); console.log('  ✓', name); }
    catch (error) { report.steps.push({ name, ok: false, error: String(error) }); report.errors.push(name + ': ' + error); throw error; }
  };

  // ---- 登录（借用 test-signoff.cjs 的脚手架账号）----
  await page.goto(base + '/sitelog/');
  await page.locator('#login-user').fill('admin');
  await page.locator('#login-pass').fill('Test-admin-initial-12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForFunction(() => { const a = window.Alpine && Alpine.$data(document.body); return a?.draftOwner && !a.draftHydrating; }, null, { timeout: 20000 });

  // ---- 员工接口：查地址 → 生成 stage 签认令牌 ----
  const api = (url, body) => page.evaluate(({ url, body }) => Alpine.$data(document.body).accountJSON(url, body), { url, body });
  const list = await api('/addresses?q=' + encodeURIComponent('客户甲') + '&page=1');
  const aid = (list.items || []).find((it) => (it.label || '').includes('甲地址'))?.id;
  assert.ok(aid, '找不到脚手架种下的「甲地址」');
  const tokenResp = await api('/addresses/' + aid + '/signoff-token', { kind: 'stage', stage_key: '框架施工', slot: 0 });
  assert.ok(tokenResp.token, '令牌签发失败：' + JSON.stringify(tokenResp));
  const token = tokenResp.token;
  assert.ok(/^[A-Za-z0-9_-]{20,64}$/.test(token), '令牌格式异常：' + token);

  // ---- 打开业主签认页 ----
  await page.goto(base + '/sign/' + token);
  await page.getByText('手写签名', { exact: true }).waitFor({ timeout: 10000 });

  await step('业主 UI 签认：填表 + 手写签名 + 提交 → 出现「签认完成」', async () => {
    await page.locator('#name').fill('张三');
    await page.locator('#phone').fill('13800138000');
    const box = await page.locator('#pad').boundingBox();
    assert.ok(box, '找不到签名画板');
    await page.mouse.move(box.x + 40, box.y + 40);
    await page.mouse.down();
    await page.mouse.move(box.x + 140, box.y + 100, { steps: 12 });
    await page.mouse.move(box.x + 220, box.y + 55, { steps: 12 });
    await page.mouse.up();
    await page.locator('#submit').click();
    await page.getByText('签认完成').waitFor({ timeout: 10000 });
    assert.ok(await page.locator('#state-done').isVisible(), '签认完成后完成态不可见');
    // 完成提示里应带有签字人与范围。
    const note = await page.locator('#done-note').textContent();
    assert.ok(note.includes('张三'), '完成提示未含签字人：' + note);
  });

  await step('刷新同一链接 → 仍显示「签认完成」，不显示「链接已失效」，且不再请求服务端', async () => {
    requests.length = 0; // 只看刷新之后的请求
    await page.reload();
    await page.waitForLoadState('networkidle').catch(() => {});
    // 本机命中：直接显示 done，不会进 GET。
    await page.locator('#state-done').waitFor({ state: 'visible', timeout: 10000 });
    assert.ok(await page.locator('#state-done').isVisible(), '刷新后完成态不可见');
    assert.ok(!(await page.locator('#state-invalid').isVisible().catch(() => false)), '刷新后竟显示「链接已失效」');
    const hit = requests.some((u) => u.includes('/api/signoff/' + token));
    assert.ok(!hit, '刷新后本应命中本机记录，却仍向服务端请求了 ' + token);
  });

  await browser.close();
  report.passed = true;
}

main()
  .then(() => { if (REPORT) fs.writeFileSync(REPORT, JSON.stringify(report, null, 2)); process.exit(report.passed ? 0 : 1); })
  .catch((error) => { report.errors.push(String(error)); if (REPORT) fs.writeFileSync(REPORT, JSON.stringify(report, null, 2)); console.error(error); process.exit(1); });
