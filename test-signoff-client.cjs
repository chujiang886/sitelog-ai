#!/usr/bin/env node
/*
 * 客户签认（contract signoff v1）员工侧前端测试。
 *
 * 【为什么必须单独测这一块】
 * 签认这套东西的失败方式和别处不一样：它错了**不会报错**，只会让「证据」变得不可信。
 *
 *   - 令牌过期了界面还在显示二维码 → 业主扫了打不开，员工以为递出去就完事了
 *   - 前端自己拼签认链接 → 换域名后二维码指向不存在的页面，而二维码已经打印/递出去了
 *   - 前端自己算 digest → 得到的是「和证据不是同一个值」的第二个数字
 *   - 撤回原因空着就提交 → 日后没人知道为什么撤的（后端会 400，但员工白等一个来回）
 *   - 后端 409「此阶段已签认」被前端换成自编文案 → 员工拿着前端文案去问后端，两边说的不是一回事
 *   - stale 提示漏渲染 → 签认后档案又改过，双方都以为签认覆盖的是现在看到的内容
 *
 * 所以这里既跑纯逻辑，也做 index.html 的结构守卫（这类问题截图看不出来）。
 *
 * 用法：node test-signoff-client.cjs
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const HTML = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const ADDRESS_SRC = fs.readFileSync(path.join(__dirname, 'address-client.js'), 'utf8');
// 与 test-share.cjs 同一套取法：只抓无属性的 <script>，最后一个就是 siteLogApp() 所在的大块。
const inlineScripts = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)];

// 阶段名真源在 address-client.js 顶部；测试里这一份只用来断言「index.html 没再抄一遍」。
const STAGE_NAMES = ['吊装施工', '框架施工', '框架1对1', '玻扇施工', '玻扇1对1', '五金安装', '离场自检', '售后保养'];

// ---------- 沙箱 ----------

function makeCanvasStub() {
  const ops = [];
  return {
    ops, width: 0, height: 0, style: {},
    getContext: () => ({
      fillStyle: '', fillRect: (...a) => ops.push(['fillRect', ...a]),
      fillText: () => {}, measureText: () => ({ width: 0 }),
    }),
  };
}

/**
 * 建一个能跑 siteLogApp() 的沙箱。
 * 定时器全部换成假的：真 setInterval 会把 node 进程挂住不退出，
 * 而倒计时逻辑本身只依赖 signoffExpires，不需要真的等一秒。
 */
function makeApp(fetchImpl, opts = {}) {
  const calls = [];
  const canvas = makeCanvasStub();
  const encoded = { value: null };
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
      getElementById: (id) => (id === 'signoff-qr-canvas' ? canvas : null),
      createElement: () => ({ click() {}, remove() {}, select() {}, style: {} }),
      body: { appendChild() {} },
      execCommand: () => true,
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'auth-client.js'), 'utf8'), context, { filename: 'auth-client.js' });
  vm.runInContext(ADDRESS_SRC, context, { filename: 'address-client.js' });
  vm.runInContext(inlineScripts.at(-1)[1], context, { filename: 'index.html:<last inline script>' });

  // 二维码组件：本页已有 window.qrcode，记录它被喂进去的字符串——
  // 「编码的是不是后端返回的 url」只能这样钉住。
  context.window.qrcode = () => ({
    addData: (d) => { encoded.value = d; },
    make: () => {}, getModuleCount: () => 21, isDark: (r, c) => (r + c) % 2 === 0,
  });

  const app = context.siteLogApp();
  app.showToast = () => {};       // 默认静音；要断言提示的用例自己换掉
  app.calls = calls;
  app.qrCanvas = canvas;
  app.qrEncoded = encoded;
  if (opts.addressId) app.addressDetail = { id: opts.addressId, label: '观海花园 3 栋 2201' };
  return app;
}

const okJson = (body, status = 200) => ({ status, ok: true, json: async () => body });
const errJson = (body, status) => ({ status, ok: false, json: async () => body });

const TOKEN_OK = {
  ok: true, token: 'T'.repeat(43), url: 'https://cj-az.cn/sign/TOKEN123',
  expires: 1000300, kind: 'stage', stage_key: '框架施工', slot: 0,
};

// ---------- 1. 生成令牌：state 里出现链接与过期时间 ----------

test('生成阶段签认令牌：state 里出现链接与过期时间，链接只用后端返回的 url', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201), { addressId: 'addr1' });
  app.csrf = 'test-csrf';

  await app.requestSignoffToken('stage', '框架施工', 0);

  assert.equal(app.signoffUrl, 'https://cj-az.cn/sign/TOKEN123', '链接必须原样来自后端 url');
  assert.equal(app.signoffExpires, 1000300);
  assert.equal(app.signoffToken, 'T'.repeat(43));
  assert.equal(app.signoffKind, 'stage');
  assert.equal(app.signoffStageKey, '框架施工');
  assert.equal(app.signoffSlot, 0);
  assert.equal(app.signoffLabel, '框架归档记录', '签认范围要念得出来（后端没给 label 时退回本地阶段显示名）');
  assert.equal(app.signoffPanelOpen, true);
  assert.equal(app.signoffQrError, '');
  assert.equal(app.signoffBusy, false, '请求结束后必须解除 busy，否则按钮永久禁用');

  // 请求本身：路径 / 方法 / body / CSRF
  assert.equal(app.calls.length, 1);
  const call = app.calls[0];
  assert.equal(call.url, '/api/share/addresses/addr1/signoff-token');
  assert.equal(call.options.method, 'POST');
  assert.deepEqual(JSON.parse(call.options.body), { kind: 'stage', stage_key: '框架施工', slot: 0 });
  assert.equal(call.options.headers['X-CSRF-Token'], 'test-csrf', '写请求必须带 X-CSRF-Token');
  assert.equal(call.options.credentials, 'same-origin');
});

test('整址竣工验收签认：kind=final，范围显示名用后端 label', async () => {
  // 后端 token() 会回 label（final → 「整址竣工验收签认」），前端优先用它。
  const app = makeApp(async () => okJson(
    { ...TOKEN_OK, kind: 'final', stage_key: '', slot: 0, label: '整址竣工验收签认' }, 201,
  ), { addressId: 'addr1' });

  await app.requestSignoffToken('final');

  assert.equal(app.signoffKind, 'final');
  assert.equal(app.signoffStageKey, '');
  assert.equal(app.signoffSlot, 0);
  assert.equal(app.signoffLabel, '整址竣工验收签认', '有后端 label 时必须用它');
  const body = JSON.parse(app.calls[0].options.body);
  assert.equal(body.kind, 'final');
  // final 也带上 stage_key/slot 的空默认值（契约表里两者有 DEFAULT ''/0，且规则写明忽略）
  assert.equal(body.stage_key, '');
  assert.equal(body.slot, 0);
});

test('二维码编码的就是后端返回的 url，用的是本页已有的 window.qrcode', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201), { addressId: 'addr1' });

  await app.requestSignoffToken('stage', '框架施工', 0);

  assert.equal(app.qrEncoded.value, 'https://cj-az.cn/sign/TOKEN123', '二维码里编码的必须是后端给的 url');
  assert.ok(app.qrCanvas.ops.some((op) => op[0] === 'fillRect'), '二维码没画到 canvas 上');
});

test('二维码绘制失败时链接不能跟着丢，只提示改用链接', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201), { addressId: 'addr1' });
  app.drawSignoffQr = async () => { throw new Error('二维码组件未就绪，请改用下方链接'); };

  await app.requestSignoffToken('stage', '框架施工', 0);

  assert.equal(app.signoffUrl, 'https://cj-az.cn/sign/TOKEN123', '画不出二维码也要保住链接');
  assert.match(app.signoffQrError, /二维码/);
  assert.equal(app.signoffPanelOpen, true);
});

test('连点两次「请业主签认」只发一次请求', async () => {
  let release;
  let posts = 0;
  const app = makeApp(() => { posts++; return new Promise((r) => { release = r; }); }, { addressId: 'addr1' });

  const first = app.requestSignoffToken('stage', '框架施工', 0);
  await app.requestSignoffToken('stage', '框架施工', 0);   // 第二次点在 busy 期间
  assert.equal(posts, 1, '防重复提交失效：连点会生成两张令牌');

  release(okJson(TOKEN_OK, 201));
  await first;
  assert.equal(app.signoffBusy, false);
});

// ---------- 2. 倒计时到期 ----------

test('倒计时由后端 expires 反推，到期后标记失效并停表', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201), { addressId: 'addr1' });
  await app.requestSignoffToken('stage', '框架施工', 0);

  app.signoffNow = 1000;
  app.signoffExpires = 1300;
  assert.equal(app.signoffExpired(), false);
  assert.equal(app.signoffRemaining(), 300);
  assert.equal(app.signoffCountdownText(), '05:00');

  app.signoffNow = 1299;
  assert.equal(app.signoffCountdownText(), '00:01');

  app.signoffNow = 1300;
  assert.equal(app.signoffRemaining(), 0);
  assert.equal(app.signoffCountdownText(), '00:00');
  assert.equal(app.signoffExpired(), true);

  // 到期那一拍要把表停掉，但不许自动关面板——
  // 自动关掉的话员工只看到面板消失，会以为二维码已经发出去了。
  app.signoffTimer = { fn: () => {}, ms: 1000 };
  app.signoffTick();
  assert.equal(app.signoffTimer, null, '到期后定时器没停');
  assert.equal(app.signoffPanelOpen, true, '到期不该自动关面板，要让人看到「请重新生成」');
});

test('没有 expires 时按「已失效」处理，不显示一个能扫的二维码', () => {
  const app = makeApp(async () => okJson({ ok: true }), { addressId: 'addr1' });
  assert.equal(app.signoffExpires, 0);
  assert.equal(app.signoffExpired(), true);
  assert.equal(app.signoffRemaining(), 0);
});

test('关掉面板等于这张令牌作废：链接与过期时间一起清掉', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201), { addressId: 'addr1' });
  await app.requestSignoffToken('stage', '框架施工', 0);

  app.closeSignoffPanel();

  assert.equal(app.signoffPanelOpen, false);
  assert.equal(app.signoffUrl, '');
  assert.equal(app.signoffExpires, 0);
  assert.equal(app.signoffTimer, null);
});

// ---------- 3. 签认记录列表 ----------

const SIGN_OFFS = [
  {
    id: 'a'.repeat(32), kind: 'stage', stage_key: '框架施工', stage_label: '框架归档记录', slot: 0,
    signer_name: '张三', signer_phone: '13800138000', has_stroke: true, witness: 1, witness_name: '李工',
    created: 1780000000, digest: 'd'.repeat(64), stale: true, revoked: false,
    revoke_note: '', revoked_at: null, revoked_by_name: '',
  },
  {
    id: 'b'.repeat(32), kind: 'final', stage_key: '', stage_label: '', slot: 0,
    signer_name: '张三', signer_phone: '13800138000', has_stroke: true, witness: 2, witness_name: '王工',
    created: 1770000000, digest: 'e'.repeat(64), stale: false, revoked: false,
    revoke_note: '', revoked_at: null, revoked_by_name: '',
  },
  {
    id: 'c'.repeat(32), kind: 'stage', stage_key: '售后保养', stage_label: '售后保养施工归档', slot: 1,
    signer_name: '李四', signer_phone: '13900139000', has_stroke: false, witness: 1, witness_name: '李工',
    created: 1760000000, digest: 'f'.repeat(64), stale: false, revoked: true,
    revoke_note: '业主反映漏拍了厨房推拉门', revoked_at: 1761000000, revoked_by_name: '王工',
  },
];

test('签认记录：拉取 items、范围显示名、时间、笔迹图地址', async () => {
  const app = makeApp(async () => okJson({ ok: true, items: SIGN_OFFS }), { addressId: 'addr1' });

  await app.loadSignoffs('addr1');

  assert.equal(app.signoffLoading, false);
  assert.equal(app.signoffError, '');
  assert.equal(app.signoffItems.length, 3, '含已撤回的记录也要列出来');
  assert.equal(app.calls[0].url, '/api/share/addresses/addr1/signoffs');
  assert.equal(app.calls[0].options.method, undefined, '读取签认记录必须是 GET，不能带 method');

  // 范围显示名：后端 stage_label 优先（与业主页、后端文案同源）
  assert.equal(app.signoffRangeLabel(app.signoffItems[0]), '框架归档记录');
  assert.equal(app.signoffRangeLabel({ kind: 'final', stage_label: '整址竣工验收签认' }), '整址竣工验收签认',
    '后端给的名字必须优先，否则列表和二维码面板会各叫一个名');
  // 后端没给 stage_label 时才退回本地文案
  assert.equal(app.signoffRangeLabel(app.signoffItems[1]), '整址竣工验收');
  assert.equal(app.signoffRangeLabel({ kind: 'stage', stage_key: '售后保养' }), '售后保养施工归档');
  assert.equal(app.signoffRangeLabel(null), '');

  // 时间
  assert.match(app.signoffTimeText(app.signoffItems[0].created), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.equal(app.signoffTimeText(null), '—');

  // 笔迹图：同源路径，session cookie 自动带上（契约 A3 要求 require_session）
  assert.equal(app.signoffStrokeUrl(app.signoffItems[0]), '/api/share/signoffs/' + 'a'.repeat(32) + '/stroke');

  // 已撤回那条的撤回信息要能取到（模板靠这三个字段渲染置灰说明）
  const revoked = app.signoffItems[2];
  assert.equal(revoked.revoked, true);
  assert.equal(revoked.revoke_note, '业主反映漏拍了厨房推拉门');
  assert.equal(revoked.revoked_by_name, '王工');
  assert.equal(app.signoffTimeText(revoked.revoked_at).length, 16);

  // stale 徽标的数据来源
  assert.equal(app.signoffItems[0].stale, true);
  assert.equal(app.signoffItems[1].stale, false);
});

test('签认记录读取失败时进 error 态，不留空列表冒充「没有记录」', async () => {
  const app = makeApp(async () => errJson({ ok: false, error: '无权访问该地址' }, 403), { addressId: 'addr1' });

  await app.loadSignoffs('addr1');

  assert.equal(app.signoffLoading, false);
  assert.equal(app.signoffItems.length, 0);
  assert.equal(app.signoffError, '无权访问该地址', '后端文案要透出，不能吞掉');
});

test('切地址时迟到的旧响应不覆盖新地址的签认记录', async () => {
  let release;
  const app = makeApp(() => new Promise((r) => { release = r; }), { addressId: 'addrA' });
  app.signoffItems = [{ id: 'x'.repeat(32) }];

  const pending = app.loadSignoffs('addrA');
  app.addressDetail = { id: 'addrB' };            // 员工已经切到另一户
  release(okJson({ ok: true, items: SIGN_OFFS }));

  await pending;
  assert.equal(app.signoffItems.length, 1, 'A 户的记录不能落到 B 户详情里');
});

// ---------- 4. 撤回 ----------

test('撤回未填原因时不发请求，并给出员工能看懂的原因', async () => {
  const app = makeApp(async () => okJson({ ok: true }), { addressId: 'addr1' });
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });

  app.openSignoffRevoke({ id: 's1' });
  assert.equal(app.signoffRevokeId, 's1');
  assert.equal(app.signoffRevokeNote, '');

  await app.submitSignoffRevoke({ id: 's1' });
  assert.equal(app.calls.length, 0, '空原因不该发请求');
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].type, 'error');
  assert.match(toasts[0].msg, /撤回原因/);
  assert.equal(app.signoffRevokeBusy, false);

  // 只输空白字符同样算没填
  app.signoffRevokeNote = '   ';
  await app.submitSignoffRevoke({ id: 's1' });
  assert.equal(app.calls.length, 0, '纯空白不该发请求');

  // 超过契约 REVOKE_NOTE_LIMIT(500) 也先挡下
  app.signoffRevokeNote = '原'.repeat(501);
  await app.submitSignoffRevoke({ id: 's1' });
  assert.equal(app.calls.length, 0, '超长原因不该发请求');
  assert.match(toasts[2].msg, /500/);

  // 下限是 2 而不是 1：后端 `REVOKE_NOTE_MIN` 就是 2，前端必须用同一个下限。
  // 只挡空串的话，员工填一个「错」字会被后端 400 打回来，白等一个来回。
  app.signoffRevokeNote = '错';
  await app.submitSignoffRevoke({ id: 's1' });
  assert.equal(app.calls.length, 0, '1 个字的原因不该发请求（后端会 400）');
  assert.match(toasts[3].msg, /2/);
  assert.equal(app.signoffRevokeNoteLength(), 1);

  // 字数计数器（界面上的「已填 N / 500 字」）
  app.signoffRevokeNote = '漏拍厨房';
  assert.equal(app.signoffRevokeNoteLength(), 4);
});

test('撤回原因下限与后端 REVOKE_NOTE_MIN 一致（跨仓库守卫）', () => {
  // 这条是**跨文件**守卫：前端的下限不能低于后端 signoffs.REVOKE_NOTE_MIN。
  // 后端仓库不在场时跳过——它只在后端 CI（会把两个仓库并排 checkout）里生效。
  const backend = process.env.SITELOG_BACKEND;
  if (!backend) return;
  const src = fs.readFileSync(path.join(backend, 'signoffs.py'), 'utf8');
  const min = Number((src.match(/REVOKE_NOTE_MIN\s*=\s*(\d+)/) || [])[1]);
  assert.ok(min >= 1, '没读到后端 REVOKE_NOTE_MIN');
  assert.equal(ADDRESS_SRC.match(/SIGNOFF_REVOKE_NOTE_MIN:\s*(\d+)/)[1], String(min),
    '前端撤回原因下限与后端 signoffs.REVOKE_NOTE_MIN 不一致');
});

test('撤回表单要写清楚作用在哪一条上（列表外的表单靠这句对应）', async () => {
  const app = makeApp(async () => okJson({ ok: true, items: SIGN_OFFS }), { addressId: 'addr1' });
  await app.loadSignoffs('addr1');

  assert.equal(app.signoffRevokeLabel(), '', '没选任何一条时是空串，不是 undefined');
  app.openSignoffRevoke(app.signoffItems[0]);
  assert.equal(app.signoffRevokeLabel(), '框架归档记录 · 张三');
  app.openSignoffRevoke(app.signoffItems[1]);
  assert.equal(app.signoffRevokeLabel(), '整址竣工验收 · 张三');
  // 指向一条已经不存在的记录时不报错
  app.signoffRevokeId = 'zzz';
  assert.equal(app.signoffRevokeLabel(), '');
});

test('撤回表单不带 row 参数也能提交（表单渲染在列表外）', async () => {
  const app = makeApp(async (url) => (
    /\/revoke$/.test(url) ? okJson({ ok: true }) : okJson({ ok: true, items: SIGN_OFFS })
  ), { addressId: 'addr1' });
  await app.loadSignoffs('addr1');
  app.openSignoffRevoke(app.signoffItems[2]);
  app.signoffRevokeNote = '撤回后补档重签';

  await app.submitSignoffRevoke();     // 模板里就是这么调的

  const revoke = app.calls.find((c) => /\/revoke$/.test(c.url));
  assert.ok(revoke, '不带 row 参数时没发出撤回请求：' + JSON.stringify(app.calls.map((c) => c.url)));
  assert.equal(revoke.url, '/api/share/signoffs/' + 'c'.repeat(32) + '/revoke');
  assert.deepEqual(JSON.parse(revoke.options.body), { note: '撤回后补档重签' });
  assert.equal(app.signoffRevokeId, '');
});

test('刷新后目标记录不在清单里时收起撤回表单，不留空壳输入框', async () => {
  const app = makeApp(async () => okJson({ ok: true, items: [SIGN_OFFS[0]] }), { addressId: 'addr1' });
  app.openSignoffRevoke(SIGN_OFFS[2]);       // 指向一条刷新后不会出现的记录
  app.signoffRevokeNote = '写了一半';

  await app.loadSignoffs('addr1');

  assert.equal(app.signoffRevokeId, '');
  assert.equal(app.signoffRevokeNote, '');
});

test('撤回成功后提交 {note} 并重新拉取签认记录', async () => {
  const app = makeApp(async (url) => (
    /\/revoke$/.test(url) ? okJson({ ok: true }) : okJson({ ok: true, items: [] })
  ), { addressId: 'addr1' });

  app.openSignoffRevoke({ id: 's1' });
  app.signoffRevokeNote = '  业主反映漏拍厨房推拉门  ';   // 前后空白应被 trim
  await app.submitSignoffRevoke({ id: 's1' });

  assert.equal(app.calls.length, 2);
  assert.equal(app.calls[0].url, '/api/share/signoffs/s1/revoke');
  assert.equal(app.calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(app.calls[0].options.body), { note: '业主反映漏拍厨房推拉门' });
  assert.equal(app.calls[1].url, '/api/share/addresses/addr1/signoffs', '撤回后要刷新记录，否则界面还显示「未撤回」');
  assert.equal(app.signoffRevokeId, '', '成功后要收起原因输入框');
  assert.equal(app.signoffRevokeBusy, false);
});

test('撤回按钮连点只提交一次', async () => {
  let release;
  let posts = 0;
  const app = makeApp(async (url) => {
    if (/\/revoke$/.test(url)) { posts++; return new Promise((r) => { release = r; }); }
    return okJson({ ok: true, items: [] });   // 撤回成功后的记录刷新
  }, { addressId: 'addr1' });
  app.openSignoffRevoke({ id: 's1' });
  app.signoffRevokeNote = '漏拍厨房推拉门';

  const first = app.submitSignoffRevoke({ id: 's1' });
  await app.submitSignoffRevoke({ id: 's1' });
  assert.equal(posts, 1);

  release(okJson({ ok: true }));
  await first;
  assert.equal(app.signoffRevokeBusy, false);
});

// ---------- 5. 后端错误文案原样透出 ----------

test('409「此阶段已签认」原样透出后端文案，前端不另编话术', async () => {
  const app = makeApp(async () => errJson({ ok: false, error: '此阶段已签认，如需重新签认请先撤回' }, 409), { addressId: 'addr1' });
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });

  await app.requestSignoffToken('stage', '框架施工', 0);

  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].msg, '此阶段已签认，如需重新签认请先撤回');
  assert.equal(toasts[0].type, 'error');
  assert.equal(app.signoffPanelOpen, false, '失败不能弹出空二维码面板');
  assert.equal(app.signoffUrl, '');
  assert.equal(app.signoffBusy, false);
});

test('403 撤回被拒（需另一位员工复核）原样透出', async () => {
  const app = makeApp(async () => errJson({ ok: false, error: '撤回需要另一位员工复核，请让同事操作' }, 403), { addressId: 'addr1' });
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.openSignoffRevoke({ id: 's1' });
  app.signoffRevokeNote = '漏拍厨房推拉门';

  await app.submitSignoffRevoke({ id: 's1' });

  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].msg, '撤回需要另一位员工复核，请让同事操作');
  assert.equal(app.signoffRevokeBusy, false);
  assert.equal(app.signoffRevokeId, 's1', '失败时保留输入框，别把员工写的原因清掉');
  assert.equal(app.signoffRevokeNote, '漏拍厨房推拉门');
});

test('没有 addressDetail 时不发令牌请求', async () => {
  const app = makeApp(async () => okJson(TOKEN_OK, 201));
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });

  await app.requestSignoffToken('stage', '框架施工', 0);

  assert.equal(app.calls.length, 0);
  assert.equal(toasts.length, 1);
  assert.equal(app.signoffBusy, false);
});

// ---------- 6. 状态隔离 ----------

test('关掉地址面板时二维码层一并关掉，不留悬挂的一层', () => {
  const app = makeApp(async () => okJson({ ok: true }), { addressId: 'addr1' });
  app.addressPanel = true;
  app.signoffPanelOpen = true;
  app.signoffUrl = 'https://cj-az.cn/sign/t';
  app.signoffRevokeId = 's1';
  app.signoffRevokeNote = '写了半句';

  app.closeAddressPanel();

  assert.equal(app.signoffPanelOpen, false);
  assert.equal(app.addressPanel, false);
  assert.equal(app.signoffUrl, '');
  assert.equal(app.signoffRevokeId, '');
});

test('切地址时上一户的签认状态全部复位', () => {
  const app = makeApp(async () => okJson({ ok: true }), { addressId: 'addr1' });
  app.signoffPanelOpen = true;
  app.signoffUrl = 'https://cj-az.cn/sign/t';
  app.signoffItems = [{ id: 'x'.repeat(32) }];
  app.signoffRevokeNote = '半句';

  app.resetSignoffState();

  assert.equal(app.signoffPanelOpen, false);
  assert.equal(app.signoffUrl, '');
  assert.equal(app.signoffItems.length, 0);
  assert.equal(app.signoffRevokeNote, '');
  assert.equal(app.signoffTimer, null);
});

// ---------- 7. 契约对账 / 红线守卫 ----------

test('调用的端点与契约 signoff v1 逐条对得上', () => {
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + this.addressDetail.id + '/signoff-token'"), 'A1 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/addresses/' + addressId + '/signoffs'"), 'A2 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/signoffs/' + sid + '/revoke'"), 'A4 路径不对');
  assert.ok(ADDRESS_SRC.includes("'/api/share/signoffs/' + row.id + '/stroke'"), 'A3 路径不对');
  // 契约常量：撤回原因上限 500（REVOKE_NOTE_LIMIT）
  assert.match(ADDRESS_SRC, /SIGNOFF_REVOKE_NOTE_MAX:\s*500/);
});

test('用到的字段名全部来自契约，没有自造字段', () => {
  const combined = ADDRESS_SRC + HTML;
  for (const field of [
    'signer_name', 'signer_phone', 'has_stroke', 'witness_name', 'stage_label',
    'stale', 'revoked', 'revoke_note', 'revoked_at', 'revoked_by_name',
  ]) {
    assert.ok(combined.includes(field), '契约字段没被用上（或拼错了）：' + field);
  }
  // 请求体字段
  assert.match(ADDRESS_SRC, /kind:\s*'final'/);
  assert.match(ADDRESS_SRC, /kind:\s*'stage'/);
  assert.match(ADDRESS_SRC, /stage_key:/);
  assert.match(ADDRESS_SRC, /\bslot:/);
  assert.match(ADDRESS_SRC, /\{\s*note\s*\}/);
});

test('红线：前端不拼签认链接、不算 digest/manifest、不发裸 fetch', () => {
  // 不拼公开页地址：链接只能来自后端 data.url
  assert.ok(!/['"]\/sign\//.test(ADDRESS_SRC), '出现了前端自己拼 /sign/<token> 的写法');
  assert.match(ADDRESS_SRC, /this\.signoffUrl = data\.url/);
  // 不算摘要：digest / manifest 只能由服务端在签认瞬间冻结
  assert.ok(!/\bdigest\s*[:=]/.test(ADDRESS_SRC), '前端在算 digest');
  assert.ok(!/\bmanifest\s*[:=]/.test(ADDRESS_SRC), '前端在拼 manifest');
  assert.ok(!/sha256/i.test(ADDRESS_SRC), '前端出现了 sha256 —— 摘要不属于前端');
  // 写请求一律走 accountJSON（它负责加 X-CSRF-Token）；裸 fetch 会漏掉 CSRF
  assert.ok(!/\bfetch\s*\(/.test(ADDRESS_SRC), 'address-client.js 不该自己发 fetch');
  // 不调外部二维码 API
  assert.ok(!/qrserver|googleapis|chart\.api|quickchart/i.test(ADDRESS_SRC + HTML), '引用了外部二维码/图表服务');
  // 不硬编码域名
  assert.ok(!/https?:\/\/(?!cj-az\.cn\/sign\/TOKEN123)/.test(ADDRESS_SRC.replace(/https:\/\/cj-az\.cn/g, '')), '出现了硬编码域名');
});

test('index.html：签认入口挂在每一条留档上，阶段名不抄第二份', () => {
  assert.match(HTML, /requestSignoffToken\('stage',\s*stage\.stage_key,\s*stage\.slot\)/, '阶段签认入口没带 stage_key/slot');
  assert.match(HTML, /requestSignoffToken\('final'\)/, '整址竣工验收入口缺失');
  // 已隐藏的阶段后端要求 visible=1，点必然 404 —— 入口只在可见时给
  assert.match(HTML, /x-show="stage\.visible"[\s\S]{0,300}?requestSignoffToken\('stage'/);

  // 签认区块里不能出现具体阶段名（真源在 address-client.js 的 ADDRESS_STAGE_KEYS）
  const start = HTML.indexOf('<!-- ===== 客户签认（signoff v1）=====');
  const end = HTML.indexOf('<!-- ========== 存量归类');
  assert.ok(start > 0 && end > start, '找不到签认区块的边界，守卫失效');
  const region = HTML.slice(start, end);
  for (const name of STAGE_NAMES) {
    assert.ok(!region.includes(name), '签认区块里抄了一份阶段名：' + name);
  }
});

test('index.html：stale 徽标、已撤回置灰、撤回入口三态都在位', () => {
  // stale 徽标：签认后档案又改过，必须显眼提示
  assert.match(HTML, /row\.stale\s*&&\s*!row\.revoked/);
  assert.match(HTML, /签认后该阶段档案已更新/);
  // 已撤回：置灰 + 撤回原因/撤回人/撤回时间
  assert.match(HTML, /:class="\[\(row\.revoked \? 'revoked' : ''\)/);
  assert.match(HTML, /\.signoff-row\.revoked\s*\{/);
  assert.match(HTML, /row\.revoke_note/);
  assert.match(HTML, /row\.revoked_by_name/);
  assert.match(HTML, /row\.revoked_at/);
  // 未撤回才给「撤回」按钮，已撤回显示灰字
  assert.match(HTML, /x-show="!row\.revoked"[\s\S]{0,200}?openSignoffRevoke\(row\)/);
  // 正在撤回的那条要高亮，表单在列表外，靠这圈高亮对应
  assert.match(HTML, /signoffRevokeId === row\.id \? 'picking' : ''/);
  assert.match(HTML, /\.signoff-row\.picking\s*\{/);
  // 笔迹缩略图：无笔迹时整块不渲染（x-show 会留着 src 照样发一次 404 请求）
  assert.match(HTML, /<template x-if="row\.has_stroke">[\s\S]{0,200}?signoffStrokeUrl\(row\)/);
});

test('撤回原因输入框只渲染一份，且不在 x-for 里', () => {
  const start = HTML.indexOf('<!-- ===== 客户签认（signoff v1）=====');
  const end = HTML.indexOf('<!-- ========== 存量归类');
  const region = HTML.slice(start, end);
  assert.equal((region.match(/x-model="signoffRevokeNote"/g) || []).length, 1,
    '撤回原因输入框只能有一份。放进 x-for 会变成每行一份：同一个 x-model、同一个 label，'
    + '读屏软件和「按标签找输入框」都会撞车');
  assert.match(region, /signoffRevokeLabel\(\)/, '撤回表单没写清楚作用在哪一条上');
  assert.match(region, /submitSignoffRevoke\(\)/, '列表外的表单没有 row 参数，要能不带参调用');
  assert.ok(ADDRESS_SRC.includes('signoffRevokeLabel()'), 'address-client.js 缺 signoffRevokeLabel');
});

test('index.html：倒计时与失效态、复制链接按钮都在位', () => {
  assert.match(HTML, /id="signoff-qr-canvas"/);
  assert.match(HTML, /signoffCountdownText\(\)/);
  assert.match(HTML, /链接已失效，请重新生成/);
  assert.match(HTML, /copySignoffUrl\(\)/);
  // 失效态里要有「重新生成」的出口，不能只报错
  assert.match(HTML, /signoffExpired\(\)[\s\S]{0,600}?requestSignoffToken\(signoffKind, signoffStageKey, signoffSlot\)/);
});

test('x-show 表达式不能混类型：Alpine 会对同一元素隐藏两次并抛未捕获错误', () => {
  // 踩过的坑（浏览器冒烟才抓得到，node 单测和截图都看不出来）：
  // `x-show="!signoffLoading && signoffError"` 在「初始 / 加载中 / 加载完成无错误」
  // 三种状态下依次求值为 `''` / `false` / `''`。值都是假，但类型在 string 和 boolean
  // 之间跳，而 Alpine 内部用 `p === l` 判断「值有没有变」，于是判定变了两次，
  // 对同一个元素连续走两次隐藏流程 —— 第二次 `_x_hidePromise` 已被删掉，
  // 抛 `TypeError: u is not a function`（vendor/alpine.min.js 内部，未捕获）。
  // 加 `!!` 之后三种状态恒为 false，判等成立，隐藏只走一次。
  assert.ok(!/x-show="[^"]*&&\s*(signoffError|signoffQrError|signoffUrl|signoffToken|signoffLabel|signoffRevokeId)\s*"/.test(HTML),
    'x-show 里把字符串字段直接当成 && 的右操作数 —— 必须用 !! 转成布尔');
  assert.match(HTML, /x-show="!signoffLoading && !!signoffError"/, '错误提示行的 !! 丢了');
});

test('产品文案只说「客户已确认」，不写「具有法律效力」', () => {
  const signoffText = ADDRESS_SRC + HTML;
  assert.ok(!/具有法律效力|法律效力|可靠电子签名/.test(signoffText),
    '签认文案越界了：手写笔迹+时间戳只构成「电子数据」，不构成可靠电子签名');
});
