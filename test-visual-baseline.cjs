#!/usr/bin/env node
'use strict';
/*
 * 视觉回归基线 —— 拆 Alpine 根组件之前必须先有这张网。
 *
 * 【为什么需要它】
 * 前端单测（157 项）是在 node 里跑纯逻辑：它读 app-main.js 的文本、用 vm 造假的
 * window/document，既不渲染、也不跑 Alpine。所以「界面其实已经坏了但测试全绿」
 * 这类缺陷它一概抓不到 —— 2026-09-25 的全站白屏就是这么漏过去的。
 * 拆根组件动了 Alpine 的数据组装方式，属于最高风险的一类改动，
 * 必须有「截图逐像素对比 + pageErrors 守卫」才能动手。
 *
 * 【它守护什么】
 *   1. pageErrors === 0（Alpine 初始化失败、方法丢失都会落到这里）
 *   2. 每个视图的关键 DOM 真的渲染出来了（不是空壳）
 *   3. 截图与 visual-baseline/ 下的基线逐像素一致
 *
 * 【怎么跑】
 *   VISUAL_UPDATE=1 首次生成/刷新基线；之后再跑即为对比。
 *   必须由后端仓库的 test_browser_server.py 带动（它起临时库+后端+静态前端，
 *   并提供 TEST_BASE / TEST_OUTPUT）：
 *
 *     cd /Users/chujiangai/repos/chujiang-sitelog-share
 *     <py3.13> test_browser_server.py --frontend /Users/chujiangai/repos/sitelog-ai \
 *       --output /tmp/visual --script test-visual-baseline.cjs
 *
 *   环境变量：VISUAL_UPDATE=1 写基线；TEST_CHROME 指本机 Chrome；
 *   node 需要 NODE_PATH 指到装了 playwright 的目录。
 *
 * 【基线为什么能稳定复现】
 *   - 数据用页面自带的「载入示例数据」（固定 SVG、固定文案、固定时间字符串）
 *   - 服务器返回的 created_at 之类时间戳一律归一化成 FROZEN_TIME
 *   - archiveDate 是客户端 new Date() 算的，手动钉死
 *   - 截图前清掉 toast（3 秒后自动消失的浮层会让每次都不一样）
 *   - animations: 'disabled' + 固定 viewport + deviceScaleFactor 1
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PNG } = require('pngjs');

const base = process.env.TEST_BASE;
const out = process.env.TEST_OUTPUT;
if (!base || !out) throw Error('需要 TEST_BASE / TEST_OUTPUT（由 test_browser_server.py 提供）');

const BASELINE_DIR = path.join(__dirname, 'visual-baseline');
const UPDATE = process.env.VISUAL_UPDATE === '1';
const VIEWPORT = { width: 1440, height: 1000 };
// 允许的比例上限。字体渲染在不同 Chrome 小版本下会有极少量像素抖动，
// 但「界面真的变了」通常是成片的差异，不会只有万分之几。
const MAX_DIFF_RATIO = 0.0005;

const FROZEN_TIME = '2026-06-23 15:30';
const FROZEN_DATE = '2026-06-23';

const VIEWS = [
  '01-登录',
  '02-工作台-示例数据',
  '03-分享弹窗',
  '04-分享管理',
  '05-地址面板',
  '06-账号设置',
  '07-业主分享页',
  '08-一址一码页',
];

const errors = [];

function readPng(file) {
  return PNG.sync.read(fs.readFileSync(file));
}
function diffPixels(a, b) {
  const pa = readPng(a);
  const pb = readPng(b);
  if (pa.width !== pb.width || pa.height !== pb.height) {
    return { diff: -1, ratio: 1, note: `尺寸不同 ${pa.width}x${pa.height} vs ${pb.width}x${pb.height}` };
  }
  let diff = 0;
  for (let i = 0; i < pa.data.length; i += 4) {
    if (pa.data[i] !== pb.data[i] || pa.data[i + 1] !== pb.data[i + 1] || pa.data[i + 2] !== pb.data[i + 2]) diff += 1;
  }
  return { diff, ratio: diff / (pa.width * pa.height), note: '' };
}

// 差异像素的外接矩形 —— 用来定位「到底哪一块变了」
function diffBBox(a, b) {
  const pa = readPng(a);
  const pb = readPng(b);
  if (pa.width !== pb.width || pa.height !== pb.height) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1, n = 0;
  for (let y = 0; y < pa.height; y++) {
    for (let x = 0; x < pa.width; x++) {
      const i = (pa.width * y + x) << 2;
      if (pa.data[i] !== pb.data[i] || pa.data[i + 1] !== pb.data[i + 1] || pa.data[i + 2] !== pb.data[i + 2]) {
        n += 1;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  return n ? { x0, y0, x1, y1, n } : null;
}

async function capture(page, name) {
  // toast 是 3 秒后自动消失的浮层，不清掉会让每次截图都不一样
  await page.evaluate(() => {
    const data = window.Alpine && window.Alpine.$data ? window.Alpine.$data(document.body) : null;
    if (data) data.toast = { show: false, msg: '', type: 'info' };
  });
  await page.waitForTimeout(350);
  const file = path.join(out, name + '.png');
  await page.screenshot({ path: file, animations: 'disabled' });

  // VISUAL_DIAG=1：当场报出差异区域落在哪个元素上（截图时页面状态还在，查得到）
  if (process.env.VISUAL_DIAG === '1') {
    const baseline = path.join(BASELINE_DIR, name + '.png');
    if (fs.existsSync(baseline)) {
      const box = diffBBox(baseline, file);
      if (!box) { console.log(`  [诊断] ${name} 无差异`); return; }
      const at = await page.evaluate(({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        if (!el) return 'null';
        return `${el.tagName}.${el.className} :: ${(el.innerText || '').slice(0, 90).replace(/\n/g, ' / ')}`;
      }, { x: box.x0 + Math.floor((box.x1 - box.x0) / 2), y: box.y0 + Math.floor((box.y1 - box.y0) / 2) });
      console.log(`  [诊断] ${name} ${box.n}px x:${box.x0}-${box.x1} y:${box.y0}-${box.y1} → ${at}`);
    }
  }
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('dialog', (d) => d.accept());

  // 时间戳归一化：分享清单的 created_at 这类文本每次运行都不同，
  // 不归一化基线第二天就必然对不上。
  await context.route('**/api/share/**', async (route) => {
    const response = await route.fetch();
    const headers = { ...response.headers() };
    delete headers['content-encoding'];
    delete headers['content-length'];
    const body = (await response.text()).replace(
      /\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?/g,
      FROZEN_TIME,
    );
    await route.fulfill({ status: response.status(), headers, body });
  });

  await page.goto(base + '/sitelog/');
  await page.waitForFunction(() => window.Alpine && window.Alpine.$data(document.body));
  await capture(page, '01-登录');

  // ---- 登录（fixture 里 must_change_password 已置 0，无需改密）----
  await page.locator('#login-user').fill('admin');
  await page.locator('#login-pass').fill('Test-admin-initial-12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.locator('#login-user').waitFor({ state: 'hidden' });

  // ---- 示例数据：固定 SVG + 固定文案，基线可复现的前提 ----
  await page.getByTitle('载入示例数据').click();
  await page.waitForFunction(() => {
    const d = window.Alpine.$data(document.body);
    return d && d.images.length === 3;
  });
  // 归档日期取自 new Date()、文档编号带 4 位随机数，两者都会让基线第二天就对不上。
  // 顺序有讲究：
  //   ① 必须在载入示例**之后**钉 —— loadSampleData 里的 resetProjectContext() 会清掉它；
  //   ② 编号只在 getTemplateHtml() 里注入（syncCoverMeta 不覆盖它），所以要再跑一次
  //      switchTemplate() 才会生效；
  //   ③ switchTemplate() 会异步重建编辑器 → 必须**等钉死的编号真的出现在页面上**再截图，
  //      否则有时截到渲染一半的界面（实测 2.8% 像素差异就是这么来的）。
  await page.evaluate((d) => {
    const a = window.Alpine.$data(document.body);
    a.archiveDate = d;
    a.documentId = 'CJ-SL-20260623-1234';
  }, FROZEN_DATE);
  await page.evaluate(() => window.Alpine.$data(document.body).switchTemplate());
  await page.waitForFunction(() => document.body.innerText.includes('CJ-SL-20260623-1234'), null, { timeout: 20000 });
  await page.waitForTimeout(600);
  await capture(page, '02-工作台-示例数据');

  // ---- 分享弹窗（打开时是空表单，还没有随机 id）----
  await page.getByTitle('一键生成分享二维码，业主扫码即看').click();
  await page.waitForFunction(() => window.Alpine.$data(document.body).shareDialogOpen);
  await page.waitForTimeout(500);
  await capture(page, '03-分享弹窗');
  await page.evaluate(() => { window.Alpine.$data(document.body).shareDialogOpen = false; });

  // ---- 分享管理（需要后端有一条已发布分享，见 test_browser_server.py 的 fixture）----
  await page.getByTitle('查看已分享清单、查看次数、作废链接').click();
  await page.waitForFunction(() => {
    const d = window.Alpine.$data(document.body);
    return d && d.shareManageOpen && !d.shareListLoading && d.shareList.length > 0;
  });
  await page.waitForTimeout(500);
  await capture(page, '04-分享管理');
  await page.evaluate(() => { window.Alpine.$data(document.body).shareManageOpen = false; });

  // ---- 地址管理（一址一码）----
  await page.getByTitle('一址一码：一个地址一张二维码，业主扫码看该户全部阶段归档').click();
  await page.getByText('甲地址 1栋101').first().waitFor();
  await page.waitForTimeout(500);
  await capture(page, '05-地址面板');
  await page.evaluate(() => { window.Alpine.$data(document.body).addressPanel = false; });

  // ---- 账号与公司设置 ----
  await page.getByTitle('账号与公司设置').click();
  await page.waitForFunction(() => window.Alpine.$data(document.body).showSettings);
  await page.waitForTimeout(500);
  await capture(page, '06-账号设置');
  await page.evaluate(() => { window.Alpine.$data(document.body).showSettings = false; });

  // ---- 业主侧两个公开页（模板来自后端 views.py，本次不动，但必须一起守住）----
  const pubId = process.env.VISUAL_PUB_ID;
  const addressId = process.env.VISUAL_ADDRESS_ID;
  const owner = await context.newPage();
  owner.on('pageerror', (e) => errors.push(e.message));
  if (pubId) {
    const resp = await owner.goto(`${base}/s/${pubId}`);
    if (process.env.VISUAL_DEBUG === '1') console.log('DEBUG /s/', pubId, resp.status());
    // 正文在 iframe 里，body.innerText 读不到它 —— 只能等 iframe 自己加载完
    await owner.waitForSelector('iframe', { timeout: 15000 });
    await owner.waitForLoadState('load');
    await owner.waitForTimeout(1500);
    await capture(owner, '07-业主分享页');
  }
  if (addressId) {
    await owner.goto(`${base}/a/${addressId}`);
    // 一址一码页是 JS 拉数据渲染的，等真正有内容
    await owner.waitForFunction(() => document.body.innerText.length > 20, null, { timeout: 20000 });
    await owner.waitForTimeout(1200);
    await capture(owner, '08-一址一码页');
  }

  await browser.close();

  // ---- 对比 / 写基线 ----
  const missing = [];
  const changed = [];
  fs.mkdirSync(BASELINE_DIR, { recursive: true });
  for (const name of VIEWS) {
    const current = path.join(out, name + '.png');
    const baseline = path.join(BASELINE_DIR, name + '.png');
    if (!fs.existsSync(current)) { missing.push(name); continue; }
    if (UPDATE || !fs.existsSync(baseline)) {
      fs.copyFileSync(current, baseline);
      console.log(`${UPDATE ? '基线已更新' : '基线缺失，已写入'}: ${name}`);
      continue;
    }
    const { diff, ratio, note } = diffPixels(baseline, current);
    if (diff === 0) { console.log(`✓ ${name} 逐像素一致`); continue; }
    changed.push({ name, diff, ratio, note });
    console.log(`✗ ${name} 差异 ${diff} px（${(ratio * 100).toFixed(3)}%）${note}`);
  }

  assert.deepEqual(errors, [], '页面抛出异常：\n' + errors.join('\n'));
  assert.deepEqual(missing, [], '这些视图没有截到图：' + missing.join('、'));
  const bad = changed.filter((c) => c.ratio > MAX_DIFF_RATIO);
  assert.deepEqual(bad.map((c) => c.name), [], '这些视图与基线不一致（若是有意改动，用 VISUAL_UPDATE=1 刷新基线）：'
    + bad.map((c) => `${c.name}(${c.diff}px)`).join('、'));

  console.log('\n通过：8 个视图渲染无异常' + (UPDATE ? '（本次为写基线）' : '，与基线一致') + '。');
})().catch((e) => { console.error(e); process.exit(1); });
