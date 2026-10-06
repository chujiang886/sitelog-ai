#!/usr/bin/env node
'use strict';
/*
 * 报告模板拆分（app-main.js → templates.js）的守护测试。
 *
 * 和后端把业主侧模板抽到 views.py 是同一件事、同一套守法：
 * 763 行模板字符串是**数据**，不是逻辑，留在主脚本里只会把真正的逻辑埋掉。
 * 搬走之后要防三件事：
 *   1. 内容被顺手改了（用 sha256 钉死）
 *   2. 定义没有真的搬走（原文件里又长出一份）
 *   3. 加载顺序被颠倒（templates.js 必须先于 app-main.js，否则运行时是 undefined）
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const APP_MAIN = fs.readFileSync(path.join(__dirname, 'app-main.js'), 'utf8');
const TEMPLATES_JS = fs.readFileSync(path.join(__dirname, 'templates.js'), 'utf8');
const HTML = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

// 从 app-main.js 搬出时的基线（含前导注释行，逐字节）
const BLOCK_SHA256 = 'cf798d7ef10476c1015f3fa4ac7c9fbd48600645447358ad61ae5729768ad397';
const BLOCK_START = '// ====== 模板定义';
const BLOCK_LINES = 764; // 763 行模板 + 1 行前导注释

function blockSha() {
  const lines = TEMPLATES_JS.split('\n');
  const start = lines.findIndex((l) => l.includes(BLOCK_START));
  assert.ok(start >= 0, 'templates.js 里找不到模板块的起点注释');
  return crypto.createHash('sha256').update(lines.slice(start).join('\n'), 'utf8').digest('hex');
}

test('templates.js 里的模板块与搬出时逐字节一致', () => {
  assert.equal(blockSha(), BLOCK_SHA256, '模板内容被改动了 —— 若是有意改版式，请更新本测试里的基线并说明改了什么');
});

test('模板块的行数没有变（763 行模板 + 1 行前导注释）', () => {
  const lines = TEMPLATES_JS.split('\n');
  const start = lines.findIndex((l) => l.includes(BLOCK_START));
  assert.equal(lines.length - start, BLOCK_LINES + 1); // +1 是文件末尾的空行
});

test('app-main.js 里不再有模板定义，只剩引用', () => {
  assert.ok(!/const TEMPLATES/.test(APP_MAIN), 'app-main.js 里又长出了一份 TEMPLATES 定义');
  assert.ok(APP_MAIN.includes('TEMPLATES.'), 'app-main.js 里连 TEMPLATES 的引用都没了 —— 是改坏了还是换写法了？');
});

test('index.html 里 templates.js 必须排在 app-main.js 之前', () => {
  // 顶层 const 的经典脚本共享同一个全局词法环境，但**按文档顺序初始化**；
  // 顺序反了 app-main.js 执行时 TEMPLATES 还在 TDZ 里 → 运行时 ReferenceError，
  // 而 node 单测（vm 里只跑 app-main.js）根本不会发现。
  // 按 <script src> 精确匹配：注释里也会提到文件名，用裸文件名会找错位置
  const tpl = HTML.indexOf('<script src="templates.js">');
  const app = HTML.indexOf('<script src="app-main.js">');
  assert.ok(tpl > 0 && app > 0, 'index.html 里缺少 templates.js 或 app-main.js 的 <script src>');
  assert.ok(tpl < app, 'templates.js 必须出现在 app-main.js 之前');
});

test('templates.js 是纯数据：不依赖任何运行时状态', () => {
  assert.ok(!/\brequire\s*\(/.test(TEMPLATES_JS), 'templates.js 不该 require 任何东西');
  assert.ok(!/\bfetch\s*\(/.test(TEMPLATES_JS), 'templates.js 不该发请求');
  assert.ok(!/^\s*import\s/m.test(TEMPLATES_JS), 'templates.js 不该有 import');
  assert.ok(!/\bwindow\.\w+\s*=/.test(TEMPLATES_JS), 'templates.js 不该往 window 上挂东西');
  assert.ok(!/\bthis\./.test(TEMPLATES_JS), '模板里不该引用组件状态（this.*）—— 那是渲染时注入的事');
});
