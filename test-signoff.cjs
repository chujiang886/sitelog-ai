'use strict';
// =====================================================================
// 客户签认（signoff v1）员工侧 —— 真实浏览器 + 真实后端 一体化回归
// =====================================================================
//
// 【这个脚本和后端脚手架怎么配合】
// 由 `chujiang-sitelog-share/test_browser_server.py --script test-signoff.cjs --wsgi` 拉起：
//   · 后端建临时库、种好「管理员 + 甲地址 1栋101 / 客户甲 + 一条已发布的框架施工留档」；
//   · 前端静态文件挂在 /sitelog/ 下；
//   · 端口随机分配，通过环境变量 TEST_BASE 传进来（**脚本内不得硬编码端口**）。
// 本脚本只读 TEST_BASE / TEST_OUTPUT，其余一律从界面上找（不写死地址 id）。
//
// 【为什么单测不够、必须再来这一层】
// test-signoff-client.cjs 是 vm 沙箱 + 打桩 fetch 的单测，它证明的是
// 「前端按契约拼了正确的请求、状态机分支对」。它**证明不了**下面这几件事：
//   · 真实后端返回的字段，界面是不是真的渲染得出来（字段名对不上时单测照样绿）；
//   · 画到 canvas 上的二维码，扫出来到底是不是后端那个 url；
//   · 真实 409 的后端文案，有没有被前端改成自己的话术；
//   · 切地址时会不会闪出上一户的签认记录（肉眼分辨不出，只有脚本抓得到）。
// 这一层就补这几个缺口，并且刻意走 --wsgi（Flask + Waitress，生产路径）：
// stdlib 服务器和 WSGI 在请求体处理上不是同一条代码路径。
//
// 【六条覆盖】
//   1 登录 → 打开地址详情 → 签认入口可见，且挂在**每一条留档**上（不是阶段分组头）
//   2 生成令牌 → 二维码出现，且二维码编码的字符串 == 后端返回的 url（不是前端拼的）
//   3 倒计时在走；到 0 面板**不自动关闭**，显示「链接已失效，请重新生成」
//   4 撤回原因不足 2 字**不发请求**（驱动真实 DOM）；满足下限才真发
//   5 切地址时签认记录清空（MutationObserver 抓「A 户记录出现在 B 户详情里」的那一帧）
//   6 法律文案：界面出现「客户已确认」可以，出现「具有法律效力」失败
//
// 【两条容易踩的坑，脚本里都写成了断言】
//   · stale 的语义：员工侧「签认后档案又换过版」，文案要说「业主签的那一版已被替换」，
//     不能说「已过期」（链接过期是另一回事，见第 3 条）。这里断言 stale 行**不含**「过期」。
//   · 409 文案是「此**范围**已签认」（粒度 kind+stage_key+slot），前端必须原样透出。

const { chromium } = require('playwright');
const { PNG } = require('pngjs');
const jsQR = require('jsqr');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const base = process.env.TEST_BASE;
const out = process.env.TEST_OUTPUT;
// 只连本机临时后端。写死「只允许 127.0.0.1」是防止误配到生产（脚手架本来就是临时库，
// 但环境变量是唯一的输入口，多一道闸不亏）。
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw Error('仅允许隔离测试');
if (!out) throw Error('缺少 TEST_OUTPUT');

const REPORT = path.join(out, '客户签认员工侧一体化回归.json');
const report = { script: 'test-signoff.cjs', mode: '待探测', base, passed: false, steps: [], observations: {}, errors: [] };

let browser = null;
const steps = [];
const obs = {};

const uid = () => randomUUID().replace(/-/g, '');
const js = (page, expr) => page.evaluate(expr);
// 员工接口：走页面自己的 accountJSON（自动带 CSRF / 同源 cookie），不另起一套请求层。
const api = (page, url, body) => page.evaluate(({ url, body }) => Alpine.$data(document.body).accountJSON(url, body), { url, body });

async function login(page) {
  await page.goto(base + '/sitelog/');
  await page.locator('#login-user').fill('admin');
  await page.locator('#login-pass').fill('Test-admin-initial-12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForFunction(() => { const a = window.Alpine && Alpine.$data(document.body); return a?.draftOwner && !a.draftHydrating; }, null, { timeout: 20000 });
}

function clearToast(page) { return js(page, 'Alpine.$data(document.body).toast = { show: false, msg: "", type: "info" }'); }
function toastMsg(page) { return js(page, 'Alpine.$data(document.body).toast.msg'); }
async function waitToast(page) {
  await page.waitForFunction(() => { const a = Alpine.$data(document.body); return a.toast && a.toast.show && !!a.toast.msg; }, null, { timeout: 10000 });
  return toastMsg(page);
}

// 打开地址管理面板（幂等：已经开着就不再点一次，否则会把面板关掉）。
async function openAddressPanel(page) {
  if (!(await page.locator('.addr-panel-head').isVisible().catch(() => false))) {
    await page.locator('button[title*="一址一码"]').click();
  }
  await page.locator('.addr-item').first().waitFor({ state: 'visible', timeout: 15000 });
}

// 打开某个地址的详情。addressLabel 用界面上的文字定位，不写死 id。
//
// 【为什么要先点「返回地址列表」】
// 地址列表和地址详情是互斥渲染的（列表外面套着 `x-if="!addressDetail"`）。
// 详情开着的时候，列表根本不在 DOM 里——此时去找某一户的行必然超时。
// 所以顺序必须是：先退回列表 → 等列表渲染出来 → 再点那一户的「管理」。
async function openAddressDetail(page, addressLabel) {
  const back = page.getByRole('button', { name: '← 返回地址列表' });
  if (await back.isVisible().catch(() => false)) await back.click();
  await page.locator('.addr-item').first().waitFor({ state: 'visible', timeout: 15000 });
  const row = page.locator('.addr-item', { hasText: addressLabel });
  await row.first().waitFor({ state: 'visible', timeout: 15000 });
  await row.first().getByRole('button', { name: '管理', exact: true }).click();
  await page.getByText('客户签认记录').first().waitFor({ state: 'visible', timeout: 15000 });
}

// 签认区的「刷新」按钮。
//
// 【为什么不直接 getByRole('button', { name: '刷新' })】
// 地址详情里**不止一个「刷新」**：隐蔽工程验收区（hiddenwork v1）也有一个同样文案的
// `.addr-group-add` 按钮，而且它在 DOM 里排在签认区**之前**。全局定位会命中两个元素，
// Playwright 严格模式直接报 `strict mode violation` —— 脚本挂在一个与签认无关的地方。
// 所以这里按「签认区自己的标题」把范围收窄：`.addr-stage-head` 里含「客户签认记录」的那一个。
// （阶段列表的分组头也用 `.addr-stage-head`，但它们不含这段文字。）
const signoffRefresh = (page) => page
  .locator('.addr-stage-head', { hasText: '客户签认记录' })
  .getByRole('button', { name: '刷新', exact: true });

// 画一张「手写签名」PNG，当作业主提交的笔迹。
// 体积必须落在后端 STROKE_MIN_BYTES..STROKE_MAX_BYTES（512..262144）之间，
// 且首块 IHDR、以 IEND 结尾——pngjs 的输出天然满足结构校验。
function strokeDataUrl() {
  const w = 320, h = 160;
  const png = new PNG({ width: w, height: h });
  for (let i = 0; i < png.data.length; i += 4) { png.data[i] = 255; png.data[i + 1] = 255; png.data[i + 2] = 255; png.data[i + 3] = 255; }
  const plot = (x, y, r) => {
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      if (dx * dx + dy * dy > r * r) continue;
      const px = Math.round(x + dx), py = Math.round(y + dy);
      if (px < 0 || py < 0 || px >= w || py >= h) continue;
      const i = (py * w + px) << 2;
      png.data[i] = 24; png.data[i + 1] = 36; png.data[i + 2] = 30; png.data[i + 3] = 255;
    }
  };
  // 几笔正弦折线，模拟手写签名（同时保证 PNG 不至于小到 512 字节以下）。
  for (let t = 0; t <= 220; t++) {
    const x = 34 + t * 1.15;
    const y = 88 + Math.sin(t / 9) * 40 + Math.sin(t / 3.1) * 8;
    plot(x, y, 2);
  }
  for (let t = 0; t <= 60; t++) plot(46 + t * 3.4, 128 - t * 0.9, 2);
  const buf = PNG.sync.write(png);
  return { url: 'data:image/png;base64,' + buf.toString('base64'), bytes: buf.length };
}

// 业主侧提交签认。业主没有账号，走一次性令牌端点；Origin 由浏览器自动带上（同源 POST）。
async function ownerSign(page, token, stroke) {
  return page.evaluate(async ({ token, stroke }) => {
    const r = await fetch('/api/signoff/' + token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signer_name: '张三', signer_phone: '13800138000', stroke }),
    });
    let body = null;
    try { body = await r.json(); } catch (e) { body = null; }
    return { status: r.status, body };
  }, { token, stroke });
}

// 发布一版新的公开档案并挂到地址上，返回落点。
// slot 省略 = 追加一次留档（`_slot_or_auto` 自动分配，永不覆盖）；
// slot 给整数 = 落到指定槽位（同槽位已有留档时是「换版」，这正是 stale 的触发条件）。
async function publishVersion(page, aid, { stageKey, slot, report }) {
  const list = await api(page, '/projects?q=&page=1');
  const project = (list.items || []).find((p) => p.title === '客户甲') || (list.items || [])[0];
  if (!project) throw new Error('找不到脚手架种下的工程「客户甲」');
  const body = {
    format: 'sitelog-project', schema: 1,
    meta: { projectName: '客户甲', templateType: '框架施工' },
    report, css: '',
    images: [], arrivalImages: [], finishImages: [], sopImages: [],
  };
  const saved = await api(page, '/projects/' + project.id + '/draft', { revision: project.revision, body });
  const rev = saved.revision;
  await api(page, '/projects/' + project.id + '/review', { revision: rev, decision: 'submit' });
  await api(page, '/projects/' + project.id + '/review', { revision: rev, decision: 'approve' });
  const pub = await api(page, '/projects/' + project.id + '/publish', { revision: rev, idempotency: uid(), audience: 'public', html: report });
  const payload = { stage_key: stageKey, publication_id: pub.id };
  if (slot !== undefined) payload.slot = slot;
  const attached = await api(page, '/addresses/' + aid + '/attach', payload);
  return { publication: pub.id, slot: attached.attached && attached.attached.slot };
}

// 让「框架施工」这个阶段下出现第二条留档（slot 1）。
// 签认粒度是 (kind, stage_key, slot)——一个阶段来两次就该有两条互不覆盖的签认。
// 只有一条留档时，「入口挂在每条留档上」这句话证明力不足，所以造第二条。
// 这是**尽力而为**的增强：拿不到就退回单条留档，不影响其余断言（会在报告里说明）。
async function ensureSecondRecord(page, aid) {
  return publishVersion(page, aid, { stageKey: '框架施工', report: '<p>框架施工归档正文（第二次上门补档）</p>' });
}

(async () => {
  // --channel=chrome：本机已装 Chrome，不下载 Chromium（CI 上也没有捆绑浏览器）。
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e.stack || e.message || e)));
  page.on('dialog', (d) => d.accept());

  // 记录所有撤回请求，用来证明「不足 2 字时一个请求都没发出去」。
  const revokeRequests = [];
  page.on('request', (r) => {
    try { if (/\/api\/share\/signoffs\/[a-f0-9]{32}\/revoke$/.test(new URL(r.url()).pathname)) revokeRequests.push(r.url()); } catch (e) { /* data: 等非 URL 请求忽略 */ }
  });

  await login(page);
  steps.push('登录成功（admin，must_change_password=0）');

  // 确认自己跑在 WSGI(Waitress) 上。这不是洁癖：stdlib 服务器和 WSGI 在请求体处理上
  // 不是同一条代码路径，而这一层存在的意义就是覆盖生产那条路径。用 `Server` 响应头判定
  // （Waitress 自报 `waitress`，stdlib 自报 `BaseHTTP/...`），跑错路径就直接失败。
  const serverHeader = (await (await fetch(base + '/sitelog/index.html')).headers.get('server') || '').toLowerCase();
  report.mode = serverHeader.includes('waitress') ? 'wsgi(Flask+Waitress)' : '非 WSGI（Server: ' + serverHeader + '）';
  obs.serverHeader = serverHeader;
  assert.ok(serverHeader.includes('waitress'), '当前不是 WSGI(Waitress) 路径（Server: ' + serverHeader + '）——必须带 --wsgi 跑，否则覆盖不到生产路径');

  // ---------- 准备：造第二条留档 ----------
  await openAddressPanel(page);
  await openAddressDetail(page, '甲地址 1栋101');
  const addressId = await js(page, 'Alpine.$data(document.body).addressDetail.id');
  assert.match(addressId, /^[a-f0-9]{32}$/, '地址 id 形态不对');
  obs.addressId = addressId;

  let secondRecord = null;
  try {
    secondRecord = await ensureSecondRecord(page, addressId);
    steps.push('已造第二条留档（框架施工 slot ' + secondRecord.slot + '）');
  } catch (e) {
    obs.secondRecordError = e.message;
    steps.push('第二条留档未造出（降级为单条留档）：' + e.message);
  }
  // 重新打开详情，让界面拿到最新的留档清单。
  await openAddressDetail(page, '甲地址 1栋101');

  // =====================================================================
  // 1) 签认入口挂在每一条留档上，不是阶段分组头
  // =====================================================================
  const recordCount = await page.locator('.addr-stage').count();
  const entryTotal = await page.locator('.signoff-invite-btn').count();
  const entryInRows = await page.locator('.addr-stage .signoff-invite-btn').count();
  const entryInHeads = await page.locator('.addr-stage-head .signoff-invite-btn').count();
  // 注意：`客户签认记录` 那个区块的标题也复用了 `.addr-stage-head` 这个类，
  // 所以「阶段分组头有几个」不能数 `.addr-stage-head`，要数只属于阶段列表的 `.addr-stage-rows`。
  const groupHeads = await page.locator('.addr-stage-rows').count();
  obs.entryPlacement = { recordCount, entryTotal, entryInRows, entryInHeads, groupHeads };
  assert.ok(recordCount >= 1, '地址详情里一条留档都没有，脚手架没种上');
  assert.equal(entryInHeads, 0, '签认入口出现在了阶段分组头上——粒度错了，分组头指不出是第几次留档');
  assert.equal(entryTotal, recordCount, '签认入口数量与留档数量不一致（应每条留档一个）');
  assert.equal(entryInRows, entryTotal, '有签认入口不在留档行内');
  await page.locator('.addr-stage .signoff-invite-btn').first().waitFor({ state: 'visible', timeout: 10000 });
  if (secondRecord) {
    assert.equal(recordCount, 2, '造了第二条留档，但详情里只看到 ' + recordCount + ' 条');
    assert.equal(groupHeads, 1, '两条留档应归在同一个阶段分组下');
    steps.push('入口位置：' + recordCount + ' 条留档各一个入口，阶段分组头 0 个（分组头 ' + groupHeads + ' 个）');
  } else {
    steps.push('入口位置：' + recordCount + ' 条留档各一个入口，阶段分组头 0 个');
  }

  // =====================================================================
  // 2) 生成令牌 → 二维码编码的字符串 == 后端返回的 url
  // =====================================================================
  const [tokenResp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/signoff-token') && r.request().method() === 'POST', { timeout: 15000 }),
    page.locator('.addr-stage-head:has-text("框架归档记录") + .addr-stage-rows .addr-stage .signoff-invite-btn').first().click(),
  ]);
  assert.equal(tokenResp.status(), 201, '签发令牌没有返回 201');
  const tokenPayload = await tokenResp.json();
  obs.tokenResponse = { kind: tokenPayload.kind, stage_key: tokenPayload.stage_key, slot: tokenPayload.slot, label: tokenPayload.label, url: tokenPayload.url, tokenLen: (tokenPayload.token || '').length };

  await page.locator('.signoff-mask').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => {
    const c = document.getElementById('signoff-qr-canvas');
    if (!c || !c.width) return false;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let dark = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] < 128) dark++;
    return dark > 500;
  }, null, { timeout: 10000 });

  const qrDataUrl = await js(page, 'document.getElementById("signoff-qr-canvas").toDataURL("image/png")');
  const qrPng = PNG.sync.read(Buffer.from(qrDataUrl.split(',')[1], 'base64'));
  const decoded = jsQR(new Uint8ClampedArray(qrPng.data), qrPng.width, qrPng.height);
  assert.ok(decoded, '二维码画出来了但扫不出内容（jsQR 解码失败）');
  const linkValue = await page.locator('.signoff-link').inputValue();
  obs.qr = { decoded: decoded.data, linkInput: linkValue, backendUrl: tokenPayload.url };
  assert.equal(decoded.data, tokenPayload.url, '二维码编码的字符串与后端返回的 url 不一致');
  assert.equal(linkValue, tokenPayload.url, '链接框里的值不是后端返回的 url');
  assert.ok(tokenPayload.url.startsWith(base + '/sign/'), '后端 url 不以 <base>/sign/ 开头：' + tokenPayload.url);
  assert.equal(obs.tokenResponse.label, '框架归档记录', '后端返回的 label 不是阶段显示名');
  steps.push('令牌 + 二维码：扫码结果 == 后端 url == 链接框（' + tokenPayload.url + '）');

  // =====================================================================
  // 3) 倒计时在走；到 0 面板不自动关闭，显示「已失效，请重新生成」
  // =====================================================================
  const countdown1 = await page.locator('.signoff-countdown').innerText();
  assert.match(countdown1, /^链接 \d\d:\d\d 后失效$/, '倒计时文案形态不对：' + countdown1);
  const sec1 = Number(countdown1.slice(3, 5)) * 60 + Number(countdown1.slice(6, 8));
  await page.waitForTimeout(2200);
  const countdown2 = await page.locator('.signoff-countdown').innerText();
  const sec2 = Number(countdown2.slice(3, 5)) * 60 + Number(countdown2.slice(6, 8));
  obs.countdown = { first: countdown1, second: countdown2 };
  assert.ok(sec2 < sec1, '倒计时没有推进：' + countdown1 + ' → ' + countdown2);

  // 等 300 秒不现实，把「过期时刻」拨到 1 秒后——但倒计时仍由**页面自己的定时器**逐秒推进，
  // DOM 的失效切换是真实发生的，不是脚本替它切。
  const token = await js(page, 'Alpine.$data(document.body).signoffToken');
  assert.ok(token && token.length >= 20, '面板里没有拿到明文令牌');
  await js(page, 'Alpine.$data(document.body).signoffExpires = Math.floor(Date.now() / 1000) + 1');
  await page.locator('.signoff-expired').waitFor({ state: 'visible', timeout: 10000 });
  const expiredText = await page.locator('.signoff-expired').innerText();
  const panelStillOpen = await page.locator('.signoff-mask').isVisible();
  const panelFlag = await js(page, 'Alpine.$data(document.body).signoffPanelOpen');
  obs.expiry = { expiredText: expiredText.split('\n')[0], panelStillOpen, panelFlag };
  assert.ok(panelStillOpen && panelFlag === true, '倒计时到 0 后面板被自动关掉了（员工会以为二维码已递出去）');
  assert.ok(expiredText.includes('链接已失效，请重新生成'), '失效文案不对：' + expiredText);
  assert.ok(await page.locator('.signoff-expired button:has-text("重新生成签认链接")').isVisible(), '失效态没有给「重新生成」的出口');
  steps.push('倒计时：' + countdown1 + ' → ' + countdown2 + '；到 0 后面板保持打开并提示「链接已失效，请重新生成」');

  await page.locator('.signoff-card button[aria-label="关闭签认面板"]').click();
  await page.locator('.signoff-mask').waitFor({ state: 'hidden', timeout: 5000 });

  // =====================================================================
  // 6-预) 法律文案（先做，因为要开面板看到那句「客户已确认」）
  // =====================================================================
  // 面板已关，这里直接扫「渲染后的可见文本」+ 源文件。
  const bodyText = await js(page, 'document.body.innerText');
  const srcHtml = await (await fetch(base + '/sitelog/index.html')).text();
  const srcJs = await (await fetch(base + '/sitelog/address-client.js')).text();
  obs.legal = { bodyHasConfirmed: bodyText.includes('客户已确认'), forbiddenInBody: /法律效力|可靠电子签名/.test(bodyText), forbiddenInSrc: /法律效力|可靠电子签名/.test(srcHtml) || /法律效力|可靠电子签名/.test(srcJs) };
  assert.ok(!obs.legal.forbiddenInBody, '界面上出现了「具有法律效力 / 可靠电子签名」这类超出「客户已确认」的承诺');
  assert.ok(!obs.legal.forbiddenInSrc, '前端源码里出现了「具有法律效力 / 可靠电子签名」');

  // =====================================================================
  // 4-预) 造出真实的签认记录（业主侧提交）
  // =====================================================================
  const stroke = strokeDataUrl();
  obs.strokeBytes = stroke.bytes;
  assert.ok(stroke.bytes >= 512 && stroke.bytes <= 262144, '测试笔迹图体积不合规：' + stroke.bytes);
  const signed = await ownerSign(page, token, stroke.url);
  obs.ownerSign = { status: signed.status, kind: signed.body && signed.body.kind };
  assert.equal(signed.status, 201, '业主提交签认失败：' + JSON.stringify(signed.body));

  await signoffRefresh(page).click();
  await page.locator('.signoff-row').first().waitFor({ state: 'visible', timeout: 10000 });
  let rows = await js(page, 'Alpine.$data(document.body).signoffItems');
  assert.equal(rows.length, 1, '刷新后应看到 1 条签认记录，实际 ' + rows.length);
  assert.equal(rows[0].kind, 'stage', '第一条记录的 kind 不对');
  assert.equal(rows[0].stage_label, '框架归档记录', '第一条记录的 stage_label 不对：' + rows[0].stage_label);
  assert.equal(rows[0].signer_name, '张三', '签字人姓名不对');
  assert.equal(rows[0].signer_phone, '13800138000', '签字人手机号不对');
  assert.equal(rows[0].has_stroke, true, '后端说有笔迹但 has_stroke=false');
  assert.equal(rows[0].stale, false, '刚签完就 stale 了（冻结清单与当前内容应当一致）');
  const thumbCount = await page.locator('.signoff-row img.signoff-thumb').count();
  assert.equal(thumbCount, 1, '笔迹缩略图没渲染出来（<img> 数量 ' + thumbCount + '）');
  const thumbLoaded = await js(page, '(function(){const i=document.querySelector(".signoff-row img.signoff-thumb");return i?i.naturalWidth:0})()');
  assert.ok(thumbLoaded > 0, '笔迹缩略图请求失败（naturalWidth=0，可能 404/403）');
  obs.firstRecord = { stage_label: rows[0].stage_label, signer_name: rows[0].signer_name, has_stroke: rows[0].has_stroke, stale: rows[0].stale, thumbNaturalWidth: thumbLoaded };
  steps.push('业主签认落库并渲染：' + rows[0].stage_label + ' / ' + rows[0].signer_name + ' / 笔迹缩略图 naturalWidth=' + thumbLoaded);

  // 再造一条「整址竣工验收」签认，让记录区同时有 stage 与 final 两种范围。
  const finalToken = await api(page, '/addresses/' + addressId + '/signoff-token', { kind: 'final', stage_key: '', slot: 0 });
  const finalSigned = await ownerSign(page, finalToken.token, stroke.url);
  assert.equal(finalSigned.status, 201, '整址竣工验收签认提交失败：' + JSON.stringify(finalSigned.body));
  await signoffRefresh(page).click();
  await page.waitForFunction(() => Alpine.$data(document.body).signoffItems.length === 2, null, { timeout: 10000 });
  rows = await js(page, 'Alpine.$data(document.body).signoffItems');
  const finalRow = rows.find((r) => r.kind === 'final');
  assert.ok(finalRow, '记录区里没有整址竣工验收那一条');
  assert.equal(finalRow.stage_label, '整址竣工验收签认', 'final 的范围名不是后端的 FINAL_LABEL：' + finalRow.stage_label);
  obs.finalRecord = { stage_label: finalRow.stage_label, stale: finalRow.stale };
  steps.push('记录区两种范围都在：框架归档记录 + ' + finalRow.stage_label);

  // =====================================================================
  // 4-预a) 真实 stale：把 slot 0 换成新一版 → 原来那份签认必须被标成「已被替换」
  // =====================================================================
  // 这是团队特别点名的坑：stale 说的是「业主签的那一版已经被换掉了」，
  // 不是「链接过期」（那是另一回事，见第 3 条）。所以文案里不能出现「过期」。
  await publishVersion(page, addressId, { stageKey: '框架施工', slot: 0, report: '<p>框架施工归档正文（整改后重新归档）</p>' });
  await signoffRefresh(page).click();
  await page.waitForFunction(() => Alpine.$data(document.body).signoffItems.some((r) => r.stale), null, { timeout: 10000 });
  rows = await js(page, 'Alpine.$data(document.body).signoffItems');
  const staleRow = rows.find((r) => r.stale && !r.revoked);
  assert.ok(staleRow, '换版后原签认没有变成 stale');
  const staleText = await page.locator('.signoff-row', { hasText: '框架归档记录' }).locator('.signoff-stale').innerText();
  obs.stale = { stale: staleRow.stale, copy: staleText };
  assert.ok(!/过期/.test(staleText), 'stale 文案说成了「过期」——链接过期与档案被替换是两回事：' + staleText);
  assert.ok(/更新|替换|不是当前/.test(staleText), 'stale 文案没说清「业主签的那一版已被替换」：' + staleText);
  steps.push('stale：换版后原签认被标记（文案「' + staleText + '」）');

  // =====================================================================
  // 4-预b) 真实 409：同一范围再次发起签认，前端必须原样透出后端文案
  // =====================================================================
  await clearToast(page);
  await page.locator('.addr-stage-head:has-text("框架归档记录") + .addr-stage-rows .addr-stage .signoff-invite-btn').first().click();
  const conflictMsg = await waitToast(page);
  obs.conflict = { message: conflictMsg };
  assert.ok(conflictMsg.includes('此范围已签认'), '409 文案没透出后端原话：' + conflictMsg);
  assert.ok(!conflictMsg.includes('此阶段已签认'), '前端把「此范围」改写成了「此阶段」——粒度被说错了');
  assert.ok(conflictMsg.includes('撤回'), '409 文案缺少「先撤回」的下一步指引');
  assert.ok(!(await page.locator('.signoff-mask').isVisible()), '409 之后不该弹出二维码面板');
  steps.push('409 原样透出：' + conflictMsg);

  // =====================================================================
  // 4) 撤回原因不足 2 字不发请求（驱动真实 DOM）
  // =====================================================================
  const stageRow = page.locator('.signoff-row', { hasText: '框架归档记录' });
  await stageRow.getByRole('button', { name: '撤回', exact: true }).click();
  await page.locator('.signoff-revoke-form').waitFor({ state: 'visible', timeout: 10000 });

  const revokeBefore = revokeRequests.length;
  await page.locator('.signoff-revoke-form textarea').fill('错');   // 1 字 < 下限 2
  await clearToast(page);
  await page.getByRole('button', { name: '确认撤回', exact: true }).click();
  const shortMsg = await waitToast(page);
  await page.waitForTimeout(400);
  obs.revokeGuard = { reason: '错', requestsBefore: revokeBefore, requestsAfter: revokeRequests.length, message: shortMsg };
  assert.equal(revokeRequests.length, revokeBefore, '撤回原因不足 2 字却发出了请求');
  assert.ok(/撤回原因/.test(shortMsg) && /2/.test(shortMsg), '不足下限时的提示不对：' + shortMsg);
  assert.ok(await page.locator('.signoff-revoke-form').isVisible(), '被挡下后不该收起撤回表单');

  // 满足下限 → 真的发出去（证明上面的守卫不是「永远不发」）
  await page.locator('.signoff-revoke-form textarea').fill('业主反映漏拍了厨房推拉门');
  await clearToast(page);
  await page.getByRole('button', { name: '确认撤回', exact: true }).click();
  await page.waitForFunction(() => !Alpine.$data(document.body).signoffRevokeBusy, null, { timeout: 10000 });
  await page.waitForTimeout(600);
  obs.revokeOk = { requestsAfter: revokeRequests.length, sent: revokeRequests.length > revokeBefore };
  assert.ok(revokeRequests.length > revokeBefore, '满足下限后撤回请求没发出去');
  assert.ok(!(await page.locator('.signoff-revoke-form').isVisible()), '撤回成功后表单没有收起');
  rows = await js(page, 'Alpine.$data(document.body).signoffItems');
  const revokedRow = rows.find((r) => r.kind === 'stage');
  assert.equal(revokedRow.revoked, true, '撤回后该条没有置为已撤回');
  assert.equal(revokedRow.revoke_note, '业主反映漏拍了厨房推拉门', '撤回原因没落库');
  assert.ok(await page.locator('.signoff-row.revoked').first().isVisible(), '已撤回的行没有置灰');
  assert.ok((await page.locator('.signoff-row.revoked').first().innerText()).includes('已撤回'), '已撤回的行没有「已撤回」字样');
  steps.push('撤回守卫：1 字不发请求（提示：' + shortMsg + '）；≥2 字发请求并落库');

  // =====================================================================
  // 5) 切地址时签认记录清空（抓「A 户记录出现在 B 户详情里」的那一帧）
  // =====================================================================
  // 造一个没有任何签认记录的 B 户。
  const allStages = await js(page, 'Alpine.$data(document.body).ADDRESS_STAGE_KEYS');
  const addrB = await api(page, '/addresses', { label: '乙地址 2栋202', client_name: '客户乙', note: '', enabled_stages: allStages });
  const bId = addrB.id;
  assert.match(bId, /^[a-f0-9]{32}$/, 'B 户地址 id 形态不对');
  // 列表是在建 B 之前拉的，不刷新的话界面上根本没有 B 这一行。
  // 注意要在**详情还开着**的时候刷：列表只在详情关闭后才渲染，数据先备好，退回列表就能看到 B。
  await js(page, 'Alpine.$data(document.body).loadAddresses()');

  // 装一个监视器：只要「当前详情是 B 户」且 DOM 里还存在 .signoff-row，就记一次泄漏。
  // MutationObserver 覆盖每一次会改变画面的 DOM 变更，所以任何**被渲染出来**的
  // 「B 户详情里显示 A 户签认记录」都会被抓到，哪怕只存在一帧。
  await js(page, `(function(){
    window.__signoffLeaks = [];
    const bid = ${JSON.stringify(bId)};
    const check = () => {
      try {
        const a = window.Alpine && Alpine.$data(document.body);
        if (!a || !a.addressDetail || a.addressDetail.id !== bid) return;
        const rows = document.querySelectorAll('.signoff-row').length;
        const items = (a.signoffItems || []).length;
        if (rows > 0 || items > 0) window.__signoffLeaks.push({ rows, items, at: Date.now() });
      } catch (e) {}
    };
    window.__signoffLeakObserver && window.__signoffLeakObserver.disconnect();
    window.__signoffLeakObserver = new MutationObserver(check);
    window.__signoffLeakObserver.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
    check();
  })()`);

  const rowsAtA = await page.locator('.signoff-row').count();
  assert.ok(rowsAtA > 0, 'A 户应当有签认记录（' + rowsAtA + '）');

  await openAddressDetail(page, '乙地址 2栋202');
  // 等 B 户彻底打开、且这一轮签认记录请求已经落地，再做判定。
  await page.waitForFunction((bid) => {
    const a = window.Alpine && Alpine.$data(document.body);
    return !!a && !!a.addressDetail && a.addressDetail.id === bid && !a.signoffLoading;
  }, bId, { timeout: 10000 });
  const bItems = await js(page, 'Alpine.$data(document.body).signoffItems.length');
  const bRows = await page.locator('.signoff-row').count();
  // 空态要「等」不要「快照」：三态是 loading → empty，中间必然有一小段
  // 「正在读取签认记录…」（这正是三态存在的意义），取瞬间快照会拍到还没切过去的那一帧。
  // 所以这里等它出现（有界超时），而不是断言某一瞬间的 display。
  const bEmpty = await page.waitForFunction(() => {
    const p = [...document.querySelectorAll('p')].find((x) => x.textContent.includes('还没有客户签认记录'));
    return !!p && !!(p.offsetWidth || p.offsetHeight || p.getClientRects().length);
  }, null, { timeout: 5000 }).then(() => true).catch(() => false);
  const bError = await js(page, 'Alpine.$data(document.body).signoffError');
  obs.switchToB = { signoffItems: bItems, rows: bRows, emptyStateVisible: bEmpty, signoffError: bError };
  assert.equal(bItems, 0, 'B 户的签认记录没清空（signoffItems=' + bItems + '）');
  assert.equal(bRows, 0, 'B 户详情里出现了签认记录行（' + bRows + ' 行）');
  assert.ok(bEmpty, 'B 户没有显示「还没有客户签认记录」空态');

  await openAddressDetail(page, '甲地址 1栋101');
  await page.waitForFunction(() => !Alpine.$data(document.body).signoffLoading, null, { timeout: 10000 });
  const aItemsBack = await js(page, 'Alpine.$data(document.body).signoffItems.length');
  assert.ok(aItemsBack > 0, '切回 A 户后签认记录没回来（' + aItemsBack + '）');

  const leaks = await js(page, 'window.__signoffLeaks');
  obs.leaks = leaks;
  assert.deepEqual(leaks, [], '切地址期间出现过「B 户详情里显示签认记录」的帧：' + JSON.stringify(leaks));
  steps.push('切地址：B 户 ' + bRows + ' 行 / 空态可见；切回 A 户 ' + aItemsBack + ' 条；泄漏帧 ' + leaks.length);

  // =====================================================================
  // 6) 法律文案（面板开着时再确认一次「客户已确认」在界面上）
  // =====================================================================
  await page.locator('.addr-stage-head:has-text("框架归档记录") + .addr-stage-rows .addr-stage .signoff-invite-btn').first().click();
  await page.waitForFunction(() => Alpine.$data(document.body).signoffPanelOpen, null, { timeout: 10000 }).catch(() => {});
  // 上面这次点击可能因 409 不弹面板（该范围已撤回，正常会重新签发）。两种都接受，但文案扫描必须做。
  await page.waitForTimeout(300);
  const panelText = await js(page, 'document.body.innerText');
  obs.legalAfter = { hasConfirmed: panelText.includes('客户已确认'), hasForbidden: /法律效力|可靠电子签名/.test(panelText) };
  assert.ok(!obs.legalAfter.hasForbidden, '界面上出现了「具有法律效力 / 可靠电子签名」');
  assert.ok(panelText.includes('客户已确认'), '界面上找不到「客户已确认」这句合规文案');
  steps.push('法律文案：界面只说「客户已确认」，无「具有法律效力 / 可靠电子签名」');

  // 收尾
  assert.deepEqual(pageErrors, [], '页面存在未捕获 JS 错误：' + JSON.stringify(pageErrors));
  obs.pageErrors = pageErrors;
  await page.screenshot({ path: path.join(out, '客户签认员工侧回归.png'), fullPage: false });

  report.passed = true;
  report.steps = steps;
  report.observations = obs;
  report.errors = pageErrors;
  console.log('通过：客户签认员工侧一体化回归（wsgi）。');
  for (const s of steps) console.log('  · ' + s);
  console.log('观测值：' + JSON.stringify(obs, null, 2));
})().catch(async (e) => {
  report.passed = false;
  report.steps = steps;
  report.observations = obs;
  report.errors.push(String(e && e.message || e));
  console.error('失败：' + (e && e.message || e));
  console.error(e && e.stack ? e.stack : '');
  if (browser) {
    for (const c of browser.contexts()) for (const p of c.pages()) {
      try {
        if (p.url().startsWith(base + '/sitelog')) {
          console.error('页面状态：' + JSON.stringify(await js(p, '(function(){const a=window.Alpine&&Alpine.$data(document.body);if(!a)return null;return {detail:a.addressDetail&&a.addressDetail.id,panel:a.signoffPanelOpen,items:(a.signoffItems||[]).length,toast:a.toast&&a.toast.msg}})()')));
        }
      } catch (e2) { /* 页面已关 */ }
    }
  }
  process.exitCode = 1;
}).finally(async () => {
  try { fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(REPORT, JSON.stringify(report, null, 2)); console.log('报告：' + REPORT); } catch (e) { console.error('报告写入失败：' + e.message); }
  if (browser) await browser.close();
});
