#!/usr/bin/env node
/*
 * 材料与性能证明附件（contract materials v1）员工侧前端测试。
 *
 * 【为什么单独测】
 * ③ 的失败方式和 ② 一样隐蔽：错了不会报错，只会让「交付业主的那一份材料清单」
 * 变得不可信——类别传错、PDF 被压坏、材料串到另一户留档上、删材料却发成 POST。
 *
 *   - kind 不在契约 KINDS 内 → 业主文档视图按 KINDS 渲染，前端传个「其它」之外的值会被忽略
 *   - 前端自己抄一份 KINDS → 后端改了名、界面还印着旧名
 *   - title 不校验 → 空标题直接塞进「交付业主」的清单里
 *   - 非 PDF/图片也传 → 后端会 400，但员工不该等一个来回
 *   - 走 POST 删材料 → 后端判 command != 'DELETE' 直接 405，材料删不掉
 *   - 切地址没清缓存 → A 户某留档的材料出现在 B 户同名留档里
 *   - 上传前 compressDataUrl → PNG 透明底变黑、PDF 被重编码损坏（证明文件作废）
 *
 * 用法：node --test test-materials-client.cjs
 *       SITELOG_BACKEND=/path/to/chujiang-sitelog-share node --test test-materials-client.cjs
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const HTML = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const ADDRESS_SRC = fs.readFileSync(path.join(__dirname, 'address-client.js'), 'utf8');
const inlineScripts = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)];

// ---------- 跨仓库守卫：读后端契约（照 test-hidden-client.cjs）----------
const CONTRACT_PATH = process.env.SITELOG_BACKEND
  ? path.join(process.env.SITELOG_BACKEND, 'docs/contracts/materials.v1.json')
  : '/Users/chujiangai/repos/chujiang-sitelog-share/docs/contracts/materials.v1.json';
let contract = null;
try { contract = JSON.parse(fs.readFileSync(CONTRACT_PATH, 'utf8')); }
catch (e) { contract = null; }

// 面板区块边界（结构守卫都在这段里做）
const MAT_START = '<!-- ===== 材料与性能证明（materials v1）';
const hiddenRegion = HTML.slice(HTML.indexOf(MAT_START)); // 从材料区到文件末尾，足够覆盖本面板

const stripComments = (s) => s.replace(/<!--[\s\S]*?-->/g, '');

// ---------- 沙箱 ----------
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
  app.showToast = () => {};       // 默认静音
  app.calls = calls;
  app.csrf = 'test-csrf';
  if (opts.addressId) app.addressDetail = { id: opts.addressId, label: '观海花园 3 栋 2201' };
  return app;
}

const okJson = (body, status = 200) => ({ status, ok: true, json: async () => body });
const errJson = (body, status) => ({ status, ok: false, json: async () => body });
const tick = () => new Promise((resolve) => setImmediate(resolve));

// =====================================================================
// 1. 读取（契约 M2）
// =====================================================================

test('M2：拉取某留档材料清单，写入 addressMaterials[pid]，形状归一化成数组', async () => {
  const items = [
    { id: 'a'.repeat(32), kind: '合格证', title: '铝合金型材合格证', filename: 'cert.pdf', mime: 'application/pdf', size: 12345, created: 1 },
    { id: 'b'.repeat(32), kind: '检测报告', title: '气密性检测报告', filename: 'report.png', mime: 'image/png', size: 678, created: 2 },
  ];
  const app = makeApp(async () => okJson({ ok: true, items }));

  await app.loadMaterials('pid1');

  assert.equal(app.calls[0].url, '/api/share/publication/pid1/materials');
  assert.equal(app.calls[0].options.method, undefined, '读取必须是 GET，不能带 method');
  assert.equal(app.addressMaterials.pid1.loading, false);
  assert.equal(app.addressMaterials.pid1.error, '');
  assert.equal(app.addressMaterials.pid1.items.length, 2);
  assert.equal(app.addressMaterials.pid1.items[0].id, 'a'.repeat(32));
  assert.equal(app.addressMaterials.pid1.items[1].kind, '检测报告');

  // 后端返回 items 缺失/非数组时兜底成空数组，不渲染半截清单
  const app2 = makeApp(async () => okJson({ ok: true }));
  await app2.loadMaterials('pid2');
  assert.equal(app2.addressMaterials.pid2.items.length, 0, '后端未返回 items 时兜底成空数组');
});

test('M2：读取失败进 error 态，不静默渲染空清单冒充「无材料」', async () => {
  const app = makeApp(async () => errJson({ ok: false, error: '无此留档权限' }, 403));

  await app.loadMaterials('pid1');

  assert.equal(app.addressMaterials.pid1.items.length, 0, '失败不应渲染半截清单');
  assert.equal(app.addressMaterials.pid1.error, '无此留档权限', '后端文案要透出，不能吞掉');
  assert.equal(app.addressMaterials.pid1.loading, false);
});

test('M2：已加载且非错误态不重复拉（反复展开折叠不重发请求）', async () => {
  let getCount = 0;
  const app = makeApp(async (url, options) => {
    if (!options || !options.method) { getCount++; return okJson({ ok: true, items: [{ id: 'a'.repeat(32), kind: '合格证', title: 't', filename: 'f', mime: 'application/pdf', size: 1, created: 1 }] }); }
    return okJson({ ok: true, items: [] });
  });

  await app.loadMaterials('pid1');
  await app.loadMaterials('pid1');     // 第二次应短路
  assert.equal(getCount, 1, '已加载后不应再发 GET');
});

// =====================================================================
// 2. 上传前的校验（每条都挡在发请求之前）
// =====================================================================

test('上传校验①：kind 不在契约 KINDS 内，不发任何请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201));
  app.fileToDataUrl = async () => 'data:application/pdf;base64,JVBERi0xLjQK';
  await app.uploadMaterial('pid1', '不属于五类的类别', '铝合金合格证', { name: 'cert.pdf' });
  assert.equal(app.calls.length, 0, 'kind 非法不该发请求');
});

test('上传校验②：title 空，不发任何请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201));
  app.fileToDataUrl = async () => 'data:application/pdf;base64,JVBERi0xLjQK';
  await app.uploadMaterial('pid1', '合格证', '   ', { name: 'cert.pdf' });
  assert.equal(app.calls.length, 0, 'title 空不该发请求');
});

test('上传校验③：title 超过 60 字，不发请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201));
  app.fileToDataUrl = async () => 'data:application/pdf;base64,JVBERi0xLjQK';
  await app.uploadMaterial('pid1', '合格证', '材'.repeat(61), { name: 'cert.pdf' });
  assert.equal(app.calls.length, 0, 'title 超长不该发请求');
});

test('上传校验④：mime 不在白名单（如 text/plain），不发请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201), { addressId: 'addr1' });
  app.fileToDataUrl = async () => 'data:text/plain;base64,QQ==';
  await app.uploadMaterial('pid1', '合格证', '某说明文档', { name: 'note.txt' });
  assert.equal(app.calls.length, 0, '非白名单类型不该发请求');
  assert.equal(app.addressMaterials.pid1.draft.uploading, false);
});

test('上传校验⑤：解码后超过 25MB（dataUrl 超上限），不发请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201), { addressId: 'addr1' });
  // 造一个刚好超过 MATERIAL_DATA_URL_CEILING 的 dataUrl
  app.fileToDataUrl = async () => 'data:application/pdf;base64,' + 'A'.repeat(app.MATERIAL_DATA_URL_CEILING + 10);
  await app.uploadMaterial('pid1', '合格证', '大文件', { name: 'big.pdf' });
  assert.equal(app.calls.length, 0, '超限文件不该发请求（后端会 413）');
});

// =====================================================================
// 3. 上传（契约 M3）
// =====================================================================

test('M3：POST（不是 PUT），body 是 {kind,title,dataUrl,filename}，成功后刷新清单', async () => {
  const app = makeApp(async (url, options) => {
    if (options && options.method === 'POST') return okJson({ ok: true, id: 'm'.repeat(32), kind: '合格证', title: '铝合金型材合格证', mime: 'application/pdf', size: 12345 }, 201);
    return okJson({ ok: true, items: [] });   // 上传后的 loadMaterials 刷新
  }, { addressId: 'addr1' });
  app.fileToDataUrl = async () => 'data:application/pdf;base64,JVBERi0xLjQK';

  await app.uploadMaterial('pid1', '合格证', '铝合金型材合格证', { name: 'cert.pdf' });

  const post = app.calls.find((c) => c.options && c.options.method === 'POST');
  assert.ok(post, '没发出上传请求');
  assert.equal(post.url, '/api/share/publication/pid1/materials');
  assert.equal(post.options.method, 'POST', '契约 errata 同 hidden_work：用 POST 不用 PUT');
  assert.equal(post.options.headers['X-CSRF-Token'], 'test-csrf', '写请求必须带 X-CSRF-Token');

  const body = JSON.parse(post.options.body);
  assert.equal(body.kind, '合格证');
  assert.equal(body.title, '铝合金型材合格证');
  assert.equal(body.filename, 'cert.pdf');
  assert.ok(body.dataUrl.startsWith('data:application/pdf;base64,'), '直接发 FileReader 读出的 dataUrl，不压缩');
  // 关键：mime 由后端从 dataUrl 前缀解析，前端**不另发 mime 字段**（契约 M3 请求体无 mime）。
  // 任务描述里写的 {kind,title,filename,mime,dataUrl} 是错的，以契约为准。
  assert.ok(!('mime' in body), '前端不该另发 mime 字段——后端从 dataUrl 前缀解析');

  // 成功后 loadMaterials 刷新：发起了一次 GET /materials
  assert.ok(app.calls.some((c) => !c.options.method && /materials$/.test(c.url)), '上传成功后应刷新清单');
  assert.equal(app.addressMaterials.pid1.draft.uploading, false);
  assert.equal(app.addressMaterials.pid1.draft.kind, '', '传完清空类别，避免误重传');
  assert.equal(app.addressMaterials.pid1.draft.title, '', '传完清空标题，避免误重传');
});

test('M3：重复上传（后端 duplicate:true）给出可理解的提示，不报错', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'b'.repeat(32), kind: '合格证', title: 't', mime: 'application/pdf', size: 1, duplicate: true }, 201), { addressId: 'addr1' });
  const toasts = [];
  app.showToast = (msg, type) => toasts.push({ msg, type });
  app.fileToDataUrl = async () => 'data:application/pdf;base64,JVBERi0xLjQK';

  await app.uploadMaterial('pid1', '合格证', '铝合金型材合格证', { name: 'cert.pdf' });

  assert.match(toasts[0].msg, /已经传过/);
  assert.equal(toasts[0].type, undefined, '重复上传不是错误');
});

test('M3：文件未选 / 没打开地址时直接返回，不发请求', async () => {
  const app = makeApp(async () => okJson({ ok: true, id: 'c'.repeat(32) }, 201));
  await app.uploadMaterial('pid1', '合格证', '铝合金型材合格证', null);
  assert.equal(app.calls.length, 0);
});

// =====================================================================
// 4. 删除（契约 M4）
// =====================================================================

test('M4：删材料走 DELETE（不是 POST），并带上 CSRF 头，本地只摘被删那条', async () => {
  const app = makeApp(async (url, options) => {
    if (options && options.method === 'DELETE') return okJson({ ok: true });
    return okJson({ ok: true, items: [] });
  }, { addressId: 'addr1' });
  app.addressMaterials.pid1 = {
    items: [
      { id: 'aaa', kind: '合格证', title: 't1', filename: 'f1', mime: 'application/pdf', size: 1 },
      { id: 'bbb', kind: '检测报告', title: 't2', filename: 'f2', mime: 'image/png', size: 2 },
    ],
    loading: false, error: '', removing: false, draft: { kind: '', title: '', file: null, uploading: false },
  };

  await app.removeMaterial('pid1', 'aaa');

  const call = app.calls[0];
  assert.equal(call.url, '/api/share/publication/pid1/materials/aaa');
  assert.equal(call.options.method, 'DELETE',
    '契约 M4 判 self.command==\'DELETE\'；走 accountJSON 只能发 POST，后端会 405');
  assert.equal(call.options.headers['X-CSRF-Token'], 'test-csrf', 'DELETE 是写请求，必须带 CSRF 头');
  assert.deepEqual(app.addressMaterials.pid1.items, [{ id: 'bbb', kind: '检测报告', title: 't2', filename: 'f2', mime: 'image/png', size: 2 }], '只摘掉被删的那一条');
  assert.equal(app.addressMaterials.pid1.removing, false, '删除结束要解除 removing');
});

test('M4：删除进行中再点删除被防重复拦截（不连发 DELETE）', async () => {
  let deletes = 0;
  const app = makeApp(async (url, options) => {
    if (options && options.method === 'DELETE') { deletes++; return okJson({ ok: true }); }
    return okJson({ ok: true, items: [] });
  }, { addressId: 'addr1' });
  app.addressMaterials.pid1 = {
    items: [{ id: 'aaa', kind: '合格证', title: 't', filename: 'f', mime: 'application/pdf', size: 1 }],
    loading: false, error: '', removing: true, draft: { kind: '', title: '', file: null, uploading: false },
  };

  await app.removeMaterial('pid1', 'aaa');   // removing 已是 true，应直接返回
  assert.equal(deletes, 0, '防重复提交失效：removing 期间又发了删除');
});

// =====================================================================
// 5. 状态隔离：切地址 / 关详情必须清干净（材料串户比文字串户严重）
// =====================================================================

test('切地址：openAddress 立刻按当前留档重建空缓存，不留上一户材料', async () => {
  const app = makeApp(() => okJson({ ok: true, id: 'addrB', stages: [], enabled_stages: [] }), { addressId: 'addrA' });
  app.addressMaterials.addrA_p1 = {
    items: [{ id: 'x', kind: '合格证', title: 'A 户的材料', filename: 'f', mime: 'application/pdf', size: 1 }],
    loading: false, error: '', removing: false, draft: { kind: '检测报告', title: '半截', file: null, uploading: false },
  };

  await app.openAddress('addrB');
  await tick();

  assert.equal(Object.keys(app.addressMaterials).length, 0, 'A 户的材料缓存不能留到 B 户');
});

test('关详情清空材料缓存', () => {
  const app = makeApp(() => okJson({ ok: true }));
  app.addressMaterials.p1 = { items: [{ id: 'x' }], loading: false, error: '', removing: false, draft: { kind: '', title: '', file: null, uploading: false } };
  app.closeAddressDetail();
  assert.equal(Object.keys(app.addressMaterials).length, 0, 'closeAddressDetail 必须清空材料缓存');
});

// =====================================================================
// 6. index.html 结构守卫
// =====================================================================

test('index.html：每条留档记录里挂了「材料与性能证明」折叠区', () => {
  assert.ok(hiddenRegion.includes('材料与性能证明'), '找不到材料区标题');
  assert.match(hiddenRegion, /<details[^>]*@click="loadMaterials\(stage\.publication_id\)"/, '展开时应触发 loadMaterials');
  assert.ok(hiddenRegion.includes('loadMaterials(stage.publication_id)'), 'loadMaterials 调用缺失');
  assert.ok(hiddenRegion.includes('uploadMaterial(stage.publication_id'), 'uploadMaterial 调用缺失');
  assert.ok(hiddenRegion.includes('removeMaterial(stage.publication_id'), 'removeMaterial 调用缺失');
});

test('index.html：标题右侧「N 项」徽标 / 无材料时「待补充」', () => {
  assert.match(hiddenRegion, /\+ ' 项'/, '「N 项」徽标缺失');
  assert.ok(hiddenRegion.includes('待补充'), '无材料时应显示「待补充」');
});

test('index.html：内容块用 <template x-if> 而非 x-show（规避 x-for 内 x-show 重复求值坑）', () => {
  const markup = stripComments(hiddenRegion);
  assert.match(markup, /<template x-if="!addressMaterials\[stage\.publication_id\]\.loading && !addressMaterials\[stage\.publication_id\]\.error">/,
    '材料列表/上传表单应放在 x-if 内容块里，不能用 x-show');
  // 上传表单必须能找到，且在 x-if 内容块内
  assert.match(markup, /uploadMaterial\(stage\.publication_id/);
});

test('index.html：类别下拉渲染契约 KINDS，标题带「会随留档展示给业主」提示', () => {
  assert.match(hiddenRegion, /<template x-for="k in MATERIAL_KINDS"/, '类别下拉应遍历 MATERIAL_KINDS');
  assert.ok(hiddenRegion.includes('会随留档展示给业主'), 'title 输入应提示「会随留档展示给业主」');
});

test('index.html：文件选择 accept 覆盖契约 MIME 白名单，上传中禁用并显示「上传中…」', () => {
  assert.match(hiddenRegion, /accept="\.pdf,\.png,\.jpg,\.jpeg,\.webp"/, 'accept 必须覆盖 PDF/PNG/JPG/WebP');
  assert.match(hiddenRegion, /type="file"[\s\S]{0,400}?uploadMaterial\(stage\.publication_id[^)]*\);\s*\$event\.target\.value = ''/,
    '选完文件要清空 input.value，否则同一份第二次选不触发 change');
  assert.match(hiddenRegion, /:disabled="addressMaterials\[stage\.publication_id\]\.draft\.uploading"/, '上传中禁用上传按钮');
  assert.ok(hiddenRegion.includes('上传中…'), '上传中应显示「上传中…」');
});

test('x-show 表达式只收敛成布尔（不外带字符串字段做 && 右操作数，避免 Alpine 3 抛错）', () => {
  assert.ok(
    !/x-show="[^"]*&&\s*(m\.kind|m\.title|m\.filename|m\.mime|stage\.label|stage\.created)\s*"/.test(HTML),
    'x-show 里把可能为字符串的字段直接当成 && 的右操作数 —— 必须用 !! 转成布尔',
  );
  assert.match(hiddenRegion, /x-show="!addressMaterials\[stage\.publication_id\]\.loading && !!addressMaterials\[stage\.publication_id\]\.error"/,
    '错误提示行的 !! 丢了');
});

test('产品文案克制，不夸大材料证明的法律效力', () => {
  const text = ADDRESS_SRC + HTML;
  assert.ok(!/具有法律效力|法律效力|可靠电子签名/.test(text), '文案越界了：材料清单只构成交付附件，不构成效力承诺');
});

// =====================================================================
// 7. 契约对账 / 红线守卫
// =====================================================================

test('调用的端点与契约 materials v1 逐条对得上', () => {
  // 注意：前端走 accountJSON / accountDelete，它们会自动在前面拼 /api/share，
  // 所以源码里只写相对路径 /publication/<pid>/materials（契约完整路径是 /api/share/publication/<pid>/materials）。
  assert.ok(ADDRESS_SRC.includes("/publication/' + pid + '/materials'"),
    'M2 读取 / M3 上传 路径不对（源码相对路径应是 /publication/<pid>/materials）');
  assert.ok(ADDRESS_SRC.includes("/publication/' + pid + '/materials/' + mid"),
    'M4 删除路径不对（/publication/<pid>/materials/<mid>）');
  // M4 必须是 DELETE，且走 accountDelete（accountJSON 发不出 DELETE）
  assert.match(ADDRESS_SRC, /removeMaterial\(pid, mid\)[\s\S]{0,600}?accountDelete\('\/publication\/' \+ pid \+ '\/materials\/' \+ mid\)/,
    'removeMaterial 必须走 accountDelete（DELETE + CSRF）');
  // 上传绝不能用 compressDataUrl（会损坏 PDF / 把 PNG 透明底压成黑块）
  assert.ok(!/compressDataUrl/.test(ADDRESS_SRC.slice(ADDRESS_SRC.indexOf('uploadMaterial'))),
    'uploadMaterial 不能调 compressDataUrl——PDF 原样、PNG 不动');
});

test('用到的字段名全部来自契约，没有自造字段', () => {
  const combined = ADDRESS_SRC + HTML;
  for (const field of ['kind', 'title', 'filename', 'mime', 'size', 'dataUrl', 'items', 'publication_id']) {
    assert.ok(combined.includes(field), '契约字段没被用上（或拼错了）：' + field);
  }
});

test('契约常量与前端常量一致', () => {
  assert.match(ADDRESS_SRC, /MATERIAL_KINDS:\s*\['合格证', '检测报告', '使用说明书', '质保卡', '其它'\]/);
  assert.match(ADDRESS_SRC, /MATERIAL_MIME_ALLOWED:\s*\['image\/png', 'image\/jpeg', 'image\/webp', 'application\/pdf'\]/);
  assert.match(ADDRESS_SRC, /MATERIAL_TITLE_LIMIT:\s*60/);
  assert.match(ADDRESS_SRC, /MATERIAL_FILENAME_LIMIT:\s*160/);
  assert.match(ADDRESS_SRC, /MATERIAL_BODY_LIMIT:\s*26214400/);
});

test('红线：前端不发裸 fetch、不硬编码域名、不算摘要 / 不解析 EXIF', () => {
  assert.ok(!/\bfetch\s*\(/.test(ADDRESS_SRC), 'address-client.js 不该自己发 fetch');
  assert.ok(!/https?:\/\/(?!cj-az\.cn)/.test(ADDRESS_SRC.replace(/https:\/\/cj-az\.cn/g, '')), '出现了硬编码域名');
  assert.ok(!/sha256|digest\s*[:=]/i.test(ADDRESS_SRC), '摘要不属于前端');
  assert.ok(!/exifr|piexif|getExif|EXIF\.|gps\./i.test(ADDRESS_SRC), '前端在解析 EXIF/GPS —— 那是后端职责');
});

// ---------- 跨仓库守卫 ----------

test('跨仓库守卫：前端常量与后端契约 materials.v1.json 一致', () => {
  // 这条只在能读到契约文件时生效（本地绝对路径或后端 CI 的 SITELOG_BACKEND）。
  // 读不到时跳过，不制造假红。
  if (!contract) {
    console.log('  跳过：未读到契约文件 ' + CONTRACT_PATH);
    return;
  }
  const app = makeApp(async () => okJson({ ok: true, items: [] }));
  // 注意：app 的属性是在 vm 沙箱里创建的跨 realm 对象，跨 realm 的数组/对象与
  // 主 realm 字面量用 deepStrictEqual 比较会因 prototype 不同被判不相等（即使内容一致）。
  // ② 的惯例是改用 .length / .map 逐个比；这里对数组用 JSON 序列化后比字符串。
  const sameJSON = (a, b, msg) => assert.ok(JSON.stringify(a) === JSON.stringify(b), msg);
  sameJSON(app.MATERIAL_KINDS, contract.constants.KINDS,
    '前端 KINDS 与契约 constants.KINDS 不一致');
  sameJSON(app.MATERIAL_MIME_ALLOWED, contract.constants.MIME_ALLOWED,
    '前端 MIME 白名单与契约 constants.MIME_ALLOWED 不一致');
  assert.equal(app.MATERIAL_TITLE_LIMIT, contract.constants.TITLE_LIMIT,
    '前端标题上限与契约 TITLE_LIMIT 不一致');
  assert.equal(app.MATERIAL_FILENAME_LIMIT, contract.constants.FILENAME_LIMIT,
    '前端文件名上限与契约 FILENAME_LIMIT 不一致');
  assert.equal(app.MATERIAL_BODY_LIMIT, contract.constants.MATERIAL_BODY_LIMIT,
    '前端体积上限与契约 MATERIAL_BODY_LIMIT 不一致');
  // 软拦上限与后端 MATERIAL_DATA_URL_CEILING 同一公式（base64 放大 4/3 再留 2MB 余量）。
  assert.equal(
    app.MATERIAL_DATA_URL_CEILING,
    Math.floor(app.MATERIAL_BODY_LIMIT / 3) * 4 + 2 * 1024 * 1024,
    '前端 dataUrl 软拦上限与后端公式不一致',
  );
  assert.ok(app.MATERIAL_DATA_URL_CEILING > app.MATERIAL_BODY_LIMIT, '软拦上限必须大于原始体积上限');
});
