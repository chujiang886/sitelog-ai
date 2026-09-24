'use strict';
// =====================================================================
// 隐蔽工程验收（hiddenwork v1）员工侧 —— 真实浏览器 + 真实后端 冒烟
// =====================================================================
//
// 【它为什么必须进仓库】
// 单测（test-hidden-client.cjs）只跑方法、不跑模板。而本页是 Alpine 模板驱动，
// 「模板在真实 DOM 上求值会不会抛」只有真浏览器能回答——2026-09-24 就在这里
// 抓到过一个真 bug：x-show 藏在 x-for 里、外层列表同轮被整体替换时，Alpine 3
// 会对同一元素重复走一遍隐藏流程并抛未捕获 TypeError。
// 漏掉这一层的代价是「npm test 全绿、线上页面报错」，所以必须由后端脚手架
// （`--script test-hidden.cjs`，后端 CI 第 10 条）拉起来跑。
//
// 【它补的是单测补不了的那几个缺口】
//   · Alpine 表达式在真实 DOM 上求值会不会抛（单测只跑方法，不跑模板）
//   · 后端真实返回的 item.label/hint 到底渲染出来没有
//   · 选「不适用」时理由输入框有没有真的出现、选别的时有没有真的收起
//   · 上传照片后缩略图有没有出来（H3 → 本地追加，不重拉）
//   · 切地址时甲户的照片会不会串到乙户界面上
//
// 用法（由后端脚手架拉起，端口随机，脚本不硬编码端口）：
//   python test_browser_server.py --frontend <前端仓库> --output browser-output/hidden \
//     --script test-hidden.cjs --wsgi

const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(path.join(process.cwd(), 'node_modules', 'playwright'));

const base = process.env.TEST_BASE;
const out = process.env.TEST_OUTPUT;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw Error('仅允许隔离测试');
if (!out) throw Error('缺少 TEST_OUTPUT');

const report = { script: 'test-hidden.cjs（隐蔽工程验收员工侧 · 真实浏览器）', base, passed: false, steps: [], observations: {}, errors: [] };
const obs = {};

// 造一张真图当上传素材。**不读仓库外的文件**：脚本进了仓库，就必须在任何
// checkout 上都能跑。后端接受 PNG，用 pngjs 生成（test-signoff.cjs 已依赖它）。
function makePhotoBytes() {
  const { PNG } = require(path.join(process.cwd(), 'node_modules', 'pngjs'));
  const png = new PNG({ width: 240, height: 180 });
  for (let y = 0; y < png.height; y++) {
    for (let x = 0; x < png.width; x++) {
      const i = (png.width * y + x) << 2;
      png.data[i] = 120 + ((x * 7) % 120);      // R
      png.data[i + 1] = 80 + ((y * 5) % 120);   // G
      png.data[i + 2] = 60 + ((x + y) % 90);    // B
      png.data[i + 3] = 255;
    }
  }
  return PNG.sync.write(png);
}

const js = (page, expr) => page.evaluate(expr);
const toastMsg = (page) => js(page, 'Alpine.$data(document.body).toast.msg');
const clearToast = (page) => js(page, 'Alpine.$data(document.body).toast = { show:false, msg:"", type:"info" }');
async function waitToast(page) {
  await page.waitForFunction(() => { const a = Alpine.$data(document.body); return a.toast && a.toast.show && !!a.toast.msg; }, null, { timeout: 10000 });
  return toastMsg(page);
}

async function login(page) {
  await page.goto(base + '/sitelog/');
  await page.locator('#login-user').fill('admin');
  await page.locator('#login-pass').fill('Test-admin-initial-12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForFunction(() => { const a = window.Alpine && Alpine.$data(document.body); return a?.draftOwner && !a.draftHydrating; }, null, { timeout: 20000 });
}
async function openAddressPanel(page) {
  if (!(await page.locator('.addr-panel-head').isVisible().catch(() => false))) {
    await page.locator('button[title*="一址一码"]').click();
  }
  await page.locator('.addr-item').first().waitFor({ state: 'visible', timeout: 15000 });
}
async function openAddressDetail(page, label) {
  const back = page.getByRole('button', { name: '← 返回地址列表' });
  if (await back.isVisible().catch(() => false)) await back.click();
  await page.locator('.addr-item').first().waitFor({ state: 'visible', timeout: 15000 });
  const row = page.locator('.addr-item', { hasText: label });
  await row.first().waitFor({ state: 'visible', timeout: 15000 });
  await row.first().getByRole('button', { name: '管理', exact: true }).click();
  await page.locator('.addr-stage-head', { hasText: '隐蔽工程验收' }).first().waitFor({ state: 'visible', timeout: 15000 });
}

const items = (page) => page.locator('.hidden-item');
const summaryText = (page) => page.locator('.hidden-summary-text').innerText();
const summarySub = (page) => page.locator('.hidden-summary-sub').innerText();
const saveBtn = (page) => page.locator('.hidden-actions button');
const noteInput = (page, i) => items(page).nth(i).locator('input.hidden-input');
const naTextarea = (page, i) => items(page).nth(i).locator('textarea.hidden-textarea');
const photoInput = (page, i) => items(page).nth(i).locator('input[type=file]');
const thumbs = (page, i) => items(page).nth(i).locator('.hidden-photo img');

let failed = 0;
async function step(name, fn) {
  try {
    const detail = await fn();
    report.steps.push({ name, ok: true, detail: detail ?? null });
    console.log('  ✅ ' + name + (detail ? ' — ' + detail : ''));
  } catch (error) {
    failed++;
    report.steps.push({ name, ok: false, error: String(error && error.message || error) });
    report.errors.push({ name, error: String(error && error.message || error) });
    console.log('  ❌ ' + name + ' — ' + (error && error.message || error));
  }
}

async function main() {
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e && e.message || e)));

  try {
    await login(page);
    await openAddressPanel(page);
    await openAddressDetail(page, '甲地址 1栋101');

    // ---- 1. 三项由后端返回，界面照实渲染 ----
    await step('甲户：三项由后端返回并渲染（含员工侧 hint）', async () => {
      const labels = await items(page).locator('.hidden-item-name').allInnerTexts();
      obs.labels = labels;
      assert.equal(labels.length, 3, '必须渲染三项');
      assert.deepEqual(labels, ['预埋件和锚固件', '隐蔽部位的防腐和填嵌处理', '高层金属窗防雷连接节点']);
      const hints = await items(page).locator('.hidden-item-hint').allInnerTexts();
      obs.hints = hints;
      assert.ok(hints.length === 3 && hints.every((h) => h.trim()), '员工侧 hint 缺失');
      return labels.join(' / ');
    });

    await step('甲户：尚未填写 + 交代业主看得到什么', async () => {
      obs.summaryInitial = { text: await summaryText(page), sub: await summarySub(page) };
      assert.equal(obs.summaryInitial.text, '尚未填写');
      assert.match(obs.summaryInitial.sub, /业主/);
      return JSON.stringify(obs.summaryInitial);
    });

    await step('甲户：三个结论下拉框选项来自 HIDDEN_RESULT_LABELS（不写死文字）', async () => {
      const opts = await items(page).nth(0).locator('option').allInnerTexts();
      obs.options = opts;
      assert.deepEqual(opts, ['请选择', '合格', '不合格', '不适用']);
      return opts.join('/');
    });

    await step('甲户：「会展示给业主」按输入框逐个标记 / 「不公开」只在整单备注', async () => {
      const pub = await page.locator('.hidden-public-tag').allInnerTexts();
      const priv = await page.locator('.hidden-private-tag').allInnerTexts();
      obs.tags = { pub, priv };
      // x-for ×3：每一项的「说明」各一个（此时没有 na 项，理由框未渲染）
      assert.equal(pub.length, 3, '三项的「说明」各要有一个「会展示给业主」标记');
      assert.ok(pub.every((t) => t.includes('会展示给业主')));
      assert.deepEqual(priv, ['不公开']);
      for (let i = 0; i < 3; i++) {
        assert.equal(await items(page).nth(i).locator('.hidden-public-tag').count(), 1,
          '第 ' + (i + 1) + ' 项的「说明」没标「会展示给业主」');
      }
      return 'public=' + pub.length + ' private=' + priv.length;
    });

    await step('甲户：结论不是「不适用」时理由输入框整块收起', async () => {
      const before = await naTextarea(page, 0).count();
      await items(page).nth(0).locator('select.hidden-select').selectOption('na');
      await page.waitForTimeout(150);
      const onNa = await naTextarea(page, 0).count();
      const tagsOnNa = await page.locator('.hidden-public-tag').count();
      await items(page).nth(0).locator('select.hidden-select').selectOption('pass');
      await page.waitForTimeout(150);
      const offNa = await naTextarea(page, 0).count();
      obs.naToggle = { before, onNa, offNa, tagsOnNa };
      assert.equal(before, 0, '未选 na 时不该有理由框');
      assert.equal(onNa, 1, '选 na 后必须出现理由框');
      assert.equal(tagsOnNa, 4, '理由框出现时要多一个「会展示给业主」标记');
      assert.equal(offNa, 0, '改回 pass 后理由框必须收起（x-if）');
      return JSON.stringify(obs.naToggle);
    });

    // ---- 2. 三条前端预校验（真实 DOM 驱动） ----
    await step('甲户：缺结论时保存被挡，提示指名缺哪几项', async () => {
      await clearToast(page);
      await saveBtn(page).click();
      const msg = await waitToast(page);
      obs.missingMsg = msg;
      assert.match(msg, /全部三项/);
      assert.ok(msg.includes('隐蔽部位的防腐和填嵌处理'), '缺项提示要带项目名：' + msg);
      return msg;
    });

    await step('甲户：合格但没照片时保存被挡，提示带项目名', async () => {
      // 先把另两项填成「不适用」并给足理由，让校验走到「缺照片」这一条
      await items(page).nth(1).locator('select.hidden-select').selectOption('na');
      await items(page).nth(2).locator('select.hidden-select').selectOption('na');
      await naTextarea(page, 1).fill('无此项');
      await naTextarea(page, 2).fill('本户非高层');
      await clearToast(page);
      await saveBtn(page).click();
      const msg = await waitToast(page);
      obs.photoMsg = msg;
      assert.match(msg, /至少上传 1 张照片/);
      assert.ok(msg.includes('预埋件和锚固件'), '缺照片提示要带项目名：' + msg);
      return msg;
    });

    await step('甲户：上传照片后缩略图出现（H3），且不重拉整单', async () => {
      const before = await thumbs(page, 0).count();
      // **不依赖仓库外的文件**：原版读的是 /tmp/hidden-e2e/anchorage.jpg，
      // 进了仓库就成了「只有写脚本那台机器能跑」。改成运行时用 pngjs 造一张真图，
      // 走 setInputFiles 的 buffer 形式——任何 checkout 都能跑。
      await photoInput(page, 0).setInputFiles({
        name: 'anchor.png', mimeType: 'image/png', buffer: makePhotoBytes(),
      });
      await page.waitForFunction(() => document.querySelectorAll('.hidden-item')[0].querySelectorAll('.hidden-photo img').length === 1, null, { timeout: 20000 });
      const after = await thumbs(page, 0).count();
      const src = await thumbs(page, 0).first().getAttribute('src');
      obs.upload = { before, after, src };
      assert.equal(before, 0);
      assert.equal(after, 1);
      assert.match(src, /^\/api\/share\/address\/[a-f0-9]{32}\/hidden-media\/[a-f0-9]{32}$/,
        '照片地址必须是契约 H5 的单数 address 公开路由，实际：' + src);
      // 照片真的能加载（不是 404 占位）。
      //
      // **必须等到它解码完再断言**：`<img>` 节点出现的那一刻 naturalWidth 还是 0
      // （src 刚换上去、字节还没到）。原版在这里直接取值，于是「功能是对的、
      // 断言是错的」——同一步里后面的放大核对 naturalWidth=240 反而过了，
      // 就是因为它晚了几百毫秒。这里改成有界等待，不是放宽断言。
      await page.waitForFunction(() => {
        const img = document.querySelectorAll('.hidden-item')[0]?.querySelector('.hidden-photo img');
        return img && img.complete && img.naturalWidth > 0;
      }, null, { timeout: 20000 }).catch(() => {});
      const natural = await thumbs(page, 0).first().evaluate((el) => el.naturalWidth);
      obs.upload.naturalWidth = natural;
      assert.ok(natural > 0, '缩略图加载失败（naturalWidth=0，等了 20s 仍未解码）');
      return JSON.stringify(obs.upload);
    });

    await step('甲户：「不适用」理由只有 1 字时保存被挡', async () => {
      await naTextarea(page, 1).fill('无');
      await clearToast(page);
      await saveBtn(page).click();
      const msg = await waitToast(page);
      obs.naMsg = msg;
      assert.match(msg, /不适用的理由/);
      assert.ok(msg.includes('隐蔽部位的防腐和填嵌处理'), '理由提示要带项目名：' + msg);
      return msg;
    });

    // ---- 3. 保存成功 → 记录落库并回显 ----
    await step('甲户：补足 2 字理由后保存成功，「已保存」徽标 + 汇总更新', async () => {
      await naTextarea(page, 1).fill('无此项');
      await clearToast(page);
      await saveBtn(page).click();
      const msg = await waitToast(page);
      obs.saveMsg = msg;
      assert.match(msg, /已保存/);
      await page.waitForFunction(() => document.querySelectorAll('.hidden-summary-text').length === 1
        && document.querySelector('.hidden-summary-text').innerText.includes('项合格'), null, { timeout: 20000 });
      obs.summaryAfterSave = { text: await summaryText(page), sub: await summarySub(page) };
      const badge = await page.locator('.addr-stage-head', { hasText: '隐蔽工程验收' }).locator('.addr-times-badge').innerText();
      obs.badge = badge;
      assert.equal(badge, '已保存');
      assert.equal(obs.summaryAfterSave.text, '1 项合格 · 2 项不适用');
      assert.match(obs.summaryAfterSave.sub, /验收日期/);
      assert.match(obs.summaryAfterSave.sub, /验收人/, '员工侧要能看到验收人（业主侧看不到，契约 public_visibility）');
      return JSON.stringify(obs.summaryAfterSave) + ' / ' + badge;
    });

    await step('甲户：保存后 revision 已被后端回填（乐观并发就绪）', async () => {
      const rev = await js(page, 'Alpine.$data(document.body).hiddenRevision');
      obs.revisionAfterSave = rev;
      assert.ok(rev >= 1, '保存后 revision 应 >= 1，实际 ' + rev);
      return 'revision=' + rev;
    });

    // ---- 4. 切到乙户：已有记录要正确回显，甲户照片不能串过来 ----
    const jiaPhotoSrc = obs.upload && obs.upload.src;

    await step('乙户：已存在的记录回显（2 合格 · 1 不适用 + 2 张照片）', async () => {
      await openAddressDetail(page, '乙地址 2栋202');
      await page.waitForFunction(() => document.querySelectorAll('.hidden-item').length === 3
        && document.querySelector('.hidden-summary-text').innerText.includes('项合格'), null, { timeout: 20000 });
      obs.summaryB = { text: await summaryText(page), sub: await summarySub(page) };
      assert.equal(obs.summaryB.text, '2 项合格 · 1 项不适用');
      const counts = [];
      for (let i = 0; i < 3; i++) counts.push(await thumbs(page, i).count());
      obs.thumbCountsB = counts;
      assert.deepEqual(counts, [1, 1, 0], '乙户照片分布应为 预埋件1 / 防腐1 / 防雷0（na）');
      // 已保存的每项说明要回填
      obs.notesB = await items(page).locator('input.hidden-input').evaluateAll((els) => els.map((e) => e.value));
      assert.ok(obs.notesB[0].includes('预埋件间距'), '每项说明没回填：' + obs.notesB[0]);
      return JSON.stringify(obs.summaryB) + ' thumbs=' + counts.join(',');
    });

    await step('乙户：na 项的理由回填，且理由框只在这一项出现', async () => {
      const boxes = await page.locator('.hidden-item textarea.hidden-textarea').count();
      const reason = await naTextarea(page, 2).inputValue();
      obs.naB = { boxes, reason };
      assert.equal(boxes, 1, '只有 na 的那一项该有理由框');
      assert.equal(reason, '本户为多层住宅，无高层金属窗');
      return JSON.stringify(obs.naB);
    });

    await step('切回甲户：甲户照片不串到乙户，乙户照片不留在甲户', async () => {
      const bSrcs = [];
      for (let i = 0; i < 3; i++) bSrcs.push(...await thumbs(page, i).evaluateAll((els) => els.map((e) => e.getAttribute('src'))));
      obs.srcsB = bSrcs;
      assert.ok(!bSrcs.includes(jiaPhotoSrc), '甲户照片串到了乙户界面：' + jiaPhotoSrc);
      await openAddressDetail(page, '甲地址 1栋101');
      await page.waitForFunction(() => document.querySelectorAll('.hidden-item').length === 3, null, { timeout: 20000 });
      const aSrcs = [];
      for (let i = 0; i < 3; i++) aSrcs.push(...await thumbs(page, i).evaluateAll((els) => els.map((e) => e.getAttribute('src'))));
      obs.srcsA = aSrcs;
      assert.deepEqual(aSrcs, [jiaPhotoSrc], '切回甲户后照片应只剩甲户自己那一张');
      assert.ok(!aSrcs.some((s) => bSrcs.includes(s)), '乙户照片留在了甲户界面');
      return 'A=' + aSrcs.length + ' B=' + bSrcs.length;
    });

    await step('整单备注标了「不公开」，且不是公开投影的一部分', async () => {
      const label = await page.locator('label.hidden-field', { hasText: '整单备注' }).first().innerText();
      obs.noteLabel = label;
      assert.match(label, /不公开/);
      return label.replace(/\s+/g, ' ');
    });

    // ---- 5. 红线文案 ----
    await step('文案红线：无「具有法律效力 / 可靠电子签名」，面板内无签认入口', async () => {
      const text = await page.locator('.addr-panel-head').evaluate(() => document.body.innerText);
      obs.forbidden = /具有法律效力|法律效力|可靠电子签名/.test(text);
      assert.equal(obs.forbidden, false);
      const entryInHidden = await page.locator('.addr-stage-head', { hasText: '隐蔽工程验收' }).locator('button:has-text("请业主签认")').count();
      obs.signoffEntryInHidden = entryInHidden;
      assert.equal(entryInHidden, 0, '隐蔽工程不做业主签认，面板里不该有签认入口');
      return 'forbidden=false entry=0';
    });

    await step('照片放大核对：点缩略图出浮层，Esc 收起且不关地址面板', async () => {
      await thumbs(page, 0).first().click();
      await page.locator('.hidden-lightbox').waitFor({ state: 'visible', timeout: 10000 });
      const big = await page.locator('.hidden-lightbox img').evaluate((el) => el.naturalWidth);
      obs.lightbox = { naturalWidth: big };
      assert.ok(big > 0, '放大图没加载出来');
      await page.keyboard.press('Escape');
      await page.locator('.hidden-lightbox').waitFor({ state: 'hidden', timeout: 5000 });
      const panelStillOpen = await page.locator('.addr-panel-head').isVisible();
      obs.lightbox.panelStillOpen = panelStillOpen;
      assert.equal(panelStillOpen, true, 'Esc 收照片浮层不该顺手关掉地址面板');
      return JSON.stringify(obs.lightbox);
    });

    await step('全程无未捕获的页面错误（Alpine 表达式全部求值通过）', async () => {
      obs.pageErrors = pageErrors;
      assert.deepEqual(pageErrors, []);
      return 'pageErrors=0';
    });
  } finally {
    await browser.close();
  }

  report.observations = obs;
  report.passed = failed === 0;
  require('node:fs').writeFileSync(path.join(out, '隐蔽工程员工侧冒烟.json'), JSON.stringify(report, null, 2));
  console.log('\n' + (report.passed ? '通过' : '失败') + '：隐蔽工程员工侧冒烟（wsgi）。');
  console.log('报告：' + path.join(out, '隐蔽工程员工侧冒烟.json'));
  if (!report.passed) process.exit(1);
}

main().catch((error) => { console.error('脚本异常：', error); process.exit(1); });
