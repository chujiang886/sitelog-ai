// 三组「手动上传画廊」（班组进场 / SOP / 完工）的单测。
//
// 【为什么必须测】
// 这一块的错全是**静默错**：文件被跳过、照片没入队、frames 里留下悬空引用 ——
// 界面上都不会报错，只是业主打开报告时少几张照片，或者点「生成分享码」时
// 后端因为悬空引用拒收。现场已经撤场，照片补不回来。
//
// 【为什么现在才测】
// 这些方法原先内联在 app-main.js 的 Alpine 组件字面量里，vm 跑不动（要
// 整个 Alpine 运行时）。2026-10-06 搬到 gallery-client.js 之后才可以在
// 干净上下文里直接跑 —— 拆分的主要收益就在这里。
//
// 用法：node test-gallery-client.cjs
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const ctx = { window: {}, console, setTimeout, clearTimeout, document: null };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'gallery-client.js'), 'utf8'), ctx);
const G = ctx.window.galleryFeatures;

// vm 里创建的对象属于另一个 realm，deepStrictEqual 会误报 prototype 不同。
// 走一次 JSON 往返拉回本 realm —— 与 test-frame-client.cjs 同一手法。
const copy = (x) => JSON.parse(JSON.stringify(x));

const MB = 1024 * 1024;

/** 造一个只带 mixin 方法 + 必要桩件的假组件 */
function make({ frames = [], isFramed = false } = {}) {
  const toasts = [];
  const app = Object.assign(Object.create(G), {
    arrivalImages: [],
    sopImages: [],
    finishImages: [],
    frames,
    isFramedTemplate: () => isFramed,
    syncFrames: () => { app.syncFramesCalls += 1; },
    syncFramesCalls: 0,
    showToast: (msg, type) => toasts.push({ msg, type }),
    fileToDataUrl: async (f) => 'data:' + f.type + ';base64,' + f.name,
    escapeHtml: (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])),
    dupWarnHtml: () => '',
    toasts,
  });
  return app;
}

/** 假画廊元素：只实现 syncXxxGallery 真正用到的三个口子 */
function fakeGallery() {
  return { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
}

const file = (name, size = 1024, type = 'image/jpeg') => ({ name, size, type });

// ────────────────────────────────────────────────────────────────
// 三个画廊是同一套机制的三份实例 —— 结构必须完全对称
// ────────────────────────────────────────────────────────────────

const GALLERIES = [
  { key: 'Arrival', state: 'arrivalImages', domId: 'arrival-gallery', label: '班组进场' },
  { key: 'Sop', state: 'sopImages', domId: 'sop-gallery', label: '班组离场 SOP' },
  { key: 'Finish', state: 'finishImages', domId: 'finish-gallery', label: '完工照片' },
];

test('三组画廊的方法结构完全对称（sync / 收文件 / 入队 / 删除）', () => {
  for (const g of GALLERIES) {
    for (const suffix of ['', 'FileSelect', 'Drop', 'Files', 'Image']) {
      const name = suffix === '' ? `sync${g.key}Gallery`
        : suffix === 'Image' ? `remove${g.key}Image`
          : suffix === 'Files' ? `process${g.key}Files`
            : `handle${g.key}${suffix}`;
      assert.equal(typeof G[name], 'function', `缺少 ${name}`);
    }
  }
});

// ────────────────────────────────────────────────────────────────
// 入队：10MB 上限 + 字段完整性
// ────────────────────────────────────────────────────────────────

test('processArrivalFiles：超 10MB 的文件被跳过并提示，其余照常入队', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('ok1.jpg', 1 * MB), file('huge.jpg', 11 * MB), file('ok2.jpg', 2 * MB)]);
  assert.equal(app.arrivalImages.length, 2);
  assert.deepEqual(app.arrivalImages.map((p) => p.file.name), ['ok1.jpg', 'ok2.jpg']);
  assert.ok(app.toasts.some((t) => t.type === 'error' && t.msg.includes('huge.jpg') && t.msg.includes('10MB')),
    '被跳过的文件必须有明确提示，否则师傅以为传上去了');
});

test('processArrivalFiles：正好 10MB 通过（边界是 > 不是 >=）', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('exact.jpg', 10 * MB)]);
  assert.equal(app.arrivalImages.length, 1);
  await app.processArrivalFiles([file('over.jpg', 10 * MB + 1)]);
  assert.equal(app.arrivalImages.length, 1, '10MB+1 应该被跳过');
});

test('processArrivalFiles：照片对象字段完整（AI 识别依赖这些默认值）', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('a.jpg')]);
  const p = copy(app.arrivalImages[0]);
  assert.equal(p.category, '班组进场');
  assert.equal(p.section, 'arrival');
  assert.equal(p.dataUrl, 'data:image/jpeg;base64,a.jpg');
  assert.equal(p.aiConfirmed, false);
  assert.equal(p._analyzed, false);
  assert.equal(p.analyzing, false);
  assert.deepEqual(p.highlights, []);
  assert.ok(p.id && typeof p.id === 'string', 'id 必须有，且是字符串');
  assert.ok(p.time, 'time 必须有（报告里要显示）');
});

test('processSopFiles：标题取文件名去扩展名（师傅不填也有个能看的标题）', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processSopFiles([file('关水阀确认.jpeg'), file('no-ext')]);
  assert.deepEqual(app.sopImages.map((p) => p.title), ['关水阀确认', 'no-ext']);
});

test('processFinishFiles：字段完整且 category/section 正确', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processFinishFiles([file('f.jpg')]);
  const p = copy(app.finishImages[0]);
  assert.equal(p.category, '完工照片');
  assert.equal(p.section, 'finish');
  assert.equal(p.aiConfirmed, false);
});

test('三个 process 在空列表时直接返回：不提示、不渲染', async () => {
  for (const g of GALLERIES) {
    const app = make();
    let rendered = 0;
    ctx.document = { getElementById: () => { rendered += 1; return fakeGallery(); } };
    await app[`process${g.key}Files`]([]);
    assert.equal(app[g.state].length, 0);
    assert.deepEqual(app.toasts, [], `${g.label}：空列表不该弹提示`);
    assert.equal(rendered, 0, `${g.label}：空列表不该重渲染`);
  }
});

// ────────────────────────────────────────────────────────────────
// 「一框一记录」：照片以 id 引用进 frame，删除必须清引用
// ────────────────────────────────────────────────────────────────

test('processArrivalFiles(files, frameId)：照片进指定框，且框里只存 id 引用', async () => {
  const frames = [{ id: 'f1', label: '客厅', arrivalIds: [], nodeIds: [] }];
  const app = make({ frames });
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('a.jpg'), file('b.jpg')], 'f1');
  assert.equal(app.arrivalImages.length, 2);
  assert.deepEqual(frames[0].arrivalIds, app.arrivalImages.map((p) => p.id));
  // 只能是 id：整对象进 frame 会让快照体积翻倍、并且发布时被后端拒绝
  assert.ok(frames[0].arrivalIds.every((x) => typeof x === 'string'));
});

test('removeArrivalImage：删除照片时同步清掉 frames 里的悬空引用', async () => {
  const frames = [{ id: 'f1', label: '客厅', arrivalIds: [], nodeIds: [] }];
  const app = make({ frames });
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('a.jpg'), file('b.jpg')], 'f1');
  const [keep, drop] = app.arrivalImages.map((p) => p.id);
  app.removeArrivalImage(drop);
  assert.deepEqual(app.arrivalImages.map((p) => p.id), [keep]);
  assert.deepEqual(frames[0].arrivalIds, [keep],
    '悬空引用会被后端拒绝发布 —— 删照片时必须一起清');
});

test('removeArrivalImage：frames 为空 / 未定义时不炸', async () => {
  const app = make({ frames: undefined });
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('a.jpg')]);
  app.removeArrivalImage(app.arrivalImages[0].id);
  assert.equal(app.arrivalImages.length, 0);
});

test('removeSopImage / removeFinishImage：只从自己的数组里删', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processSopFiles([file('s.jpg')]);
  await app.processFinishFiles([file('f.jpg')]);
  app.removeSopImage(app.sopImages[0].id);
  assert.equal(app.sopImages.length, 0);
  assert.equal(app.finishImages.length, 1, '删 SOP 不该动完工照片');
});

// ────────────────────────────────────────────────────────────────
// 渲染
// ────────────────────────────────────────────────────────────────

test('syncArrivalGallery：空态给出「点击或拖拽上传」引导，并带隐藏 input', () => {
  const app = make();
  const gallery = fakeGallery();
  ctx.document = { getElementById: (id) => (id === 'arrival-gallery' ? gallery : null) };
  app.syncArrivalGallery();
  assert.ok(gallery.innerHTML.includes('点击或拖拽上传进场照片'), '空态必须有引导文案');
  assert.ok(gallery.innerHTML.includes('id="arrival-input-empty"'), '空态必须带 file input');
});

test('syncArrivalGallery：有照片时每张一个 node-card，编号补零到两位', () => {
  const app = make();
  app.arrivalImages = Array.from({ length: 3 }, (_, i) => ({
    id: 'p' + i, dataUrl: 'data:,', title: '第' + i + '张', desc: '', highlights: [], time: '2026-10-06',
  }));
  const gallery = fakeGallery();
  ctx.document = { getElementById: (id) => (id === 'arrival-gallery' ? gallery : null) };
  app.syncArrivalGallery();
  assert.equal((gallery.innerHTML.match(/class="node-card node-block"/g) || []).length, 3);
  assert.ok(gallery.innerHTML.includes('>01<') && gallery.innerHTML.includes('>03<'), '编号要补零');
  assert.ok(gallery.innerHTML.includes('id="arrival-zone-add"'), '有照片时也要能继续加');
});

test('syncXxxGallery：目标元素不存在时安静返回（模板里没这个画廊也不能炸）', () => {
  for (const g of GALLERIES) {
    const app = make();
    ctx.document = { getElementById: () => null };
    assert.doesNotThrow(() => app[`sync${g.key}Gallery`]());
  }
});

// ────────────────────────────────────────────────────────────────
// 拖拽入口
// ────────────────────────────────────────────────────────────────

test('handleArrivalDrop：非图片文件被过滤掉', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  const event = {
    target: { closest: () => null },
    dataTransfer: { files: [file('a.jpg', 1024, 'image/jpeg'), file('note.pdf', 1024, 'application/pdf')] },
  };
  await app.handleArrivalDrop(event);
  assert.deepEqual(app.arrivalImages.map((p) => p.file.name), ['a.jpg']);
});

test('handleArrivalFileSelect：读完把 input.value 清空（否则同一文件选第二次不触发 change）', async () => {
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  const target = { files: [file('a.jpg')], value: 'C:\\fakepath\\a.jpg' };
  await app.handleArrivalFileSelect({ target });
  assert.equal(target.value, '');
  assert.equal(app.arrivalImages.length, 1);
});

// ────────────────────────────────────────────────────────────────
// 已知缺陷（现状钉死：修的时候这条会红，提醒一并改文案）
// ────────────────────────────────────────────────────────────────

test('【已知缺陷】跳过大文件后，成功提示报的仍是 files.length 而不是实际入队数', async () => {
  // 3 张里 1 张超限 → 实际入队 2 张，但提示说「已添加 3 张」。
  // 与「不编造数据」的原则冲突，但这是搬移前的既有行为，刻意**不**在
  // 「逐字节搬移」这一次变更里顺手改（会破坏 sha256 基线）。
  // 单独修的时候，把下面的断言改成 2，并同步改 processSopFiles / processFinishFiles。
  const app = make();
  ctx.document = { getElementById: () => fakeGallery() };
  await app.processArrivalFiles([file('a.jpg'), file('b.jpg'), file('huge.jpg', 11 * MB)]);
  assert.equal(app.arrivalImages.length, 2);
  const ok = app.toasts.find((t) => t.msg.startsWith('✅'));
  assert.ok(ok.msg.includes('3 张'), '现状：提示按提交数报，不按实际入队数 —— 见上方注释');
});
