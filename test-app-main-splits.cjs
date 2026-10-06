#!/usr/bin/env node
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
 *
 * 新增一块时：往 SPLITS 里加一行，并跑一次 `node test-app-main-splits.cjs` 确认基线。
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const read = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
const APP_MAIN = read('app-main.js');
const HTML = read('index.html');

// 每一块：从主脚本搬出去的文件、块起点（行首精确匹配）、块 sha256（搬出时）、块行数
const SPLITS = [
  {
    file: 'templates.js',
    label: '报告模板（763 行模板字符串）',
    start: '// ====== 模板定义',
    sha: 'cf798d7ef10476c1015f3fa4ac7c9fbd48600645447358ad61ae5729768ad397',
    lines: 764,
    forbiddenInAppMain: /const TEMPLATES/,
  },
  {
    file: 'ai-style.js',
    label: 'AI 文案引擎（写作铁律 + 术语库 + 清洗 + 评分）',
    start: 'const NL = String.fromCharCode(10);',
    sha: 'd135bab5551a1a4891518fd7ad670010b441bc05d4256d397f3d96032e8cce7f',
    lines: 138,
    forbiddenInAppMain: /const AI_STYLE|function polishSiteLogText|function scoreSiteLogText/,
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
    const dep = HTML.indexOf(`<script src="${s.file}">`);
    const app = HTML.indexOf('<script src="app-main.js">');
    assert.ok(dep > 0, `index.html 里缺少 ${s.file} 的 <script src>`);
    assert.ok(app > 0, 'index.html 里缺少 app-main.js 的 <script src>');
    assert.ok(dep < app, `${s.file} 必须出现在 app-main.js 之前，否则运行时是 ReferenceError`);
  });

  test(`${s.file}：是纯数据 / 纯函数，不依赖运行时状态`, () => {
    const text = read(s.file);
    assert.ok(!/\brequire\s*\(/.test(text), `${s.file} 不该 require 任何东西`);
    assert.ok(!/\bfetch\s*\(/.test(text), `${s.file} 不该发请求`);
    assert.ok(!/^\s*import\s/m.test(text), `${s.file} 不该有 import`);
    assert.ok(!/\bwindow\.\w+\s*=/.test(text), `${s.file} 不该往 window 上挂东西`);
    assert.ok(!/\bthis\./.test(text), `${s.file} 不该引用组件状态（this.*）`);
  });
}

test('app-main.js 里仍在使用搬出去的符号（不是改坏了而是换写法了）', () => {
  assert.ok(APP_MAIN.includes('TEMPLATES.'), 'app-main.js 里没有 TEMPLATES 的引用');
  assert.ok(/AI_STYLE|polishSiteLogText|scoreSiteLogText/.test(APP_MAIN),
    'app-main.js 里没有用到 AI 文案引擎 —— 是改坏了还是换写法了？');
});
