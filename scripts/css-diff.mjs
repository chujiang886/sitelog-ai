#!/usr/bin/env node
// 视觉回归：构建前/后 CSS 对比，截图 5 个真实元素。
//
// 用法（在仓库根）：
//   cp vendor/app.css vendor/app.css.before
//   npm run build
//   node scripts/css-diff.mjs
// 或显式指定路径：
//   node scripts/css-diff.mjs --before <file> --after <file> --out <dir>
//
// 抽出的 5 个真实元素来自 2026-09-23 vendor/app.css 补全验收：
//   ① h-12            客户 LOGO 缩略图（原始大图 → 48px）
//   ② pt-3            地址面板 details 顶部留白
//   ③ bg/border-[#1F3D2A]/5   地址说明卡片底色+边框
//   ④ bg-slate-300    地址阶段未选灰点
//   ⑤ hover:bg-white/30  公司管理按钮 hover 态
//
// 输出：<out>/preview-old.png 与 preview-new.png —— 用图片预览工具并排对比，
// 或 diff 工具（meld / image-diff），逐元素目检。
//
// 默认 <out>=.visual-diff/（仓库根，已加 .gitignore 不入库）。

import { spawn } from 'node:child_process';
import {
  copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

// ---- 解析参数 ----
const argv = process.argv.slice(2);
const arg = (k, dflt) => {
  const i = argv.indexOf('--' + k);
  return i === -1 ? dflt : argv[i + 1];
};
const BEFORE = arg('before', path.join(ROOT, 'vendor/app.css.before'));
const AFTER  = arg('after',  path.join(ROOT, 'vendor/app.css'));
const OUT    = arg('out',    path.join(ROOT, '.visual-diff'));

if (!existsSync(BEFORE)) {
  console.error(`错误：构建前 CSS 不存在: ${BEFORE}`);
  console.error('先保存当前 vendor/app.css 为 .before，再构建、再跑本脚本。');
  console.error('示例：');
  console.error('  cp vendor/app.css vendor/app.css.before');
  console.error('  npm run build');
  console.error('  node scripts/css-diff.mjs');
  process.exit(2);
}
if (!existsSync(AFTER)) {
  console.error(`错误：构建后 CSS 不存在: ${AFTER}`);
  process.exit(2);
}

mkdirSync(OUT, { recursive: true });

// ---- 5 元素的预览页（CSS 由参数注入）----
function buildPage(cssRel) {
  const logoSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="64">'
    + '<rect width="220" height="64" rx="6" fill="#1F3D2A"/>'
    + '<text x="110" y="40" font-size="22" fill="#D8C39A" text-anchor="middle" font-family="sans-serif">'
    + '初匠 CHUJIANG</text></svg>';
  const logoUri = 'data:image/svg+xml;base64,' + Buffer.from(logoSvg).toString('base64');
  return `<!doctype html><html lang="zh"><head><meta charset="utf-8">
<link rel="stylesheet" href="${cssRel}">
<style>
body{font-family:-apple-system,system-ui,sans-serif;background:#f4f5f7;padding:18px;margin:0}
.addr-dot{width:.5rem;height:.5rem}
.wrap{max-width:560px;margin:0 auto;background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.section{margin-bottom:22px}
.label{font-size:13px;font-weight:700;color:#555;margin-bottom:6px}
.hdr{display:flex;gap:8px;align-items:center;background:#1F3D2A;padding:12px;border-radius:8px}
</style>
</head><body><div class="wrap">
<div class="section"><div class="label">① 客户 LOGO · h-12</div>
  <img src="${logoUri}" class="h-12 border rounded bg-white p-1" alt="LOGO"></div>
<div class="section"><div class="label">② 地址面板 · pt-3</div>
  <details class="border-t pt-3 mt-3" open>
    <summary class="text-sm cursor-pointer font-semibold">客户 LOGO（可选）</summary>
    <div class="mt-2"><p class="text-sm text-slate-600">地址面板展开内容（pt-3 顶部留白）。</p></div>
  </details></div>
<div class="section"><div class="label">③ 地址说明卡片 · bg-[#1F3D2A]/5 + border-[#1F3D2A]</div>
  <div class="bg-[#1F3D2A]/5 border border-[#1F3D2A] text-[#1F3D2A] rounded p-3 text-sm">
    收件地址已确认：汕头市龙湖区 xx 路 xx 号。如无误请继续下一步。</div></div>
<div class="section"><div class="label">④ 地址阶段点 · 未选 bg-slate-300 / 已选 bg-[#B8924A]</div>
  <div class="flex items-center gap-4">
    <span class="addr-dot rounded-full shrink-0 bg-slate-300 inline-block"></span><span class="text-sm">未勾选（灰点）</span>
    <span class="addr-dot rounded-full shrink-0 bg-[#B8924A] inline-block"></span><span class="text-sm">已勾选（金点）</span>
  </div></div>
<div class="section"><div class="label">⑤ 公司管理按钮 · hover:bg-white/30（基础态）</div>
  <div class="hdr">
    <button class="px-3 py-1.5 text-sm bg-white/20 hover:bg-white/30 rounded transition">⚙ 公司管理</button>
  </div></div>
</div></body></html>`;
}

// ---- 拷贝 CSS + 生成两版预览页 ----
const beforeName = path.basename(BEFORE);
const afterName = path.basename(AFTER);
copyFileSync(BEFORE, path.join(OUT, beforeName));
copyFileSync(AFTER,  path.join(OUT, afterName));
writeFileSync(path.join(OUT, 'preview-old.html'), buildPage(beforeName));
writeFileSync(path.join(OUT, 'preview-new.html'), buildPage(afterName));

// ---- 截图（用本机 Chrome，不必下载 Playwright）----
const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chrome) {
  console.error('找不到 Chrome 或 chromium。设置 CHROME_PATH 环境变量。');
  process.exit(2);
}

const shot = (htmlFile, pngFile) => new Promise((res, rej) => {
  const r = spawn(chrome, [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
    '--window-size=620,920',
    `--screenshot=${path.join(OUT, pngFile)}`,
    `file://${path.join(OUT, htmlFile)}`,
  ], { stdio: ['ignore', 'inherit', 'inherit'] });
  r.on('exit', (code) => code === 0 ? res() : rej(new Error(`chrome exit ${code} for ${htmlFile}`)));
});

await shot('preview-old.html', 'preview-old.png');
await shot('preview-new.html', 'preview-new.png');

// ---- 类数变化（粗略统计，CSS 选择器里有「.类名」的总数）----
function classCount(p) {
  const css = readFileSync(p, 'utf8');
  const set = new Set();
  for (const m of css.matchAll(/\.((?:[\w-]|\\.)+)/g)) {
    set.add(m[1].replace(/\\/g, ''));
  }
  return set.size;
}
const beforeN = classCount(BEFORE);
const afterN = classCount(AFTER);
const delta = afterN - beforeN;

console.log('✓ 已生成对比图：');
console.log(`  ${path.join(OUT, 'preview-old.png')}  ← 构建前  ${statSync(BEFORE).size}B / ~${beforeN} 个类`);
console.log(`  ${path.join(OUT, 'preview-new.png')}  ← 构建后  ${statSync(AFTER).size}B / ~${afterN} 个类`);
console.log(`  类数变化：${delta >= 0 ? '+' : ''}${delta}`);
console.log('');
console.log('对比方法：用图片预览工具并排打开两图（或 diff 工具），逐元素目检。');
console.log('注意：构建后多余的死类（如在注释里举例的类名被 Tailwind 扫到）会随 vendor/app.css 变化无视觉副作用，');
console.log('      真实视觉差异只看预览图；类数变化仅作辅助判断。');