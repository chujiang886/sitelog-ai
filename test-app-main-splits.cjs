#!/usr/bin/env node
// 2026-10-18：专项修复阶段成果标题、时间来源、AI证据边界；更新有意变化的拆移基线。
'use strict';
/*
 * app-main.js 拆分守护：从主脚本搬出去的每一块，都在这里钉死。
 *
 * 为什么要钉：
 *   1. 内容被顺手改了 —— 用 sha256 逐字节钉死（搬移的前提就是「内容零变化」）
 *   2. 定义没有真的搬走 —— 原文件里又长出一份，两份开始各自演化
 *   3. 加载顺序被颠倒 —— 顶层 const / function 的经典脚本按文档顺序初始化，
 *      顺序反了就是运行时 ReferenceError，而 node 单测在 vm 里只跑 app-main.js，
 *      **根本发现不了**（只有真浏览器能抓，见 test-visual-baseline.cjs）
 *   4. 搬出去的东西偷偷依赖了运行时状态 —— 那就不是「数据」，迟早要还回来
 *      （只对 kind='pure' 的块成立；kind='mixin' 的块天生就是组件方法，见下）
 *
 * 两种块：
 *   kind: 'pure'   纯数据 / 纯函数（templates.js、ai-style.js）。
 *                  不许出现 this.* / window.x= / fetch / require / import。
 *   kind: 'mixin'  组件方法（gallery-client.js）。**就是** this.* 的集合，
 *                  并把自己挂到 window.xxxFeatures 上，由 app-main.js 的
 *                  对象字面量用 ... 展开合并。
 *
 * ⚠️ mixin 最危险的失效方式不是报错，是**静默**：
 *   `{ ...window.galleryFeatures }` 在 galleryFeatures 为 undefined 时
 *   是合法的，展开成空对象、一个键都不加、不抛错。于是「方法整批消失」，
 *   而任何不主动调用它的测试都照样全绿。所以下面两条全局断言（每个
 *   ...window.XFeatures 都要有对应的 <script src> 与文件赋值、且跨文件不得
 *   重名）比单块的 sha256 更重要 —— 它们是这条静默路径唯一的守卫。
 *
 * 新增一块时：往 SPLITS 里加一行，并跑一次 `node test-app-main-splits.cjs` 确认基线。
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const read = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
const APP_MAIN = read('app-main.js');
const HTML = read('index.html');

// index.html 里的脚本引用可能带缓存版本号（`app-main.js?v=20261105`）。
// 缓存版本号是发布纪律：不带版本号时，某些浏览器/WebView 会继续用旧 JS，
// 用户「刷新了还是旧界面」。这里统一按「可带 ?v= 也可不带」匹配。
const scriptTagIndex = (html, file) => {
  const escaped = file.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const m = html.match(new RegExp(`<script src="${escaped}(?:\\?v=[^"]*)?">`));
  return m ? m.index : -1;
};
const AI_VISION = read('ai-vision-client.js');

// ────────────────────────────────────────────────────────────────
// ai-style.js 的术语口径语义守卫
//
// 【为什么 sha 基线不够】上面的 sha256 只能证明「这块内容没被意外改动」。
// 但如果有人把「无尘防护」误删、或把「防尘保护」错登进 TERMS，
// 只要同步更新 sha，测试照样全绿 —— 而 AI 又会开始被带偏。
// 所以口径本身必须另立语义断言。
//
// 【背景】轩哥 2026-11-06 确认：「无尘防护」是行业内部正式口径，
// 「防尘保护」不是。生产实测 AI 不认识这个词，只会拿通用词去猜
// （写成「嵌缝处理」「施打密封胶」）—— 59 条学习配对里「密封胶」
// 被人工删掉 9 次，是最高频的修正模式。
// ────────────────────────────────────────────────────────────────

/** 把 ai-style.js 装进 vm，取出 AI_STYLE 与 scoreSiteLogText（两者都是顶层声明，不挂 window） */
function loadAiStyle() {
  const ctx = { console };
  vm.createContext(ctx);
  const got = vm.runInContext(read('ai-style.js') + '\n;({ AI_STYLE, scoreSiteLogText })', ctx);
  // vm 里的对象属于另一个 realm，JSON 往返拉回本 realm（与 test-ai-vision-client.cjs 同手法）
  return { style: JSON.parse(JSON.stringify(got.AI_STYLE)), score: got.scoreSiteLogText };
}

// 正式口径与已确认的错误说法。改这两个常量前先问业务负责人。
const OFFICIAL_TERM = '无尘防护';
const WRONG_TERMS = ['防尘保护', '防尘处理'];

test('ai-style.js：GLOSSARY 登记了正式口径「无尘防护」（GLOSSARY 直接进提示词）', () => {
  const { style } = loadAiStyle();
  assert.ok(style.GLOSSARY.includes(OFFICIAL_TERM),
    `GLOSSARY 里没有「${OFFICIAL_TERM}」—— AI 不认识这个正式口径，` +
    '会拿「嵌缝」「施打密封胶」等通用词去猜，导致每张照片都要人工改');
});

test('ai-style.js：GLOSSARY 同时点名了不要写成的自造说法', () => {
  const { style } = loadAiStyle();
  // 只给正确词、不说哪些是错的，模型仍可能自造近义词。
  // 这条钉住「反例也在提示词里」，简化文案时不许删掉。
  for (const wrong of WRONG_TERMS) {
    assert.ok(style.GLOSSARY.includes(wrong),
      `GLOSSARY 应点名「${wrong}」不是本公司口径，避免 AI 自造近义词`);
  }
});

test('ai-style.js：TERMS 登记了正式口径，且绝不登记错误说法', () => {
  const { style } = loadAiStyle();
  // TERMS 用于 scoreSiteLogText 的术语命中加分（每命中 +7，上限 6 个）。
  // 不登记 → 写对口径的文案反而不得分，多模型选优时会输给写错的那条。
  assert.ok(style.TERMS.includes(OFFICIAL_TERM),
    `TERMS 里没有「${OFFICIAL_TERM}」—— 写对正式口径的文案拿不到术语加分`);
  for (const wrong of WRONG_TERMS) {
    assert.ok(!style.TERMS.includes(wrong),
      `TERMS 里不能有「${wrong}」—— 那不是本公司口径，登记进去等于给它加分`);
    assert.ok(!style.BANNED.includes(wrong),
      `BANNED 的语义是「拍照腔/套话」，不要往里塞错误术语（口径约束归 GLOSSARY 管）`);
  }
});

test('ai-style.js：写对正式口径的文案，评分高于同长度的无术语文案', () => {
  const { score } = loadAiStyle();
  // 两句除术语外长度与结构基本一致，差值只能来自 TERMS 命中。
  const official = '框体底部与混凝土台面交接处已完成无尘防护处理，周边缝隙清洁无残留，玻璃面板安装到位待复核。';
  const plain = '框体底部与混凝土台面交接处已完成相关处理工作，周边缝隙清洁无残留，玻璃面板安装到位待复核。';
  assert.ok(score(official, '框体收口', '玻扇施工') > score(plain, '框体收口', '玻扇施工'),
    '登记正式口径后，写对术语的文案必须得分更高（否则多模型选优会选回写错的那条）');
});

// 每一块：从主脚本搬出去的文件、块起点（行首精确匹配）、块 sha256（搬出时）、块行数
const SPLITS = [
  {
    kind: 'pure',
    file: 'templates.js',
    label: '报告模板（含合规版合规导出模板，v9 新增 compliance）',
    start: '// ====== 模板定义',
    // 2026-11-02：保留 main 合规模板，整合阶段成果标题修正。
    sha: '9ccde812e68a58c92f275a5a086fa4410aff09c59d1a6f85c9ed32be6a8ed75d',
    lines: 870,
    forbiddenInAppMain: /const TEMPLATES/,
  },
  {
    kind: 'pure',
    file: 'ai-style.js',
    label: 'AI 文案引擎（写作铁律 + 术语库 + 清洗 + 评分）',
    start: 'const NL = String.fromCharCode(10);',
    // 2026-11-06：GLOSSARY 与 TERMS 登记本公司正式口径「无尘防护」（轩哥确认；
    // 「防尘保护」不是口径）。生产实测 AI 不认识这个词，只会拿通用词去猜
    // （写成「嵌缝处理」「施打密封胶」），59 条学习配对里「密封胶」被人工删掉 9 次。
    // 两处都加在**现有行内**，所以行数仍是 138 —— 只有 sha 变。
    sha: '1abdc3cac3979cabb845f17d885e43d3cdb459fe6e52837ba03eb913a02a7344',
    lines: 138,
    forbiddenInAppMain: /const AI_STYLE|function polishSiteLogText|function scoreSiteLogText/,
  },
  {
    kind: 'mixin',
    file: 'gallery-client.js',
    label: '三组手动上传画廊（班组进场 / SOP / 完工）',
    start: 'window.galleryFeatures = {',
    // 2026-10-07 更新基线：三处 processXxxFiles 的成功提示改为按**实际入队数**报
    // （原按 files.length 报 —— 3 张里 1 张超 10MB 被跳过，提示仍说「已添加 3 张」）。
    // 2026-11-05 更新基线：按产品要求移除照片卡片的「拍摄时间/上传整理时间」标注。
    // 2026-11-05 再次更新：syncFinishGallery 只在原标题为「完工照片」时才改名，
    // 修掉「合规版第四段『留档影像索引』被无条件改成『本阶段成果照片』」的缺陷。
    sha: '17501cb50db9270f702ed3e55b619538bca9f0df18a94fb9ea0d494873f60c14',
    lines: 333,
    spread: 'galleryFeatures',
    forbiddenInAppMain: /^\s{8}sync(Arrival|Sop|Finish)Gallery\s*\(/m,
    methods: [
      'syncArrivalGallery', 'handleArrivalFileSelect', 'handleArrivalDrop', 'processArrivalFiles', 'removeArrivalImage',
      'syncSopGallery', 'handleSopFileSelect', 'handleSopDrop', 'processSopFiles', 'removeSopImage',
      'syncFinishGallery', 'handleFinishFileSelect', 'handleFinishDrop', 'processFinishFiles', 'removeFinishImage',
    ],
  },
  {
    kind: 'mixin',
    file: 'ai-vision-client.js',
    label: 'AI 视觉识别引擎（批量组织 / 单张重分析 / 健壮 JSON 提取 / 多模型投票去重）',
    start: 'window.aiVisionFeatures = {',
    // 2026-10-15：在原拆分基础上增加等待超时停止与状态清理；行为由 test-ai-wait 守护。
    sha: 'c9fdcf6edfdc40e024e7b44b0093440635f67246ee2da6512ed6984998e3a3d3',
    lines: 561,
    spread: 'aiVisionFeatures',
    forbiddenInAppMain: /^\s{8}(async\s+)?(aiOrganizeAll|applyCandidateAndAdopt|reAnalyze|captureDomEdits|ensureTitles|analyzeImage|applyAnalysisResult|buildAnalysisPrompt|dedupeDesc|dupWarnHtml|callVisionAPI|extractJSONRobust|_findMatchingBrace|_normalizeParsed|_extractFieldsByRegex|_extractSentenceFromRaw|testConnection)\s*\(/m,
    methods: [
      'aiOrganizeAll', 'applyCandidateAndAdopt', 'reAnalyze', 'captureDomEdits',
      'ensureTitles', 'analyzeImage', 'applyAnalysisResult', 'buildAnalysisPrompt',
      'dedupeDesc', 'dupWarnHtml', 'callVisionAPI', 'extractJSONRobust',
      '_findMatchingBrace', '_normalizeParsed', '_extractFieldsByRegex',
      '_extractSentenceFromRaw', 'testConnection',
    ],
  },
];

// 用 includes 而不是 startsWith：块起点行的缩进各不相同（模板块带 4 空格）
function blockOf(text, start) {
  const lines = text.split('\n');
  const idx = lines.findIndex((l) => l.includes(start));
  assert.ok(idx >= 0, `找不到块起点：${JSON.stringify(start)}`);
  return { block: lines.slice(idx).join('\n'), lines: lines.length - idx, idx };
}

for (const s of SPLITS) {
  test(`${s.file}：${s.label} 与搬出时逐字节一致`, () => {
    const text = read(s.file);
    const { block } = blockOf(text, s.start);
    const sha = crypto.createHash('sha256').update(block, 'utf8').digest('hex');
    assert.equal(sha, s.sha,
      `${s.file} 的内容被改动了 —— 若是有意改，请更新本测试里的基线并说明改了什么`);
  });

  test(`${s.file}：块的行数没有变（${s.lines} 行）`, () => {
    const { lines } = blockOf(read(s.file), s.start);
    assert.equal(lines, s.lines + 1); // +1 是文件末尾的空行
  });

  test(`app-main.js：${s.label} 的定义确实搬走了，且还有引用`, () => {
    assert.ok(!s.forbiddenInAppMain.test(APP_MAIN),
      `app-main.js 里又长出了 ${s.file} 的定义`);
  });

  test(`index.html：${s.file} 必须排在 app-main.js 之前`, () => {
    // 按 <script src> 精确匹配：注释里也会提到文件名，用裸文件名会找错位置
    const dep = scriptTagIndex(HTML, s.file);
    const app = scriptTagIndex(HTML, 'app-main.js');
    assert.ok(dep > 0, `index.html 里缺少 ${s.file} 的 <script src>`);
    assert.ok(app > 0, 'index.html 里缺少 app-main.js 的 <script src>');
    assert.ok(dep < app, `${s.file} 必须出现在 app-main.js 之前，否则运行时是 ReferenceError`);
  });

  if (s.kind === 'pure') {
    test(`${s.file}：是纯数据 / 纯函数，不依赖运行时状态`, () => {
      const text = read(s.file);
      assert.ok(!/\brequire\s*\(/.test(text), `${s.file} 不该 require 任何东西`);
      assert.ok(!/\bfetch\s*\(/.test(text), `${s.file} 不该发请求`);
      assert.ok(!/^\s*import\s/m.test(text), `${s.file} 不该有 import`);
      assert.ok(!/\bwindow\.\w+\s*=/.test(text), `${s.file} 不该往 window 上挂东西`);
      assert.ok(!/\bthis\./.test(text), `${s.file} 不该引用组件状态（this.*）`);
    });
  } else {
    test(`${s.file}：挂到 window.${s.spread}，且 ${s.methods.length} 个方法一个不少`, () => {
      const ctx = { window: {}, console, setTimeout, clearTimeout };
      vm.createContext(ctx);
      vm.runInContext(read(s.file), ctx);
      const obj = ctx.window[s.spread];
      assert.ok(obj && typeof obj === 'object', `${s.file} 没有挂到 window.${s.spread}`);
      const keys = new Set(Object.keys(obj));
      for (const m of s.methods) {
        assert.ok(keys.has(m), `${s.file} 少了方法 ${m}`);
        assert.equal(typeof obj[m], 'function', `${s.file}.${m} 不是函数`);
      }
      assert.equal(keys.size, s.methods.length,
        `${s.file} 的成员数变了（${keys.size} ≠ ${s.methods.length}）—— 新增成员请同步更新本测试`);
    });

    test(`app-main.js：用 ...window.${s.spread} 合并进来（不是另抄一份）`, () => {
      assert.ok(APP_MAIN.includes(`...window.${s.spread},`),
        `app-main.js 的对象字面量里没有 ...window.${s.spread},`);
    });
  }
}

test('app-main.js 里仍在使用搬出去的符号（不是改坏了而是换写法了）', () => {
  assert.ok(APP_MAIN.includes('TEMPLATES.'), 'app-main.js 里没有 TEMPLATES 的引用');
  assert.ok(/AI_STYLE|polishSiteLogText|scoreSiteLogText/.test(AI_VISION),
    'ai-vision-client.js 里没有用到 AI 文案引擎 —— 是改坏了还是换写法了？');
  assert.ok(/this\.sync(Arrival|Sop|Finish)Gallery\(\)/.test(APP_MAIN),
    'app-main.js 里没有调用画廊渲染 —— 是改坏了还是换写法了？');
});

// ────────────────────────────────────────────────────────────────
// 全局守卫：mixin 的静默失效路径
// ────────────────────────────────────────────────────────────────

/** 从 app-main.js 里取出对象字面量的一级成员名（8 空格缩进的 `name(` / `name:`） */
function appMainMembers() {
  const names = new Set();
  for (const l of APP_MAIN.split('\n')) {
    const m = l.match(/^ {8}(?:async\s+)?([A-Za-z_$][\w$]*)\s*(?:\(|:)/);
    if (m) names.add(m[1]);
  }
  return names;
}

/** 找到所有把 `window.xxxFeatures = {...}` 挂出来的文件，返回 { 变量名 -> 成员名集合 } */
function featureMixins() {
  const out = new Map();
  for (const f of fs.readdirSync(__dirname)) {
    if (!f.endsWith('.js') || f === 'app-main.js') continue;
    const text = read(f);
    const m = text.match(/window\.([A-Za-z_$][\w$]*Features)\s*=/);
    if (!m) continue;
    const ctx = { window: {}, console, setTimeout, clearTimeout };
    vm.createContext(ctx);
    try {
      vm.runInContext(text, ctx);
    } catch (e) {
      assert.fail(`${f} 无法在干净上下文里求值：${e.message}（mixin 不该依赖加载期就存在的全局）`);
    }
    const obj = ctx.window[m[1]];
    assert.ok(obj && typeof obj === 'object', `${f} 里 window.${m[1]} 不是对象`);
    out.set(f, { name: m[1], keys: new Set(Object.keys(obj)) });
  }
  return out;
}

test('app-main.js 里每个 ...window.XFeatures 都有对应的 <script src>（否则静默展开成空）', () => {
  const spreads = [...APP_MAIN.matchAll(/\.\.\.window\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]);
  assert.ok(spreads.length >= 9, `只找到 ${spreads.length} 个展开，比预期少`);
  const mixins = featureMixins();
  const declared = new Set([...mixins.values()].map((v) => v.name));
  for (const sp of spreads) {
    assert.ok(declared.has(sp),
      `app-main.js 展开了 window.${sp}，但没有任何文件给 window.${sp} 赋值 —— ` +
      `对象展开 undefined 不报错，会静默丢掉整组方法`);
    const owner = [...mixins.entries()].find(([, v]) => v.name === sp)[0];
    assert.ok(scriptTagIndex(HTML, owner) > 0,
      `index.html 里缺少 ${owner} 的 <script src>（它负责 window.${sp}）`);
  }
});

test('index.html：自有脚本与样式必须带缓存版本号（?v=）', () => {
  // 2026-11-05 事故：前端已发布新代码，但用户「刷新后仍是旧界面」——
  // 旧 JS 里还留着已下线的「拍摄时间」标注。nginx 给的是 no-cache（每次回源校验），
  // 但部分 WebView / 代理缓存不按语义办事，只有 URL 变了才必然取新文件。
  // 因此自有资源一律挂 ?v=；vendor 下的第三方库不随我们发版，不挂。
  const refs = [...HTML.matchAll(/<(?:script src|link rel="stylesheet" href)="([^"]+)"/g)].map((m) => m[1]);
  const missing = refs.filter((r) => !r.startsWith('vendor/') && !r.includes('?v='));
  assert.deepEqual(missing, [], `这些自有资源没带 ?v= 缓存版本号：${missing.join(', ')}`);
});

test('跨文件成员名不得重复（对象展开按顺序静默覆盖，重名不报错）', () => {
  const own = appMainMembers();
  const seen = new Map(); // 成员名 -> 归属
  const clashes = [];
  for (const n of own) seen.set(n, 'app-main.js');
  for (const [f, { keys }] of featureMixins()) {
    for (const k of keys) {
      if (seen.has(k)) clashes.push({ name: k, from: seen.get(k), to: f });
      else seen.set(k, f);
    }
  }

  // 唯一一处**有意**覆盖：workflow-client 是 v4.5 归档工作流，把 project-client
  // 的 5 个成员整套换成「归档 + 检查点 + 冲突」版本（数据源从 /projects 换成
  // /archives、快照多带 uploadKey/uploadPending）。它必须排在 project 之后展开，
  // 顺序反了就会静默退回旧实现 —— 所以下面额外钉死顺序。
  const KNOWN_OVERRIDES = new Map([
    ['projectSnapshotExtras', 'workflow-client.js'],
    ['restoreProjectExtras', 'workflow-client.js'],
    ['saveCloudProject', 'workflow-client.js'],
    ['openCloudProject', 'workflow-client.js'],
    ['loadProjects', 'workflow-client.js'],
  ]);

  const unexpected = clashes.filter((c) => KNOWN_OVERRIDES.get(c.name) !== c.to || c.from !== 'project-client.js');
  assert.deepEqual(unexpected, [],
    '成员名重复：后展开的那份会静默盖掉前一份，两份开始各自演化。' +
    '若是有意覆盖，请加进 KNOWN_OVERRIDES 并写清为什么');

  // 白名单不能腐烂：每一条都必须仍然是真实存在的重复
  const actual = new Set(clashes.filter((c) => c.from === 'project-client.js').map((c) => c.name));
  assert.deepEqual([...KNOWN_OVERRIDES.keys()].filter((n) => !actual.has(n)), [],
    'KNOWN_OVERRIDES 里的名字已经不再重复了 —— 请删掉，别留一条永远为真的断言');
});

test('覆盖关系必须真的生效：workflow 要排在 project 之后展开', () => {
  const order = [...APP_MAIN.matchAll(/\.\.\.window\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]);
  const pi = order.indexOf('projectFeatures');
  const wi = order.indexOf('workflowFeatures');
  assert.ok(pi >= 0 && wi >= 0, 'app-main.js 里找不到 project/workflow 的展开');
  assert.ok(pi < wi,
    'workflowFeatures 必须排在 projectFeatures 之后，否则那 5 个覆盖会静默失效，' +
    '归档工作流会退回 project-client 的 /projects 实现');
});
