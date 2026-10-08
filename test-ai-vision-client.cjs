// AI 视觉识别引擎（ai-vision-client.js）的单测。
//
// 【为什么必须测】
// 这 17 个方法原先内联在 app-main.js 的 Alpine 组件字面量里，vm 跑不动（要整个
// Alpine 运行时）。2026-10-22 搬到 ai-vision-client.js 之后，纯逻辑部分可以直接在
// 干净上下文里跑 —— 拆分的主要收益就在这里。
//
// 这一块的错大半是「不报错但结果错」：AI 返回的 JSON 夹在解释文字里、带尾逗号、
// 用单引号、字段名五花八门（desc/description/描述/工艺说明）；去重把每张照片
// 写成同一句；提示词字段错位。这些都不会抛异常，只会在业主档案里留下垃圾文案。
//
// 【加载方式】
// AI 方法依赖 ai-style.js 的全局函数（AI_STYLE / NL / polishSiteLogText /
// scoreSiteLogText）。经典脚本共享全局词法环境，但 node 的 vm 每个 runInContext
// 是独立脚本、顶层 const 不跨脚本可见 —— 因此按本仓库既有范式（APP_BUNDLE）把
// ai-style.js + ai-vision-client.js 拼成一份、按真实顺序跑，模拟浏览器里
// 「先 ai-style 后 app-main」的加载。
//
// 用法：node test-ai-vision-client.cjs
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const aiStyleSrc = fs.readFileSync(path.join(__dirname, 'ai-style.js'), 'utf8');
const aiVisionSrc = fs.readFileSync(path.join(__dirname, 'ai-vision-client.js'), 'utf8');

const ctx = { window: {}, console, setTimeout, clearTimeout, document: null };
vm.createContext(ctx);
// 按真实加载顺序拼成一份（先 ai-style 后 ai-vision）
vm.runInContext(aiStyleSrc + '\n;\n' + aiVisionSrc, ctx);
const AV = ctx.window.aiVisionFeatures;
assert.ok(AV && typeof AV === 'object', 'ai-vision-client.js 没有挂到 window.aiVisionFeatures');

// vm 里创建的对象属于另一个 realm，deepStrictEqual 会误报 prototype 不同。
// 走一次 JSON 往返拉回本 realm —— 与 test-gallery-client.cjs 同一手法。
const copy = (x) => JSON.parse(JSON.stringify(x));

/** 造一个只带 mixin 方法 + 必要桩件的假组件 */
function make({ images = [], arrivalImages = [], finishImages = [], ...rest } = {}) {
  return Object.assign(Object.create(AV), {
    images, arrivalImages, finishImages,
    showToast: () => {},
    ...rest,
  });
}

const LONG = '框体采用化学锚栓穿透固定片与结构墙连接，四周预留注胶间隙，复核垂直度后转入注胶工序。';

test('17 个方法一个不少', () => {
  const keys = new Set(Object.keys(AV));
  for (const m of ['aiOrganizeAll','applyCandidateAndAdopt','reAnalyze','captureDomEdits',
    'ensureTitles','analyzeImage','applyAnalysisResult','buildAnalysisPrompt','dedupeDesc',
    'dupWarnHtml','callVisionAPI','extractJSONRobust','_findMatchingBrace','_normalizeParsed',
    '_extractFieldsByRegex','_extractSentenceFromRaw','testConnection']) {
    assert.ok(keys.has(m), `缺少方法 ${m}`);
  }
  assert.equal(keys.size, 17, `方法数应为 17，实际 ${keys.size}`);
});

// ────────────────────────────────────────────────────────────────
// _findMatchingBrace：引号内的 { } 不能算数，未闭合返回 -1
// ────────────────────────────────────────────────────────────────
test('_findMatchingBrace：跳过字符串内的括号，未闭合返回 -1', () => {
  assert.equal(AV._findMatchingBrace('{"a":"{"}', 0), 8, '应停在字符串外的 }');
  assert.equal(AV._findMatchingBrace('{"a":1}', 0), 6);
  assert.equal(AV._findMatchingBrace('{"a":1', 0), -1, '未闭合应返回 -1');
  assert.equal(AV._findMatchingBrace('前缀 {"x": {"y": 1}} 后缀', 3), 17, '从指定 { 开始配平');
});

// ────────────────────────────────────────────────────────────────
// extractJSONRobust：各种「模型返回不那么干净」的情况
// ────────────────────────────────────────────────────────────────
test('extractJSONRobust：纯 JSON 直接解析', () => {
  const r = AV.extractJSONRobust(JSON.stringify({ title: '框体安装', desc: LONG, category: '框架施工' }));
  assert.equal(r.title, '框体安装');
  assert.ok(typeof r.desc === 'string' && r.desc.length > 0);
  assert.equal(r.category, '框架施工');
  assert.equal(r._noJson, undefined, '纯 JSON 不应带 _noJson');
});

test('extractJSONRobust：JSON 夹在解释文字里也能抠出最全的那个', () => {
  const raw = '好的，这是识别结果：\n{"title":"玻扇安装","desc":"'+LONG+'","category":"玻扇施工","highlights":["要点甲","要点乙"]}\n以上为结果。';
  const r = AV.extractJSONRobust(raw);
  assert.equal(r.title, '玻扇安装');
  assert.equal(r.category, '玻扇施工');
  assert.deepEqual(copy(r.highlights), ['要点甲', '要点乙']);
});

test('extractJSONRobust：解释文字里的小括号对（如「{玻扇施工}」）不能误抓', () => {
  const raw = '这是{玻扇施工}阶段，结果：{"title":"窗扇调试","desc":"'+LONG+'"}';
  const r = AV.extractJSONRobust(raw);
  assert.equal(r.title, '窗扇调试', '应抓到真正的对象，而非解释里的小括号');
});

test('extractJSONRobust：尾逗号 / 未引号键 容错修复', () => {
  const raw = '{title:"框体就位",desc:"'+LONG+'",}';
  const r = AV.extractJSONRobust(raw);
  assert.equal(r.title, '框体就位');
  assert.ok(r.desc.includes('注胶') || r.desc.length > 0);
});

test('extractJSONRobust：纯单引号 JSON 转双引号', () => {
  const raw = "{'title':'成品保护','desc':'"+LONG+"'}";
  const r = AV.extractJSONRobust(raw);
  assert.equal(r.title, '成品保护');
});

test('extractJSONRobust：desc 字段名别名（描述 / caption / 工艺说明）都归一化到 desc', () => {
  for (const key of ['desc', 'description', '描述', '工艺说明', 'caption']) {
    const r = AV.extractJSONRobust(JSON.stringify({ title: '节点', [key]: LONG }));
    assert.ok(r.desc && r.desc.length > 0, `键 ${key} 未归一到 desc`);
  }
});

test('extractJSONRobust：既无 JSON 也无可读句子时保留原文并标 _noJson', () => {
  const raw = 'no json, no chinese sentence, just 12345';
  const r = AV.extractJSONRobust(raw);
  assert.equal(r._noJson, true, '无 JSON 且无中文长句时应标 _noJson');
  assert.ok(typeof r._raw === 'string' && r._raw.length > 0);
});

test('extractJSONRobust：无 JSON 但有中文长句时走字段兜底（desc 取自原句）', () => {
  const raw = '抱歉我无法识别这张照片的内容，请重试一次看看。';
  const r = AV.extractJSONRobust(raw);
  assert.equal(r._noJson, undefined, '有可读句子时应走字段兜底而非 _noJson');
  assert.ok(r.desc && r.desc.includes('无法识别'), 'desc 应取自原句');
});

// ────────────────────────────────────────────────────────────────
// 兜底抠取：连 JSON 都没有时，正则抠字段 / 抽句子
// ────────────────────────────────────────────────────────────────
test('_extractFieldsByRegex：非 JSON 文本里抠出 title/desc/stage', () => {
  const raw = 'title: 洞口复核\ndesc: 激光水平仪复核洞口尺寸偏差在允许范围内\nstage: 洞口复核中';
  const r = AV._extractFieldsByRegex(raw);
  assert.equal(r.title, '洞口复核');
  assert.ok(r.desc.includes('激光水平仪'));
  assert.equal(r.stage, '洞口复核中');
});

test('_extractSentenceFromRaw：从杂乱原文里抽一句中文', () => {
  const raw = '```json\n{"title":"x"}\n```\n框体采用化学锚栓固定，四周预留注胶间隙。这是一句完整说明。';
  const s = AV._extractSentenceFromRaw(raw);
  assert.ok(s.includes('化学锚栓') || s.includes('注胶间隙'), `抽到的句子不对：${s}`);
});

// ────────────────────────────────────────────────────────────────
// 重复文案：dupWarnHtml + dedupeDesc（「每张都一样」是客户最反感的点）
// ────────────────────────────────────────────────────────────────
test('dupWarnHtml：无 _dupDesc 返回空串，有则给提示 HTML', () => {
  assert.equal(AV.dupWarnHtml({}), '');
  assert.equal(AV.dupWarnHtml({ _dupDesc: false }), '');
  const html = AV.dupWarnHtml({ _dupDesc: true });
  assert.ok(html.includes('debug-panel') && html.includes('雷同'), '应渲染重复警告');
});

test('dedupeDesc：与已有照片雷同且有其它模型版本 → 换成不雷同的那条', () => {
  const app = make({ images: [{ _analyzed: true, desc: '框体采用化学锚栓固定，四周预留注胶间隙。' }] });
  const img = { desc: '框体采用化学锚栓固定，四周预留注胶间隙。' };
  const votes = [{ desc: '框体就位后复核垂直度，偏差满足规范要求。', title: '框体就位', _score: 5 }];
  app.dedupeDesc(img, votes);
  assert.equal(img.desc, '框体就位后复核垂直度，偏差满足规范要求。', '应换成不雷同的替代文案');
  assert.equal(img._dupDesc, undefined, '换成替代文案后不应再打标');
});

test('dedupeDesc：与已有照片雷同且无替代 → 打标 _dupDesc 等人工补充', () => {
  const app = make({ images: [{ _analyzed: true, desc: '框体采用化学锚栓固定，四周预留注胶间隙。' }] });
  const img = { desc: '框体采用化学锚栓固定，四周预留注胶间隙。' };
  app.dedupeDesc(img, []);
  assert.equal(img._dupDesc, true, '所有模型都雷同时应打标');
});

test('dedupeDesc：与已有照片不雷同 → 不动', () => {
  const app = make({ images: [{ _analyzed: true, desc: '完全不同的另一段已归档说明文字内容。' }] });
  const img = { desc: '框体采用化学锚栓固定，四周预留注胶间隙。' };
  app.dedupeDesc(img, []);
  assert.equal(img._dupDesc, undefined);
  assert.equal(img.desc, '框体采用化学锚栓固定，四周预留注胶间隙。');
});

// ────────────────────────────────────────────────────────────────
// 提示词构建：三个分区的场景与字段约束不同
// ────────────────────────────────────────────────────────────────
test('buildAnalysisPrompt：三个分区各有不同场景约束且都带 JSON schema', () => {
  for (const section of ['arrival', 'construction', 'finish']) {
    const p = AV.buildAnalysisPrompt(section);
    assert.ok(p.includes('"title"'), `${section} 提示词缺 title 字段`);
    assert.ok(p.includes('"desc"'), `${section} 提示词缺 desc 字段`);
  }
  assert.ok(AV.buildAnalysisPrompt('arrival').includes('进场'), '进场分区应含进场场景');
  assert.ok(AV.buildAnalysisPrompt('finish').includes('完工'), '完工分区应含完工场景');
  assert.ok(AV.buildAnalysisPrompt('construction').includes('框架施工'), '施工分区应含分类判定');
  // 默认分区
  assert.ok(AV.buildAnalysisPrompt().includes('框架施工'));
});
