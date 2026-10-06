// 报告 CSS 取值口径的守护测试。
//
// 【为什么必须有这条测试】
// 2026-10-05 把报告模板 CSS 从 index.html 的内联 <style> 外置成 styles.css，
// 而发布/导出抓 CSS 的方式是 `document.querySelectorAll('style')` ——
// 于是抓到的变成了**空串**。它不抛错、单测全绿、编辑器页面也完全看不出来，
// 只有业主打开档案才发现整页没有样式、只剩文字（导出 PDF 同样中招）。
//
// 这类「静默丢失」只能靠静态守卫 + 行为测试拦住，所以这里把口径钉死：
//   · 抓 CSS 只能走 window.reportCssText()
//   · 它必须优先从 styles.css 的 CSSOM 取，取不到才退回内联 <style>
//   · index.html 必须仍然链着 styles.css，且 styles.css 里必须有报告模板的规则
//
// 用法：node test-report-css.cjs
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const read = (name) => fs.readFileSync(path.join(__dirname, name), 'utf8');
const EDITOR = read('editor-state.js');
const SOURCE = EDITOR;

/** 把 editor-state.js 装进一个干净上下文，返回该上下文（可改 document 后重复调用） */
function load() {
  const ctx = { window: {}, console };
  vm.createContext(ctx);
  vm.runInContext(SOURCE, ctx);
  return ctx;
}

const sheet = (href, rules) => ({ href, cssRules: rules });
const inline = (text) => ({ textContent: text });
const fakeDoc = ({ sheets = [], inlineStyles = [] } = {}) => ({
  styleSheets: sheets,
  querySelectorAll: () => inlineStyles,
});

// ────────────────────────────────────────────────────────────────
// 1. 静态守卫：口径只有一个
// ────────────────────────────────────────────────────────────────

test('editor-state.js 必须定义并导出 window.reportCssText', () => {
  assert.match(EDITOR, /function reportCssText\s*\(/, '没找到 reportCssText 函数定义');
  assert.match(EDITOR, /window\.reportCssText\s*=\s*reportCssText/, '没把它挂到 window 上，app-main.js / project-client.js 取不到');
});

test('reportCssText 必须优先读 styles.css 的 CSSOM，而不是只抓内联 <style>', () => {
  assert.match(EDITOR, /styles\\\.css/, 'helper 里没有 styles.css 的匹配，说明它还在只抓内联 <style>');
  assert.match(EDITOR, /cssRules/, 'helper 里没有 cssRules，说明没走 CSSOM');
  assert.match(EDITOR, /styleSheets/, 'helper 里没有 styleSheets');
});

test('除 editor-state.js 外，任何自有脚本都不得再裸抓内联 <style>', () => {
  const own = fs.readdirSync(__dirname).filter((f) => f.endsWith('.js') && f !== 'editor-state.js');
  const offenders = own.filter((f) => /querySelectorAll\(\s*'style'\s*\)/.test(read(f)));
  assert.deepEqual(offenders, [], '这些文件又用 querySelectorAll(\'style\') 抓 CSS 了（会静默抓到空串）：' + offenders.join(', '));
});

test('index.html 必须仍然链着 styles.css', () => {
  const html = read('index.html');
  assert.match(html, /<link[^>]+href="styles\.css"/, 'index.html 不再引用 styles.css，reportCssText 会取不到东西');
});

test('五个取值点必须全部改走 window.reportCssText()', () => {
  const app = read('app-main.js');
  const project = read('project-client.js');
  const hits = (src, re) => (src.match(re) || []).length;
  // 导出 PDF / 导出可编辑 HTML / buildSharePayload
  assert.equal(hits(app, /window\.reportCssText\(\)/g), 3, 'app-main.js 的 3 处取值点没全改');
  // 发布分享
  assert.equal(hits(project, /window\.reportCssText\(\)/g), 1, 'project-client.js 的发布分享没改');
  // 导出工程包
  assert.match(EDITOR, /result\.css\s*=\s*reportCssText\(\)/, 'editor-state.js 的导出工程包没改');
});

test('styles.css 必须非空且含报告模板的关键规则', () => {
  const css = read('styles.css');
  assert.ok(css.trim().length > 1000, 'styles.css 太短了，像是被清空过');
  for (const marker of ['#report-content', '@media print', '.pdf-section']) {
    assert.ok(css.includes(marker), 'styles.css 里没有 ' + marker + ' —— 报告模板 CSS 可能被挪走了');
  }
});

// ────────────────────────────────────────────────────────────────
// 2. 行为测试：真的能取到、且优先取 styles.css
// ────────────────────────────────────────────────────────────────

test('优先返回 styles.css 的规则，并忽略 vendor/app.css', () => {
  const ctx = load();
  ctx.document = fakeDoc({
    sheets: [
      sheet('https://cj-az.cn/sitelog/vendor/app.css', [{ cssText: '.tailwind{color:red}' }]),
      sheet('https://cj-az.cn/sitelog/styles.css', [{ cssText: '#report-content{width:100%}' }, { cssText: '@media print{body{margin:0}}' }]),
    ],
  });
  assert.equal(ctx.window.reportCssText(), '#report-content{width:100%}\n@media print{body{margin:0}}');
});

test('没有 styles.css 时退回内联 <style>（离线打开导出的 .html 的场景）', () => {
  const ctx = load();
  ctx.document = fakeDoc({
    sheets: [sheet('https://cj-az.cn/sitelog/vendor/app.css', [{ cssText: '.tailwind{}' }])],
    inlineStyles: [inline('#report-content{}'), inline('.pdf-section{}')],
  });
  assert.equal(ctx.window.reportCssText(), '#report-content{}\n.pdf-section{}');
});

test('styles.css 读 cssRules 抛错（跨域）时退回内联 <style>，不能把导出整体搞崩', () => {
  const ctx = load();
  const hostile = { href: 'https://cdn.example.com/styles.css' };
  Object.defineProperty(hostile, 'cssRules', { get() { throw new Error('SecurityError'); } });
  ctx.document = fakeDoc({ sheets: [hostile], inlineStyles: [inline('#report-content{}')] });
  assert.equal(ctx.window.reportCssText(), '#report-content{}');
});

test('styles.css 的 cssRules 为空时也要退回内联 <style>（不能返回空串）', () => {
  const ctx = load();
  ctx.document = fakeDoc({
    sheets: [sheet('https://cj-az.cn/sitelog/styles.css', [])],
    inlineStyles: [inline('#report-content{}')],
  });
  assert.equal(ctx.window.reportCssText(), '#report-content{}');
});

test('带 query / hash 的 styles.css 也要认得出来', () => {
  const ctx = load();
  ctx.document = fakeDoc({ sheets: [sheet('https://cj-az.cn/sitelog/styles.css?v=5.4.5', [{ cssText: '#report-content{}' }])] });
  assert.equal(ctx.window.reportCssText(), '#report-content{}');
});
