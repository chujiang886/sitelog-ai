// 阶段名一致性守护：四处副本必须完全一致（顺序 + 显示名）。
//
// 【为什么需要这个测试】
// 阶段名在系统里有四个副本，浏览器无法 import Python，所以做不到单一真源：
//   1. 后端  stages.py                :: STAGE_KEYS / STAGE_DISPLAY   ← 真源
//   2. 前端  address-client.js        :: ADDRESS_STAGE_KEYS / ADDRESS_STAGE_DISPLAY
//   3. 前端  index.html <option>      :: 编辑器顶部阶段下拉框
//   4. 前端  index.html TEMPLATES     :: getTemplateHtml() 的分支映射 + 模板函数本体
//
// 漏改任意一处的后果都不是「报错」而是「静默错」：
//   - 后端漏加 → 保存草稿时被白名单拒绝（能发现，但报错信息难懂）
//   - 前端 <option> 漏加 → 用户根本选不到该阶段
//   - TEMPLATES 漏加 → getTemplateHtml() 走 else 分支静默回落成「框架施工」版式，
//     照片和文字都进了错版式的报告里，且没有任何提示。这一条最危险。
//   - 顺序不一致 → 地址公开页的阶段顺序与施工实际顺序不符，业主看到的进度条是乱的
//
// 所以本测试是纯静态分析：不启服务、不连数据库，直接读文件比对。跑一次几百毫秒。
//
// 用法：
//   node test-stage-parity.cjs
//   SITELOG_BACKEND=/path/to/cj-share/current node test-stage-parity.cjs
// 后端 stages.py 的查找顺序：环境变量 → 同目录 → ../sitelog-p0-verify → ../cj-share/current

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const HERE = __dirname;
const CLIENT_JS = path.join(HERE, 'address-client.js');
const INDEX_HTML = path.join(HERE, 'index.html');

// ---------- 定位后端 stages.py ----------

function findStagesPy() {
  const candidates = [];
  if (process.env.SITELOG_BACKEND) {
    candidates.push(path.join(process.env.SITELOG_BACKEND, 'stages.py'));
    candidates.push(process.env.SITELOG_BACKEND); // 允许直接给到文件
  }
  candidates.push(path.join(HERE, 'stages.py'));
  candidates.push(path.join(HERE, '..', 'sitelog-p0-verify', 'stages.py'));
  candidates.push(path.join(HERE, '..', 'cj-share', 'current', 'stages.py'));
  for (const c of candidates) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return path.resolve(c);
  }
  return null;
}

// ---------- 解析工具 ----------

/** 从 Python 元组/列表字面量里按出现顺序取出双引号字符串。 */
function pyStrings(block) {
  const out = [];
  const re = /"((?:[^"\\]|\\.)*)"/g;
  let m;
  while ((m = re.exec(block))) out.push(m[1].replace(/\\"/g, '"'));
  return out;
}

/** 从 Python 字典字面量里取出键值对，保持出现顺序。 */
function pyPairs(block) {
  const out = [];
  const re = /"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"/g;
  let m;
  while ((m = re.exec(block))) out.push([m[1], m[2]]);
  return out;
}

/** 从 JS 数组字面量里按顺序取出单/双引号字符串。 */
function jsStrings(block) {
  const out = [];
  const re = /(['"])((?:[^'\\]|\\.)*)\1/g;
  let m;
  while ((m = re.exec(block))) out.push(m[2].replace(/\\(['"])/g, '$1'));
  return out;
}

/** 从 JS 对象字面量里取出键值对。 */
function jsPairs(block) {
  const out = [];
  const re = /(['"])((?:[^'\\]|\\.)*)\1\s*:\s*(['"])((?:[^'\\]|\\.)*)\3/g;
  let m;
  while ((m = re.exec(block))) out.push([m[2], m[4]]);
  return out;
}

/**
 * 截取 Python 顶层赋值语句的字面量部分。
 * 用负向后顾避免把 LEGACY_STAGE_KEYS 误当成 STAGE_KEYS。
 */
function pyAssign(src, name, open, close) {
  const re = new RegExp('(?<![A-Za-z0-9_])' + name + '\\s*=\\s*\\' + open + '([\\s\\S]*?)\\' + close);
  const m = re.exec(src);
  return m ? m[1] : null;
}

/** 截取 JS 对象属性名对应的数组/对象字面量内容。 */
function jsProp(src, name, open, close) {
  const re = new RegExp('(?<![A-Za-z0-9_])' + name + '\\s*:\\s*\\' + open + '([\\s\\S]*?)\\' + close);
  const m = re.exec(src);
  return m ? m[1] : null;
}

// ---------- 断言 ----------

let failures = 0;
const report = [];

function check(label, fn) {
  try {
    fn();
    report.push('  ✓ ' + label);
  } catch (err) {
    failures++;
    report.push('  ✗ ' + label + '\n      ' + err.message);
  }
}

function eq(actual, expected, what) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(what + '\n      实际: ' + a + '\n      期望: ' + e);
}

function ok(cond, msg) {
  if (!cond) throw new Error(msg);
}

// ---------- 主流程 ----------

const stagesPath = findStagesPy();
if (!stagesPath) {
  console.error('找不到后端 stages.py。请用 SITELOG_BACKEND=<cj-share/current 目录> 指定。');
  process.exit(2);
}

const py = fs.readFileSync(stagesPath, 'utf8');
const clientJs = fs.readFileSync(CLIENT_JS, 'utf8');
const html = fs.readFileSync(INDEX_HTML, 'utf8');

// 1) 后端真源
const pyKeysBlock = pyAssign(py, 'STAGE_KEYS', '(', ')');
ok(pyKeysBlock !== null, 'stages.py 里找不到 STAGE_KEYS 元组');
const backendKeys = pyStrings(pyKeysBlock);
ok(backendKeys.length > 0, 'stages.py 的 STAGE_KEYS 解析为空');

const pyDisplayBlock = pyAssign(py, 'STAGE_DISPLAY', '{', '}');
ok(pyDisplayBlock !== null, 'stages.py 里找不到 STAGE_DISPLAY 字典');
const backendDisplay = Object.fromEntries(pyPairs(pyDisplayBlock));

// 2) 前端副本
const clientKeysBlock = jsProp(clientJs, 'ADDRESS_STAGE_KEYS', '[', ']');
ok(clientKeysBlock !== null, 'address-client.js 里找不到 ADDRESS_STAGE_KEYS');
const clientKeys = jsStrings(clientKeysBlock);

const clientDisplayBlock = jsProp(clientJs, 'ADDRESS_STAGE_DISPLAY', '{', '}');
ok(clientDisplayBlock !== null, 'address-client.js 里找不到 ADDRESS_STAGE_DISPLAY');
const clientDisplay = Object.fromEntries(jsPairs(clientDisplayBlock));

// 「需要洞口/窗位名称」的阶段（P4-C 的 1 对 1 类目）
const clientLabeledBlock = jsProp(clientJs, 'ADDRESS_LABELED_STAGES', '[', ']');
ok(clientLabeledBlock !== null, 'address-client.js 里找不到 ADDRESS_LABELED_STAGES');
const clientLabeled = jsStrings(clientLabeledBlock);

const pyLabeledBlock = pyAssign(py, 'LABELED_STAGE_KEYS', '(', ')');
ok(pyLabeledBlock !== null, 'stages.py 里找不到 LABELED_STAGE_KEYS');
const backendLabeled = pyStrings(pyLabeledBlock);

// 3) index.html 顶部阶段下拉框
const selectMatch = /<select[^>]*x-model="templateType"[^>]*>([\s\S]*?)<\/select>/.exec(html);
ok(selectMatch !== null, 'index.html 里找不到 x-model="templateType" 的 <select>');
const optionKeys = [];
{
  const re = /<option\s+value="([^"]*)"/g;
  let m;
  while ((m = re.exec(selectMatch[1]))) optionKeys.push(m[1]);
}

// 4) index.html 模板映射与模板函数本体
const mapped = []; // [阶段名, 模板函数名] 按 getTemplateHtml 里的出现顺序
{
  const re = /this\.templateType\s*===\s*'([^']+)'\s*\)\s*html\s*=\s*TEMPLATES\.([A-Za-z_$][\w$]*)\(\)/g;
  let m;
  while ((m = re.exec(html))) mapped.push([m[1], m[2]]);
}
const mappedStages = mapped.map(x => x[0]);
const mappedFns = mapped.map(x => x[1]);

/** 判断 TEMPLATES 对象里是否真的定义了某个函数属性（形如 `lifting: () => \``）。 */
function templateDefined(fnName) {
  const re = new RegExp('(?<![A-Za-z0-9_])' + fnName + '\\s*:\\s*\\(');
  return re.test(html);
}

// ---------- 断言集合 ----------

console.log('后端真源: ' + stagesPath);
console.log('阶段数: ' + backendKeys.length + ' → ' + backendKeys.join(' / '));
console.log('');

check('address-client.js 的阶段列表与后端 STAGE_KEYS 完全一致（含顺序）', () => {
  eq(clientKeys, backendKeys, 'ADDRESS_STAGE_KEYS 与 stages.STAGE_KEYS 不一致');
});

check('address-client.js 的阶段显示名与后端 STAGE_DISPLAY 完全一致', () => {
  eq(clientDisplay, backendDisplay, 'ADDRESS_STAGE_DISPLAY 与 stages.STAGE_DISPLAY 不一致');
});

check('index.html 顶部阶段下拉框与后端 STAGE_KEYS 完全一致（含顺序）', () => {
  eq(optionKeys, backendKeys, '<option> 列表与 stages.STAGE_KEYS 不一致');
});

check('index.html getTemplateHtml() 覆盖全部阶段', () => {
  eq(mappedStages, backendKeys, 'getTemplateHtml 的分支与 stages.STAGE_KEYS 不一致');
});

check('每个阶段都映射到一个真实存在的 TEMPLATES 模板函数', () => {
  for (const [stage, fn] of mapped) {
    ok(templateDefined(fn), '阶段「' + stage + '」指向 TEMPLATES.' + fn + '()，但该模板函数未定义');
  }
});

check('阶段到模板的映射是一一对应的（无两个阶段共用同一版式）', () => {
  const seen = new Map();
  for (const [stage, fn] of mapped) {
    ok(!seen.has(fn), '模板 ' + fn + ' 同时被「' + seen.get(fn) + '」和「' + stage + '」使用');
    seen.set(fn, stage);
  }
});

check('后端 EDITOR_STAGE_KEYS 与 STAGE_KEYS 相等（前端已具备全部模板）', () => {
  const block = pyAssign(py, 'EDITOR_STAGE_KEYS', '(', ')');
  if (block !== null) {
    eq(pyStrings(block), backendKeys, 'EDITOR_STAGE_KEYS 是元组字面量但与 STAGE_KEYS 不一致');
    return;
  }
  const alias = /(?<![A-Za-z0-9_])EDITOR_STAGE_KEYS\s*=\s*([A-Za-z_][\w]*)/.exec(py);
  ok(alias !== null, 'stages.py 里找不到 EDITOR_STAGE_KEYS 的定义');
  eq(alias[1], 'STAGE_KEYS', 'EDITOR_STAGE_KEYS 指向 ' + alias[1] + '，应为 STAGE_KEYS');
});

check('后端 STAGE_DISPLAY 覆盖每个阶段且无多余键', () => {
  eq(Object.keys(backendDisplay).sort(), [...backendKeys].sort(), 'STAGE_DISPLAY 的键集合与 STAGE_KEYS 不一致');
});

check('后端 STAGE_ORDER 与 STAGE_KEYS 同序', () => {
  const order = /(?<![A-Za-z0-9_])STAGE_ORDER\s*=\s*([A-Za-z_][\w]*)/.exec(py);
  ok(order !== null, 'stages.py 里找不到 STAGE_ORDER 的定义');
  eq(order[1], 'STAGE_KEYS', 'STAGE_ORDER 指向 ' + order[1] + '，应为 STAGE_KEYS');
});

check('LEGACY_STAGE_KEYS 是 STAGE_KEYS 的子集（存量阶段不能是已废弃的野名字）', () => {
  const block = pyAssign(py, 'LEGACY_STAGE_KEYS', '(', ')');
  if (block === null) return; // 允许将来整体删除
  const legacy = pyStrings(block);
  for (const k of legacy) {
    ok(backendKeys.includes(k), '存量阶段「' + k + '」不在 STAGE_KEYS 中');
  }
});

check('address-client.js 的「需要洞口名」阶段与后端 LABELED_STAGE_KEYS 完全一致', () => {
  eq(clientLabeled, backendLabeled, 'ADDRESS_LABELED_STAGES 与 stages.LABELED_STAGE_KEYS 不一致');
});

check('LABELED_STAGE_KEYS 是 STAGE_KEYS 的子集（1 对 1 类目必须是真实阶段）', () => {
  for (const k of backendLabeled) {
    ok(backendKeys.includes(k), '需要洞口名的阶段「' + k + '」不在 STAGE_KEYS 中');
  }
});

console.log(report.join('\n'));
console.log('');
if (failures) {
  console.log('阶段一致性检查未通过：' + failures + ' 项失败。');
  process.exit(1);
}
console.log('阶段一致性检查通过：' + report.length + ' 项，四处副本完全一致。');
