#!/usr/bin/env node
/*
 * 隐蔽工程验收（contract hiddenwork v1）员工侧前端测试。
 *
 * 【为什么这一块必须单独测】
 * 隐蔽工程的失败方式和别处不一样：错了**不会报错**，只会让「证据」变得不可信，
 * 而证据是这一屏唯一的产品价值。
 *
 *   - 三项少填一项就存下去 → 标准强制三项，记录不完整却显示成「已验收」
 *   - 合格/不合格没有照片也存 → 隐蔽部位封板后拍不到了，事后无从查证
 *   - 「不适用」不写理由 → 「不适用」和「没做」从此分不出来
 *   - 结论从 na 改成 pass 但理由没清 → 生成「合格 + 不适用理由」这种自相矛盾的记录
 *   - 前端自己抄一份三项名字 → 后端改了名、界面还印着旧名，员工正拿着它对标准原文
 *   - 409 被静默重试 → 把对方刚存的那一版覆盖掉，而两边都以为自己的生效了
 *   - 切地址没清照片 id → A 户的现场照片出现在 B 户详情里，照片看起来都像「我家的工地」
 *   - 「会展示给业主」的字段没标出来 → 员工不知道自己在写公开内容
 *
 * 所以这里既跑纯逻辑，也做 index.html 的结构守卫（这类问题截图看不出来）。
 *
 * 用法：node --test test-hidden-client.cjs
 *       SITELOG_BACKEND=/path/to/chujiang-sitelog-share node --test test-hidden-client.cjs
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const HTML = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const ADDRESS_SRC = fs.readFileSync(path.join(__dirname, 'address-client.js'), 'utf8');
// 与 test-share.cjs / test-signoff-client.cjs 同一套取法：只抓无属性的 <script>，
// 最后一个就是 siteLogApp() 所在的大块。
const inlineScripts = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)];

// 契约 constants.ITEMS 的三项。**这份只用于对账**，不是前端的数据来源：
// 界面上的名字一律渲染后端 H1 返回的 item.label。
const CONTRACT_ITEM_KEYS = ['embedded_parts', 'anti_corrosion', 'lightning_bond'];
const CONTRACT_ITEM_LABELS = ['预埋件和锚固件', '隐蔽部位的防腐和填嵌处理', '高层金属窗防雷连接节点'];

// 面板区块边界（结构守卫都在这段里做）
const HIDDEN_START = '<!-- ===== 隐蔽工程验收（hiddenwork v1）=====';
const SIGNOFF_START = '<!-- ===== 客户签认（signoff v1）=====';
const hiddenRegion = (() => {
  const a = HTML.indexOf(HIDDEN_START);
  const b = HTML.indexOf(SIGNOFF_START);
  assert.ok(a > 0 && b > a, '找不到隐蔽工程面板的边界，结构守卫失效');
  return HTML.slice(a, b);
})();

// 扫结构时先把 HTML 注释去掉：注释里会引用 `<select>`、`x-for` 这些字样做说明，
// 不剥掉的话「下拉框里有没有 x-for」这类守卫会被自己的注释误伤。
const stripComments = (s) => s.replace(/<!--[\s\S]*?-->/g, '');

// ---------- 沙箱 ----------

/**
 * 建一个能跑 siteLogApp() 的沙箱。
 * 定时器全部换成假的（真 setInterval 会把 node 进程挂住不退出）。
 */
function makeApp(fetchImpl, opts = {}) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    return fetchImpl(url, options);
  };
  const context = {
    window: {}, fetch, confirm: () => true,
    console: { ...console, error() {} },
    setTimeout: () => 1, clearTimeout: () => {},
    setInterval: (fn, ms) => ({ fn, ms }), clearInterval: () => {},
    navigator: { clipboard: { writeText: async () => {} } },
    document: {
      getElementById: () => null,
      createElement: () => ({ click() {}, remove() {}, select() {}, style: {}, getContext: () => ({}) }),
      body: { appendChild() {} },
      execCommand: () => true,
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'auth-client.js'), 'utf8'), context, { filename: 'auth-client.js' });
  vm.runInContext(ADDRESS_SRC, context, { filename: 'address-client.js' });
  vm.runInContext(inlineScripts.at(-1)[1], context, { filename: 'index.html:<last inline script>' });
  context.window.qrcode = () => ({
    addData: () => {}, make: () => {}, getModuleCount: () => 21, isDark: (r, c) => (r + c) % 2 === 0,
  });

  const app = context.siteLogApp();
  app.showToast = () => {};       // 默认静音；要断言提示的用例自己换掉
  app.calls = calls;
  app.csrf = 'test-csrf';
  if (opts.addressId) app.addressDetail = { id: opts.addressId, label: '观海花园 3 栋 2201' };
  return app;
}

const okJson = (body, status = 200) => ({ status, ok: true, json: async () => body });
const errJson = (body, status) => ({ status, ok: false, json: async () => body });
const tick = () => new Promise((resolve) => setImmediate(resolve));

// H1 的标准返回：三项永远返回，未填写时 result=null。
const h1Items = (over = {}) => CONTRACT_ITEM_KEYS.map((key, i) => ({
  item_key: key,
  label: CONTRACT_ITEM_LABELS[i],
  hint: '检查要点 ' + (i + 1),
  result: null,
  na_reason: '',
  note: '',
  photos: [],
  ...(over[key] || {}),
}));
const h1 = (over = {}) => ({ ok: true, items: h1Items(over.items || {}), acceptance: over.acceptance ?? null });

/** 把 app 摆到「三项都填好、可以保存」的状态。 */
function readyApp(fetchImpl, opts = {}) {
  const app = makeApp(fetchImpl, { addressId: opts.addressId || 'addr1', ...opts });
  app.hiddenItems = h1Items();
  app.hiddenAcceptedAt = '2026-09-24';
  return app;
}

/** 给某一项补上「合格 + n 张照片」。 */
function fillPass(app, index, photos = 1) {
  const item = app.hiddenItems[index];
  item.result = 'pass';
  item.photos = Array.from({ length: photos }, (_, i) => String(i).padStart(32, '0'));
  return item;
}

// =====================================================================
// 1. 读取（契约 H1）
// =====================================================================

test('H1：拉取三项 + 归一化未填写态，revision / 验收日期 / 整单备注都落到 state', async () => {
  const app = makeApp(async () => okJson(h1({
    acceptance: { accepted_at: 1780000000, note: '业主在场', revision: 3, acceptor_name: '王工', updated: 1780000001 },
  })), { addressId: 'addr1' });

  await app.loadHiddenAcceptance('addr1');

  assert.equal(app.calls[0].url, '/api/share/addresses/addr1/hidden-acceptance');
  assert.equal(app.calls[0].options.method, undefined, '读取必须是 GET，不能带 method');
  assert.equal(app.hiddenLoading, false);
  assert.equal(app.hiddenError, '');
  assert.equal(app.hiddenItems.length, 3);
  assert.equal(app.hiddenRevision, 3, '已保存的地址要用记录里的 revision');
  assert.equal(app.hiddenAcceptedAt, '2026-05-29', '验收日期由 accepted_at 反推（本地时区）');
  assert.equal(app.hiddenNote, '业主在场');

  // 未填写态归一化成 ''：<select> 的 x-model 拿 null 会找不到匹配项。
  const fresh = makeApp(async () => okJson(h1()), { addressId: 'addr1' });
  await fresh.loadHiddenAcceptance('addr1');
  assert.equal(fresh.hiddenAcceptance, null);
  assert.equal(fresh.hiddenRevision, 0, '新建必须传 0，否则后端 409');
  assert.ok(fresh.hiddenItems.every((i) => i.result === ''), 'result=null 要归一化成空串');
  assert.ok(fresh.hiddenItems.every((i) => Array.isArray(i.photos)));
  assert.match(fresh.hiddenAcceptedAt, /^\d{4}-\d{2}-\d{2}$/, '没记录时默认今天，方便直接填');
});

test('H1：三项形状不对时当场报错，不静默渲染半张表', async () => {
  // 少一项就少一行，员工会在不知情的情况下存下一份「不完整」的记录。
  const app = makeApp(async () => okJson({
    ok: true, items: [{ item_key: 'embedded_parts', label: '预埋件和锚固件', result: null, photos: [] }], acceptance: null,
  }), { addressId: 'addr1' });

  await app.loadHiddenAcceptance('addr1');

  assert.equal(app.hiddenItems.length, 0, '形状不符时不能渲染');
  assert.match(app.hiddenError, /隐蔽工程验收项目与标准不符/);
  assert.equal(app.hiddenLoading, false);
});

test('H1：读取失败进 error 态，不留空表单冒充「尚未填写」', async () => {
  const app = makeApp(async () => errJson({ ok: false, error: '无权访问该地址' }, 403), { addressId: 'addr1' });

  await app.loadHiddenAcceptance('addr1');

  assert.equal(app.hiddenItems.length, 0);
  assert.equal(app.hiddenError, '无权访问该地址', '后端文案要透出，不能吞掉');
  assert.equal(app.hiddenLoading, false);
});

test('切地址时迟到的旧响应不覆盖新地址的隐蔽工程', async () => {
  let release;
  const app = makeApp(() => new Promise((r) => { release = r; }), { addressId: 'addrA' });
  app.hiddenItems = [{ item_key: 'embedded_parts', label: '旧户', result: 'pass', photos: ['m'] }];

  const pending = app.loadHiddenAcceptance('addrA');
  app.addressDetail = { id: 'addrB' };            // 员工已经切到另一户
  release(okJson(h1({ acceptance: { accepted_at: 1780000000, note: '', revision: 9 } })));

  await pending;
  assert.equal(app.hiddenItems.length, 1, 'A 户的记录不能落到 B 户详情里');
  assert.equal(app.hiddenRevision, 0);
});

// =====================================================================
// 2. 保存前的 7 条校验（每条都要带项目名，员工才知道改哪一项）
// =====================================================================

test('校验①：三项必须全部有结论，缺项要指名道姓', async () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems[0].result = 'na';
  app.hiddenItems[0].na_reason = '本户非高层';

  const problem = app.hiddenValidate();
  assert.match(problem, /全部三项/);
  assert.ok(problem.includes(CONTRACT_ITEM_LABELS[1]), '缺项提示要带项目名：' + problem);
  assert.ok(problem.includes(CONTRACT_ITEM_LABELS[2]), '缺项提示要带项目名：' + problem);

  // 三项齐全后不再报缺项
  app.hiddenItems[1].result = 'na';
  app.hiddenItems[1].na_reason = '无此项';
  app.hiddenItems[2].result = 'na';
  app.hiddenItems[2].na_reason = '本户非高层';
  assert.equal(app.hiddenValidate(), '', '三项齐全且无照片要求（na）时应通过');
});

test('校验①边界：项目还没加载出来时不放行，也不给出「缺少：（空）」', () => {
  const app = makeApp(async () => okJson({ ok: true }), { addressId: 'addr1' });
  app.hiddenItems = [];
  const problem = app.hiddenValidate();
  assert.match(problem, /尚未加载/);
  assert.ok(!/缺少：\s*$/.test(problem), '不能给出「缺少：」后面空着的提示');
});

test('校验②：合格 / 不合格至少 1 张照片（0 张拒、1 张过）', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });

  // 0 张 → 拒，且提示里带项目名
  fillPass(app, 1, 0);
  const problem = app.hiddenValidate();
  assert.match(problem, /至少上传 1 张照片/);
  assert.ok(problem.includes(CONTRACT_ITEM_LABELS[1]), '缺照片提示要带项目名：' + problem);

  // 1 张 → 过
  fillPass(app, 1, 1);
  assert.equal(app.hiddenValidate(), '', '1 张照片就该放行（下限就是 1）');

  // fail 同样要照片：隐蔽部位封板后拍不到了
  const app2 = readyApp(async () => okJson({ ok: true }));
  app2.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  app2.hiddenItems[2].result = 'fail';
  app2.hiddenItems[2].photos = [];
  assert.match(app2.hiddenValidate(), /至少上传 1 张照片/);
});

test('校验③：不适用理由至少 2 字（1 字拒、2 字过），na 不要求照片', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  app.hiddenItems[2].photos = [];

  app.hiddenItems[2].na_reason = '无';
  const problem = app.hiddenValidate();
  assert.match(problem, /不适用的理由/);
  assert.match(problem, /至少 2 字/);
  assert.ok(problem.includes(CONTRACT_ITEM_LABELS[2]), '理由提示要带项目名：' + problem);

  // 纯空白不算填写
  app.hiddenItems[2].na_reason = '   ';
  assert.match(app.hiddenValidate(), /不适用的理由/);

  // 2 字 → 过（下限就是 2，不能更松也不能更严）
  app.hiddenItems[2].na_reason = '无此';
  assert.equal(app.hiddenValidate(), '', '2 字理由就该放行；na 不需要照片');
});

test('校验④：结论不是「不适用」时理由必须清空，不留「合格 + 不适用理由」', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '本户非高层'; });
  app.hiddenItems[0].na_reason = '  本户非高层  ';      // 前后空白也要清

  fillPass(app, 0, 1);                                  // 员工把 na 改成了 pass
  assert.equal(app.hiddenValidate(), '', '结论改了之后不该再被旧理由卡住');

  const body = app.hiddenPayload();
  const entry = body.items.find((i) => i.item_key === CONTRACT_ITEM_KEYS[0]);
  assert.equal(entry.result, 'pass');
  assert.equal(entry.na_reason, '', '结论不是 na 时必须清空理由，否则记录自相矛盾');

  // 仍是 na 的那两项理由保留（并 trim）
  const naEntry = body.items.find((i) => i.item_key === CONTRACT_ITEM_KEYS[1]);
  assert.equal(naEntry.na_reason, '本户非高层');
});

test('校验⑤：每项最多 8 张照片（8 张过、9 张拒、加号按钮收起）', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });

  fillPass(app, 0, 8);
  assert.equal(app.hiddenPhotoCount(app.hiddenItems[0]), 8);
  assert.equal(app.hiddenCanAddPhoto(app.hiddenItems[0]), false, '满 8 张后「＋ 加照片」必须收起');
  assert.equal(app.hiddenValidate(), '', '8 张是允许的上限');

  fillPass(app, 0, 9);
  const problem = app.hiddenValidate();
  assert.match(problem, /最多上传 8 张照片/);
  assert.ok(problem.includes(CONTRACT_ITEM_LABELS[0]), '超限提示要带项目名：' + problem);

  // 上限是 8 不是 9：7 张时还能加
  fillPass(app, 0, 7);
  assert.equal(app.hiddenCanAddPhoto(app.hiddenItems[0]), true);
  assert.equal(app.hiddenValidate(), '');
});

test('校验⑥：验收日期必填，非法日期（2026-02-31）也要挡下', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });

  app.hiddenAcceptedAt = '';
  assert.match(app.hiddenValidate(), /请选择验收日期/);

  app.hiddenAcceptedAt = '2026-02-31';           // JS 会静默顺延到 3 月 3 日
  assert.equal(app.hiddenDateEpoch('2026-02-31'), 0, '不存在的日期必须判非法');
  assert.match(app.hiddenValidate(), /请选择验收日期/);

  app.hiddenAcceptedAt = '2026-13-01';
  assert.equal(app.hiddenDateEpoch('2026-13-01'), 0);

  app.hiddenAcceptedAt = '2026-09-24';
  assert.ok(app.hiddenDateEpoch('2026-09-24') > 1000000000, '合法日期要能转成 epoch 秒');
  assert.equal(app.hiddenValidate(), '');
  // 日期输入框 ↔ epoch 秒 必须能往返
  assert.equal(app.hiddenDateInput(app.hiddenDateEpoch('2026-09-24')), '2026-09-24');
});

test('校验：文字长度上限（每项说明 / 不适用理由 / 整单备注都是 200）', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });

  app.hiddenItems[1].note = '说'.repeat(201);
  assert.match(app.hiddenValidate(), /说明不能超过 200 字/);

  app.hiddenItems[1].note = '说'.repeat(200);
  app.hiddenItems[1].na_reason = '理'.repeat(201);
  assert.match(app.hiddenValidate(), /不适用理由不能超过 200 字/);

  app.hiddenItems[1].na_reason = '理'.repeat(200);
  app.hiddenNote = '备'.repeat(201);
  assert.match(app.hiddenValidate(), /整单备注不能超过 200 字/);

  app.hiddenNote = '备'.repeat(200);
  assert.equal(app.hiddenValidate(), '', '200 字是允许的上限');
});

// =====================================================================
// 3. 保存（契约 H2：POST 不是 PUT；revision 乐观并发）
// =====================================================================

test('H2：POST（不是 PUT）整单保存，body 字段与契约逐条对得上', async () => {
  const app = readyApp(async (url, options) => {
    if (options && options.method === 'POST') return okJson({ ok: true, revision: 1 });
    return okJson(h1({ acceptance: { accepted_at: 1780000000, note: '业主在场', revision: 1 } }));
  });
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  fillPass(app, 0, 2);
  app.hiddenNote = '  验收当天业主在场  ';        // 前后空白应被 trim

  await app.saveHiddenAcceptance();

  const post = app.calls.find((c) => c.options && c.options.method === 'POST');
  assert.ok(post, '没发出保存请求：' + JSON.stringify(app.calls.map((c) => c.url)));
  assert.equal(post.url, '/api/share/addresses/addr1/hidden-acceptance');
  assert.equal(post.options.method, 'POST', '契约 errata HW-1：用 POST 不用 PUT');
  assert.equal(post.options.headers['X-CSRF-Token'], 'test-csrf', '写请求必须带 X-CSRF-Token');

  const body = JSON.parse(post.options.body);
  assert.equal(body.revision, 0, '新建必须传 0');
  assert.equal(body.accepted_at, app.hiddenDateEpoch('2026-09-24'), 'accepted_at 是 epoch 秒');
  assert.equal(body.note, '验收当天业主在场');
  assert.equal(body.items.length, 3, 'items 必须恰好覆盖三项');
  assert.deepEqual(body.items.map((i) => i.item_key), CONTRACT_ITEM_KEYS);
  assert.equal(body.items[0].result, 'pass');
  assert.equal(body.items[0].na_reason, '');
  assert.equal(body.items[1].result, 'na');
  assert.equal(body.items[1].na_reason, '无此项');
  // 前端不算照片数、不算摘要——照片齐全性由后端在事务内复查
  assert.ok(!('photos' in body.items[0]), '前端不该把照片数组塞进保存请求');
  assert.ok(!('acceptor' in body) && !('acceptor_name' in body), 'acceptor 由后端记，不接受客户端指定');

  // 保存成功后要重新拉一遍，否则界面还显示旧的 revision
  assert.ok(app.calls.some((c) => c.options.method === undefined && /hidden-acceptance$/.test(c.url)),
    '保存成功后没有重新拉取记录');
  assert.equal(app.hiddenBusy, false, '请求结束后必须解除 busy');
});

test('H2：连点两次「保存」只提交一次', async () => {
  let release;
  let posts = 0;
  const app = readyApp((url, options) => {
    if (options && options.method === 'POST') { posts++; return new Promise((r) => { release = r; }); }
    return okJson(h1({ acceptance: { accepted_at: 1780000000, note: '', revision: 1 } }));
  });
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });

  const first = app.saveHiddenAcceptance();
  await app.saveHiddenAcceptance();               // 第二次点在 busy 期间
  assert.equal(posts, 1, '防重复提交失效：连点会存两次');

  release(okJson({ ok: true, revision: 1 }));
  await first;
  assert.equal(app.hiddenBusy, false);
});

test('校验不通过时不发保存请求，提示原样透出', async () => {
  const app = readyApp(async () => okJson({ ok: true }));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  app.hiddenItems[0].result = 'pass';             // 改成合格，但没传照片
  app.hiddenItems[0].photos = [];

  await app.saveHiddenAcceptance();

  assert.equal(app.calls.length, 0, '校验没过不该发请求');
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, 'error');
  assert.match(toasts[0].msg, /至少上传 1 张照片/);
  assert.equal(app.hiddenBusy, false);
});

test('H2 409：重新拉取 + 回填最新 revision + 明确告知，**不静默重试**', async () => {
  let posts = 0;
  // 服务端那一版：三项都是「不适用」，revision 已经被别的设备推到 5。
  const serverItems = {
    embedded_parts: { result: 'na', na_reason: '无此项' },
    anti_corrosion: { result: 'na', na_reason: '无此项' },
    lightning_bond: { result: 'na', na_reason: '无此项' },
  };
  const app = readyApp((url, options) => {
    if (options && options.method === 'POST') {
      posts++;
      return errJson({ ok: false, error: '验收记录已被其他设备更新，请刷新后重试' }, 409);
    }
    return okJson(h1({
      items: serverItems,
      acceptance: { accepted_at: 1780000000, note: '对方刚写的', revision: 5, acceptor_name: '王工' },
    }));
  });
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  app.hiddenRevision = 2;                         // 员工手上是旧版本

  await app.saveHiddenAcceptance();

  assert.equal(posts, 1, '409 之后**不许**静默重试：静默重试会把对方刚存的那一版覆盖掉');
  assert.equal(app.hiddenRevision, 5, '必须回填服务端最新 revision，员工核对后再存');
  assert.equal(app.hiddenNote, '对方刚写的', '刷新要把对方的版本显示出来，员工才能核对');
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, 'error');
  assert.match(toasts[0].msg, /已被其他设备更新/);
  assert.match(toasts[0].msg, /已刷新/);
  assert.match(toasts[0].msg, /重新保存/);
  assert.equal(app.hiddenBusy, false, '409 也要解除 busy，否则按钮永久禁用');

  // 员工核对后重存：这一轮 hiddenItems 已经是刷新回来的服务端版本，校验能过
  assert.equal(app.hiddenValidate(), '', '刷新后应该能直接重存，不该被卡住');
  await app.saveHiddenAcceptance();
  const post = app.calls.filter((c) => c.options && c.options.method === 'POST').at(-1);
  assert.equal(JSON.parse(post.options.body).revision, 5, '重存必须用刷新后的 revision');
  assert.equal(posts, 2);
});

test('H2 其他错误：原样透出后端文案，不清空员工填的内容', async () => {
  const app = readyApp(async () => errJson({ ok: false, error: '请为「预埋件和锚固件」至少上传 1 张照片' }, 400));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.hiddenItems.forEach((i) => { i.result = 'na'; i.na_reason = '无此项'; });
  app.hiddenNote = '写了半句';

  await app.saveHiddenAcceptance();

  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].msg, '请为「预埋件和锚固件」至少上传 1 张照片');
  assert.equal(app.hiddenNote, '写了半句', '失败不能把员工写的内容清掉');
  assert.equal(app.hiddenBusy, false);
});

// =====================================================================
// 4. 照片（契约 H3 上传 / H4 删除 / H5 展示）
// =====================================================================

test('H3：上传前先压缩，body 是 {item_key,dataUrl,filename}，成功后只把新 id 追加到本地', async () => {
  const app = readyApp(async (url, options) => {
    if (options && options.method === 'POST') return okJson({ ok: true, id: 'a'.repeat(32), size: 1234 }, 201);
    return okJson(h1());
  });
  const compressed = [];
  app.fileToDataUrl = async () => 'data:image/jpeg;base64,ORIGINAL';
  app.compressDataUrl = async (d) => { compressed.push(d); return 'data:image/jpeg;base64,COMPRESSED'; };

  const item = app.hiddenItems[0];
  await app.uploadHiddenPhoto(item, { name: '锚固件.jpg' });

  assert.deepEqual(compressed, ['data:image/jpeg;base64,ORIGINAL'],
    '必须先把原图交给 compressDataUrl 压过再传（现场原图动辄 4–8MB）');
  const post = app.calls.find((c) => c.options && c.options.method === 'POST');
  assert.equal(post.url, '/api/share/addresses/addr1/hidden-media');
  assert.equal(post.options.method, 'POST');
  assert.deepEqual(JSON.parse(post.options.body), {
    item_key: CONTRACT_ITEM_KEYS[0],
    dataUrl: 'data:image/jpeg;base64,COMPRESSED',
    filename: '锚固件.jpg',
  });
  assert.deepEqual(item.photos, ['a'.repeat(32)], '新 id 要追加到本地列表');
  // 只追加、不重新拉整单：重拉会把员工正在填的结论/说明一起覆盖掉
  assert.equal(app.calls.filter((c) => c.options.method === undefined).length, 0,
    '上传后不该重新拉取记录，否则员工填了一半的内容会被覆盖');
  assert.equal(app.hiddenPhotoBusy, '');
});

test('H3：重复上传（后端 duplicate:true）给出可理解的提示', async () => {
  const app = readyApp(async () => okJson({ ok: true, id: 'b'.repeat(32), size: 1, duplicate: true }, 201));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.fileToDataUrl = async () => 'data:image/jpeg;base64,X';
  app.compressDataUrl = async (d) => d;

  await app.uploadHiddenPhoto(app.hiddenItems[0], { name: 'a.jpg' });

  assert.match(toasts[0].msg, /已经传过/);
  assert.equal(toasts[0].type, undefined, '重复上传不是错误');
});

test('H3：非图片 / 超大照片先挡下，不白传一次', async () => {
  const app = readyApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.fileToDataUrl = async () => 'data:text/plain;base64,QQ==';
  app.compressDataUrl = async (d) => d;

  await app.uploadHiddenPhoto(app.hiddenItems[0], { name: 'a.txt' });
  assert.equal(app.calls.length, 0, '不是图片不该发请求');
  assert.match(toasts[0].msg, /图片格式/);

  // 超过契约 PHOTO_DATA_URL_CEILING（= 10MB 原图 base64 放大 4/3 再留余量）
  assert.equal(app.HIDDEN_PHOTO_DATA_URL_CEILING, 15029588, '上限必须与契约 PHOTO_DATA_URL_CEILING 一致');
  app.fileToDataUrl = async () => 'data:image/jpeg;base64,' + 'A'.repeat(app.HIDDEN_PHOTO_DATA_URL_CEILING);
  await app.uploadHiddenPhoto(app.hiddenItems[0], { name: 'big.jpg' });
  assert.equal(app.calls.length, 0, '超限照片不该发请求（后端会 413）');
  assert.match(toasts[1].msg, /太大/);
  assert.equal(app.hiddenPhotoBusy, '');
});

test('H3：满 8 张时不再发起上传', async () => {
  const app = readyApp(async () => okJson({ ok: true, id: 'd'.repeat(32) }, 201));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.fileToDataUrl = async () => 'data:image/jpeg;base64,X';
  app.compressDataUrl = async (d) => d;

  const item = app.hiddenItems[0];
  item.photos = Array.from({ length: 8 }, (_, i) => String(i).padStart(32, '0'));
  await app.uploadHiddenPhoto(item, { name: 'a.jpg' });

  assert.equal(app.calls.length, 0, '满 8 张不该发请求');
  assert.match(toasts[0].msg, /最多上传 8 张照片/);
  assert.equal(item.photos.length, 8, '不该被塞进第 9 张');
});

test('H4：删照片走 DELETE（不是 POST），并带上 CSRF 头', async () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.hiddenItems[0].photos = ['e'.repeat(32), 'f'.repeat(32)];
  app.hiddenPreview = 'e'.repeat(32);

  await app.removeHiddenPhoto(app.hiddenItems[0], 'e'.repeat(32));

  const call = app.calls[0];
  assert.equal(call.url, '/api/share/addresses/addr1/hidden-media/' + 'e'.repeat(32));
  assert.equal(call.options.method, 'DELETE',
    '契约 H4 判 self.command==\'DELETE\'；走 accountJSON 只能发 POST，后端会 405');
  assert.equal(call.options.headers['X-CSRF-Token'], 'test-csrf', 'DELETE 是写请求，必须带 CSRF 头');
  assert.deepEqual(app.hiddenItems[0].photos, ['f'.repeat(32)], '只摘掉被删的那一张');
  assert.equal(app.hiddenPreview, '', '删掉的正是放大查看的那张时要把浮层收起');
});

test('H5：照片展示走公开路由（单数 address），不是鉴权路由', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  assert.equal(app.hiddenPhotoUrl('m'.repeat(32)),
    '/api/share/address/addr1/hidden-media/' + 'm'.repeat(32),
    '契约 H5 的路径是单数 address（业主侧公开路由），不能写成 addresses');
  assert.equal(app.hiddenPhotoUrl(''), '');
});

// =====================================================================
// 5. 状态隔离：切地址 / 关面板必须清干净（照片串户比文字串户严重）
// =====================================================================

test('切地址：openAddress 立刻清空上一户的隐蔽工程状态，再拉新的', async () => {
  let releaseHidden;
  const app = makeApp((url) => {
    if (/hidden-acceptance$/.test(url)) return new Promise((r) => { releaseHidden = r; });
    if (/signoffs$/.test(url)) return okJson({ ok: true, items: [] });
    return okJson({ ok: true, id: 'addrB', stages: [], enabled_stages: [] });
  }, { addressId: 'addrA' });
  app.hiddenItems = h1Items({ embedded_parts: { result: 'pass', photos: ['oldmid'] } });
  app.hiddenAcceptance = { revision: 7 };
  app.hiddenRevision = 7;
  app.hiddenNote = 'A 户的备注';
  app.hiddenAcceptedAt = '2026-01-01';
  app.hiddenPhotoBusy = 'embedded_parts';
  app.hiddenPreview = 'oldmid';
  app.hiddenError = '旧错误';

  const pending = app.openAddress('addrB');
  await tick();                                   // 详情已到手，隐蔽工程请求还挂着

  assert.equal(app.hiddenItems.length, 0, 'A 户的照片/结论不能留在 B 户详情里');
  assert.equal(app.hiddenRevision, 0);
  assert.equal(app.hiddenNote, '');
  assert.equal(app.hiddenPreview, '', '照片放大浮层要收起');
  assert.equal(app.hiddenPhotoBusy, '');
  assert.equal(app.hiddenError, '');

  releaseHidden(okJson(h1()));
  await pending;
  assert.equal(app.hiddenItems.length, 3, '复位之后要拉 B 户自己的三项');
  assert.equal(app.hiddenRevision, 0, 'B 户没记录，revision 是 0');
});

test('关详情 / 关面板 / 重开面板都清空隐蔽工程状态', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  const dirty = () => {
    app.hiddenItems = h1Items();
    app.hiddenRevision = 4;
    app.hiddenNote = '半句';
    app.hiddenPreview = 'm';
    app.hiddenPhotoBusy = 'embedded_parts';
    app.hiddenBusy = true;
    app.hiddenError = '旧错误';
  };
  const assertClean = (label) => {
    assert.equal(app.hiddenItems.length, 0, label + '：items 没清');
    assert.equal(app.hiddenRevision, 0, label + '：revision 没清');
    assert.equal(app.hiddenNote, '', label + '：备注没清');
    assert.equal(app.hiddenPreview, '', label + '：照片浮层没清');
    assert.equal(app.hiddenPhotoBusy, '', label + '：上传中标记没清');
    assert.equal(app.hiddenBusy, false, label + '：busy 没清');
    assert.equal(app.hiddenError, '', label + '：error 没清');
  };

  dirty(); app.closeAddressDetail(); assertClean('closeAddressDetail');
  dirty(); app.closeAddressPanel(); assertClean('closeAddressPanel');
  dirty(); app.openAddressPanel(); assertClean('openAddressPanel');
  dirty(); app.resetHiddenState(); assertClean('resetHiddenState');
});

test('Esc 逐层退出：照片放大是最内层，先收它再收下面的面板', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.addressPanel = true;
  app.addressDetail = { id: 'addr1' };
  app.hiddenPreview = 'm'.repeat(32);

  app.escapeAddressPanel();

  assert.equal(app.hiddenPreview, '', 'Esc 要先收起照片浮层');
  assert.equal(app.addressPanel, true, '收起照片浮层不该顺手把地址面板一起关掉');
});

test('放大 / 收起照片预览', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  app.openHiddenPreview('m'.repeat(32));
  assert.equal(app.hiddenPreview, 'm'.repeat(32));
  app.closeHiddenPreview();
  assert.equal(app.hiddenPreview, '');
});

// =====================================================================
// 6. 展示口径
// =====================================================================

test('顶部汇总：2 项合格 · 1 项不适用；一项都没填时是「尚未填写」', () => {
  const app = readyApp(async () => okJson({ ok: true }));

  assert.equal(app.hiddenSummary(), '尚未填写', '一项都没填时不留空白');

  app.hiddenItems[0].result = 'pass';
  app.hiddenItems[1].result = 'pass';
  app.hiddenItems[2].result = 'na';
  assert.equal(app.hiddenSummary(), '2 项合格 · 1 项不适用');

  app.hiddenItems[1].result = 'fail';
  assert.equal(app.hiddenSummary(), '1 项合格 · 1 项不合格 · 1 项不适用');

  app.hiddenItems[1].result = '';
  assert.equal(app.hiddenSummary(), '1 项合格 · 1 项不适用 · 1 项未填', '填了一半也要说清楚还差一项');
});

test('结论显示名只在本地有一份映射，未填写时是「未填写」而不是 undefined', () => {
  const app = readyApp(async () => okJson({ ok: true }));
  assert.equal(app.hiddenResultLabel('pass'), '合格');
  assert.equal(app.hiddenResultLabel('fail'), '不合格');
  assert.equal(app.hiddenResultLabel('na'), '不适用');
  assert.equal(app.hiddenResultLabel(''), '未填写');
  assert.equal(app.hiddenResultLabel(null), '未填写');
});

test('汇总副行：已保存显示验收日期与验收人；未保存交代业主看得到什么', () => {
  const app = readyApp(async () => okJson({ ok: true }));

  assert.equal(app.hiddenAcceptanceLine(), '保存后业主可在地址页看到三项结论、验收时间与照片');

  app.hiddenAcceptance = { accepted_at: 1780000000, revision: 1, acceptor_name: '王工' };
  app.hiddenAcceptedAt = '2026-05-29';
  assert.equal(app.hiddenAcceptanceLine(), '验收日期 2026-05-29 · 验收人 王工');

  // 后端没给验收人姓名时不要留一个空的「验收人 」
  app.hiddenAcceptance = { accepted_at: 1780000000, revision: 1, acceptor_name: '' };
  assert.equal(app.hiddenAcceptanceLine(), '验收日期 2026-05-29');
});

// =====================================================================
// 7. index.html 结构守卫
// =====================================================================

test('index.html：面板在阶段列表之后、客户签认区之前', () => {
  const pending = HTML.indexOf('还没留档：');
  assert.ok(pending > 0, '找不到阶段列表的结尾');
  assert.ok(HTML.indexOf(HIDDEN_START) > pending, '隐蔽工程面板要排在阶段列表之后');
  assert.ok(HTML.indexOf(HIDDEN_START) < HTML.indexOf(SIGNOFF_START), '隐蔽工程面板要排在客户签认区之前');
});

test('index.html：三项名字一律渲染后端的 item.label，不抄第二份', () => {
  // 正面要求：名字必须来自后端返回
  assert.match(hiddenRegion, /x-text="item\.label"/, '项目名没有渲染后端 label');
  assert.match(hiddenRegion, /x-text="item\.hint"/, '员工侧的检查要点（hint）没渲染');

  // 负面要求：三项的名字不能作为**字符串字面量**写进前端。
  // （注释里引用标准原文不算——那是文档，不是数据；这里只查引号包起来的字面量。）
  for (const label of CONTRACT_ITEM_LABELS) {
    for (const quoted of [`'${label}'`, `"${label}"`]) {
      assert.ok(!ADDRESS_SRC.includes(quoted), 'address-client.js 把项目名写成了字面量：' + label);
      assert.ok(!HTML.includes(quoted), 'index.html 把项目名写成了字面量：' + label);
    }
  }
  // 三项的 key 在前端只允许出现在一处：形状兜底用的 HIDDEN_ITEM_KEYS
  assert.equal((ADDRESS_SRC.match(/HIDDEN_ITEM_KEYS/g) || []).length, 2,
    'HIDDEN_ITEM_KEYS 只应有「声明 + 形状比对」两处用法');
});

test('index.html：结论选项静态写死，不在 x-for 里（x-model 会错位）', () => {
  const markup = stripComments(hiddenRegion);
  const selects = [...markup.matchAll(/<select[\s\S]*?<\/select>/g)].map((m) => m[0]);
  assert.ok(selects.length >= 1, '找不到结论下拉框');
  for (const block of selects) {
    assert.ok(!/x-for/.test(block),
      '下拉框里用了 x-for：x-model 的初始赋值发生在 x-for 插入 <option> 之前，'
      + '会回落显示第一项，出现「显示合格、实际存不适用」的错位');
  }
  // value 是契约枚举（constants.RESULTS），静态写死是刻意的；**文字不写第二份**，
  // 一律走 hiddenResultLabel()，真源只有 address-client.js 的 HIDDEN_RESULT_LABELS。
  assert.match(markup, /<option value="">请选择<\/option>/, '要有一个空的「请选择」，否则没法表示「未填写」');
  for (const key of ['pass', 'fail', 'na']) {
    assert.match(markup, new RegExp('<option value="' + key + '"\\s+x-text="hiddenResultLabel\\(\'' + key + '\'\\)"></option>'),
      '结论选项 ' + key + ' 的文字没有走 hiddenResultLabel()（会多出一份结论显示名）');
  }
  // 结论显示名在前端只允许有一份定义
  assert.equal((ADDRESS_SRC.match(/HIDDEN_RESULT_LABELS/g) || []).length, 2,
    'HIDDEN_RESULT_LABELS 只应有「声明 + 取值」两处');
  assert.ok(!/>(合格|不合格|不适用)</.test(markup), '结论文字被写死在 HTML 里了');
});

test('index.html：「会展示给业主」与「不公开」两个标记都在位', () => {
  const publicTags = (hiddenRegion.match(/hidden-public-tag/g) || []).length;
  const privateTags = (hiddenRegion.match(/hidden-private-tag/g) || []).length;
  assert.ok(publicTags >= 2, '每项说明与不适用理由都要标「会展示给业主」，实际只有 ' + publicTags + ' 处');
  assert.equal(privateTags, 1, '整单备注要标「不公开」，且只标一处');

  // 标记要真的挂在对应输入框的标签行上，不是随便丢在面板某处
  assert.match(hiddenRegion, /说明[\s\S]{0,120}?hidden-public-tag/, '每项说明没标「会展示给业主」');
  assert.match(hiddenRegion, /不适用理由[\s\S]{0,200}?hidden-public-tag/, '不适用理由没标「会展示给业主」');
  assert.match(hiddenRegion, /整单备注[\s\S]{0,120}?hidden-private-tag/, '整单备注没标「不公开」');

  // 不适用理由只在结论是 na 时出现。
  // 用 x-if 而不是 x-show：本块在 x-for 里，而 loadHiddenAcceptance 会整体替换
  // hiddenItems（切地址 / 保存后刷新）。「x-show 藏在 x-for 里 + 外层列表同轮被整体
  // 替换」这个组合会让 Alpine 3 重复走隐藏流程并抛未捕获错误（签认区实测过）。
  assert.match(hiddenRegion, /<template x-if="item\.result === 'na'">/, '不适用理由没有按结论条件渲染');
  // 不适用理由的下限用常量，不写死
  assert.match(hiddenRegion, /HIDDEN_NA_REASON_MIN/);
  // 照片上限用常量
  assert.match(hiddenRegion, /HIDDEN_PHOTOS_PER_ITEM_MAX/);
});

test('index.html：三态（loading / error / 表单）与照片浮层都在位', () => {
  assert.match(hiddenRegion, /x-show="hiddenLoading"/);
  assert.match(hiddenRegion, /x-show="!hiddenLoading && !!hiddenError"/);
  assert.match(hiddenRegion, /openHiddenPreview\(/);
  // 上传入口 + 传完清空 input.value（不清的话同一张图第二次选不触发 change）
  assert.match(hiddenRegion, /type="file"[\s\S]{0,400}?uploadHiddenPhoto\(item, \$event\.target\.files\[0\]\)/);
  assert.match(hiddenRegion, /uploadHiddenPhoto\(item, \$event\.target\.files\[0\]\);\s*\$event\.target\.value = ''/);
  // 防重复提交
  assert.match(hiddenRegion, /:disabled="hiddenBusy"/);
  assert.match(hiddenRegion, /saveHiddenAcceptance\(\)/);

  // 照片放大浮层放在地址详情模板的末尾（不是面板块内），所以在整页范围里找。
  assert.match(HTML, /x-show="!!hiddenPreview"[\s\S]{0,400}?hiddenPhotoUrl\(hiddenPreview\)/, '照片放大浮层缺失');
  assert.match(HTML, /hidden-lightbox[\s\S]{0,300}?closeHiddenPreview\(\)/);
});

test('x-show 表达式不能混类型：Alpine 会对同一元素隐藏两次并抛未捕获错误', () => {
  // 与签认区同一个坑（详见 test-signoff-client.cjs）：`a && b` 里 b 是字符串时，
  // 表达式在 string/boolean 之间跳变，Alpine 内部 `p === l` 判等失败，
  // 对同一元素连续走两次隐藏流程，第二次抛 `TypeError: u is not a function`。
  assert.ok(
    !/x-show="[^"]*&&\s*(hiddenError|hiddenPreview|hiddenPhotoBusy|hiddenNote|hiddenAcceptedAt|item\.hint|item\.label|item\.result|item\.na_reason|item\.note)\s*"/.test(HTML),
    'x-show 里把可能为字符串的字段直接当成 && 的右操作数 —— 必须用 !! 转成布尔',
  );
  assert.match(hiddenRegion, /x-show="!hiddenLoading && !!hiddenError"/, '错误提示行的 !! 丢了');
  assert.match(hiddenRegion, /x-show="!!hiddenAcceptance"/, '「已保存」徽标的 !! 丢了');
  assert.match(HTML, /x-show="!!hiddenPreview"/, '照片浮层的 !! 丢了');
});

test('产品文案只说「已验收 / 已保存」，不写「具有法律效力」', () => {
  const text = ADDRESS_SRC + HTML;
  assert.ok(!/具有法律效力|法律效力|可靠电子签名/.test(text),
    '文案越界了：三项结论 + 照片只构成施工记录，不构成任何效力承诺');
  // 不做业主签认（产品决策）：隐蔽工程面板里不能出现签认入口
  assert.ok(!/requestSignoffToken/.test(hiddenRegion),
    '隐蔽工程不做业主签认，面板里不该出现签认入口');
});

// =====================================================================
// 8. 契约对账 / 红线守卫
// =====================================================================

test('调用的端点与契约 hiddenwork v1 逐条对得上', () => {
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + addressId + '/hidden-acceptance'"), 'H1 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + aid + '/hidden-acceptance'"), 'H2 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + aid + '/hidden-media'"), 'H3 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + aid + '/hidden-media/' + mid"), 'H4 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/api/share/address/' + aid + '/hidden-media/' + mid"), 'H5 路径不对（单数 address）');
  // H2 必须是 POST（errata HW-1）
  assert.match(ADDRESS_SRC, /saveHiddenAcceptance\(\)[\s\S]{0,600}?accountJSON\('\/addresses\/' \+ aid \+ '\/hidden-acceptance', this\.hiddenPayload\(\)\)/);
  // H4 必须是 DELETE，且走 sessionRequest（accountJSON 发不出 DELETE）
  assert.match(ADDRESS_SRC, /accountDelete\(path\)[\s\S]{0,400}?sessionRequest\(path, \{ method: 'DELETE' \}\)/);
});

test('用到的字段名全部来自契约，没有自造字段', () => {
  const combined = ADDRESS_SRC + HTML;
  for (const field of ['item_key', 'label', 'hint', 'result', 'na_reason', 'note', 'photos', 'revision', 'accepted_at', 'acceptor_name']) {
    assert.ok(combined.includes(field), '契约字段没被用上（或拼错了）：' + field);
  }
  assert.match(ADDRESS_SRC, /accepted_at:/);
  assert.match(ADDRESS_SRC, /\brevision:/);
  assert.match(ADDRESS_SRC, /\bitems:/);
  assert.match(ADDRESS_SRC, /\bnote:/);
});

test('契约常量与前端常量一致', () => {
  assert.match(ADDRESS_SRC, /HIDDEN_NA_REASON_MIN:\s*2/);
  assert.match(ADDRESS_SRC, /HIDDEN_NA_REASON_LIMIT:\s*200/);
  assert.match(ADDRESS_SRC, /HIDDEN_NOTE_LIMIT:\s*200/);
  assert.match(ADDRESS_SRC, /HIDDEN_PHOTOS_PER_ITEM_MAX:\s*8/);
  assert.match(ADDRESS_SRC, /HIDDEN_PHOTO_DATA_URL_CEILING:\s*15029588/);
});

test('红线：前端不发裸 fetch、不硬编码域名、不算摘要', () => {
  // 写请求一律走 accountJSON / accountDelete（它们负责加 X-CSRF-Token）
  assert.ok(!/\bfetch\s*\(/.test(ADDRESS_SRC), 'address-client.js 不该自己发 fetch');
  assert.ok(!/https?:\/\/(?!cj-az\.cn)/.test(ADDRESS_SRC.replace(/https:\/\/cj-az\.cn/g, '')), '出现了硬编码域名');
  assert.ok(!/sha256|digest\s*[:=]/i.test(ADDRESS_SRC), '摘要不属于前端');
  // EXIF/GPS 剥离是后端 normalize_photo 的职责，前端不许自己引库去处理
  // （注释里提到它是说明，不算违规；这里只查代码里的库/API 调用）
  assert.ok(!/exifr|piexif|getExif|EXIF\.|gps\./i.test(ADDRESS_SRC), '前端在解析 EXIF/GPS —— 那是后端 normalize_photo 的职责');
});

// ---------- 跨仓库守卫 ----------

/** 把 JS/Python 字面量（单引号字符串 + 裸键）转成 JSON 再解析。 */
function parseLiteral(text) {
  return JSON.parse(String(text)
    .replace(/'/g, '"')
    .replace(/([{,]\s*)([A-Za-z_]\w*)\s*:/g, '$1"$2":'));
}

test('跨仓库守卫：前端常量与后端 hidden_work.py 一致（SITELOG_BACKEND 未设置时跳过）', () => {
  // 这条是**跨仓库**守卫，只在后端 CI（会把两个仓库并排 checkout）里生效。
  // 本地/前端 CI 没有后端源码时直接跳过，不制造假红。
  const backend = process.env.SITELOG_BACKEND;
  if (!backend) {
    console.log('  跳过：未设置 SITELOG_BACKEND（跨仓库守卫只在后端 CI 里生效）');
    return;
  }
  const src = fs.readFileSync(path.join(backend, 'hidden_work.py'), 'utf8');

  // 三项的 key：从 ITEMS 元组里抽，顺序也要一致（标准强制项，不允许改序）
  const itemsBlock = (src.match(/^ITEMS\s*=\s*\(([\s\S]*?)^\)/m) || [])[1];
  assert.ok(itemsBlock, '没读到后端 hidden_work.ITEMS');
  const keys = [...itemsBlock.matchAll(/"key"\s*:\s*"([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual(keys, CONTRACT_ITEM_KEYS, '后端 ITEMS 的三项 key 与契约不符（或顺序变了）');
  assert.deepEqual(
    parseLiteral(ADDRESS_SRC.match(/HIDDEN_ITEM_KEYS:\s*(\[[^\]]*\])/)[1]),
    keys,
    '前端 HIDDEN_ITEM_KEYS 与后端 hidden_work.ITEMS 的 key 不一致 —— 形状兜底会误报',
  );

  // 三项的 label：前端不许有第二份（上面已守卫），这里再确认后端确实提供了它们
  const labels = [...itemsBlock.matchAll(/"label"\s*:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(labels, CONTRACT_ITEM_LABELS, '后端 ITEMS 的 label 与契约不符');

  const num = (name) => {
    const m = src.match(new RegExp('^' + name + '\\s*=\\s*([0-9_]+)', 'm'));
    assert.ok(m, '没读到后端常量 ' + name);
    return Number(m[1].replace(/_/g, ''));
  };
  const frontNum = (name) => {
    const m = ADDRESS_SRC.match(new RegExp(name + ':\\s*(\\d+)'));
    assert.ok(m, '没读到前端常量 ' + name);
    return Number(m[1]);
  };
  assert.equal(frontNum('HIDDEN_NA_REASON_MIN'), num('NA_REASON_MIN'),
    '前端「不适用理由」下限与后端 NA_REASON_MIN 不一致');
  assert.equal(frontNum('HIDDEN_PHOTOS_PER_ITEM_MAX'), num('PHOTOS_PER_ITEM_MAX'),
    '前端每项照片上限与后端 PHOTOS_PER_ITEM_MAX 不一致');
  assert.equal(frontNum('HIDDEN_NA_REASON_LIMIT'), num('NA_REASON_LIMIT'),
    '前端不适用理由上限与后端 NA_REASON_LIMIT 不一致');
  assert.equal(frontNum('HIDDEN_NOTE_LIMIT'), num('NOTE_LIMIT'),
    '前端说明/备注上限与后端 NOTE_LIMIT 不一致');

  // 结论显示名：后端 RESULT_LABELS 是这三条的唯一定义处
  const backendLabels = parseLiteral((src.match(/^RESULT_LABELS\s*=\s*(\{[^}]*\})/m) || [])[1]);
  assert.ok(backendLabels, '没读到后端 RESULT_LABELS');
  const frontLabels = parseLiteral(ADDRESS_SRC.match(/HIDDEN_RESULT_LABELS:\s*(\{[^}]*\})/)[1]);
  assert.deepEqual(frontLabels, backendLabels, '前端结论显示名与后端 RESULT_LABELS 不一致');

  // 错误文案：前端预校验的措辞必须与后端能对上，否则员工看到两套说法
  assert.ok(src.includes('请为「') && src.includes('」至少上传 1 张照片'), '后端缺照片文案变了');
  assert.ok(src.includes('请写明「') && src.includes('」不适用的理由（至少 '), '后端不适用理由文案变了');
  assert.ok(src.includes('请填写全部三项验收结论，缺少：'), '后端缺项文案变了');
});
