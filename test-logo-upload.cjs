#!/usr/bin/env node
/*
 * 客户 LOGO 上传前的预处理（index.html :: prepareLogoUpload）单元测试。
 *
 * 【为什么必须单独钉住这个函数】
 * LOGO 的整条链路里，只有这里能保证「传上去的东西还是 LOGO」。
 * 它旁边就躺着一个 `compressDataUrl()`——那个函数**固定输出 JPEG**，
 * 是给报告正文照片用的。任何人「顺手复用它」都会造成同一个静默事故：
 *
 *   公司 LOGO 的透明底被填成黑色，贴到深墨绿（#1F3D2A）的报告封面上，
 *   整个 LOGO 变成一块看不出来的黑块。
 *
 * 这个事故不会报错、不会抛异常、后端也照样收下——它只是**难看**，
 * 而截图里封面本来就是深色，很容易被当成「LOGO 没传上去」反复重试。
 * 所以「PNG 进必须 PNG 出」是一条必须用断言钉住的属性。
 *
 * 另一个静默点是「缩完反而更大」：小尺寸截图重新编码 PNG 经常比原图大。
 * 那种情况下必须保留原图，否则为了「压缩」白掉一次画质，体积还涨了。
 *
 * 本测试把两个方法从 index.html 里抽出来，在 Node 里用 DOM 桩真跑一遍。
 * 不启浏览器、不连后端，几百毫秒跑完。
 *
 * 用法：node test-logo-upload.cjs
 *      SITELOG_BACKEND=/path/to/cj-share/current node test-logo-upload.cjs
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const HERE = __dirname;
const INDEX_HTML = path.join(HERE, 'index.html');

if (!fs.existsSync(INDEX_HTML)) {
  console.error(`找不到 ${INDEX_HTML}\n请在本文件所在目录运行（cj-sitelog-web/current）。`);
  process.exit(2);
}

const html = fs.readFileSync(INDEX_HTML, 'utf8');

let passed = 0;
const failures = [];
function check(name, condition, detail) {
  if (condition) passed++;
  else failures.push(`${name}${detail ? ' —— ' + detail : ''}`);
}

// ---------- 从 index.html 里抽方法源码 ----------
//
// 用花括号配平截取整个方法体。这两个方法里没有「字符串里带花括号」的情况，
// 抽取后下面还会断言截出来的东西确实长得对（含 canvas / FileReader），
// 避免配平写歪了却静默通过。

function extractMethod(source, name) {
  // 只认**行首的定义**：`        fileToDataUrl(file) {`
  // 不能直接 indexOf(name + '(')——那样会先撞上调用点
  // （`const x = await this.prepareLogoUpload(file);`），
  // 截出来的是半句话，vm 直接 SyntaxError。
  const re = new RegExp('^[ \\t]*(?:async[ \\t]+)?' + name + '[ \\t]*\\(', 'm');
  const m = re.exec(source);
  if (!m) return null;
  const head = m[0].includes('async')
    ? m.index + m[0].search(/async/)
    : m.index + m[0].indexOf(name);
  const open = source.indexOf('{', source.indexOf(')', head));
  if (open < 0) return null;
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    const ch = source[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return source.slice(head, i + 1);
    }
  }
  return null;
}

const SRC_FILE_TO_DATA_URL = extractMethod(html, 'fileToDataUrl');
const SRC_PREPARE = extractMethod(html, 'prepareLogoUpload');
const SRC_UPLOAD = extractMethod(html, 'uploadClientLogo');

// 【为什么必须先剥注释再断言】
// 这些函数的注释里会**提到**被禁用的写法（「这里不用 createObjectURL」、
// 「revoke 会让 drawImage 拿不到像素」）。如果直接拿原文做 `indexOf` 排序或
// `includes` 判断，注释会把守卫喂饱：既可能假通过，也可能假失败。
// 守卫只能看**代码**。所以下面所有语义断言一律用 CODE_* 版本。
function stripComments(src) {
  if (src === null) return null;
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const CODE_PREPARE = stripComments(SRC_PREPARE);
const CODE_UPLOAD = stripComments(SRC_UPLOAD);

check('从 index.html 抽出了 fileToDataUrl', SRC_FILE_TO_DATA_URL !== null);
check('从 index.html 抽出了 prepareLogoUpload', SRC_PREPARE !== null);
check('从 index.html 抽出了 uploadClientLogo', SRC_UPLOAD !== null);
check('抽出的 prepareLogoUpload 确实带 canvas（配平没截歪）',
  CODE_PREPARE !== null && CODE_PREPARE.includes('canvas'));
check('抽出的 fileToDataUrl 确实带 FileReader（配平没截歪）',
  SRC_FILE_TO_DATA_URL !== null && SRC_FILE_TO_DATA_URL.includes('FileReader'));
check('抽出的 uploadClientLogo 确实带 clientLogoFiles（配平没截歪）',
  CODE_UPLOAD !== null && CODE_UPLOAD.includes('clientLogoFiles'));

// ---------- 静态结构守卫 ----------
//
// 有些回退方式在行为上「碰巧也对」，但把接口语义弄丢了，必须从源码层面拦。

check('上传 LOGO 走的是 prepareLogoUpload，不是裸的 fileToDataUrl',
  CODE_UPLOAD !== null &&
  /prepareLogoUpload\(/.test(CODE_UPLOAD) &&
  !/=\s*await\s+this\.fileToDataUrl\(/.test(CODE_UPLOAD),
  '裸 fileToDataUrl 会把 8MB 原图直接 POST 上去，员工要等、报告变大、业主端变慢');

check('prepareLogoUpload 不经过固定输出 JPEG 的 compressDataUrl',
  CODE_PREPARE !== null && !/compressDataUrl/.test(CODE_PREPARE),
  'compressDataUrl 硬编码 image/jpeg，会让 PNG 的透明底变成黑块');

check('PNG 分支显式指定 image/png 输出',
  CODE_PREPARE !== null && /toDataURL\(\s*['"]image\/png['"]/.test(CODE_PREPARE),
  '不显式指定格式就保不住透明度');

check('JPEG 分支先铺白底再画（否则透明区域变黑）',
  CODE_PREPARE !== null &&
  /image\/jpeg/.test(CODE_PREPARE) &&
  /fillStyle\s*=\s*['"]#fff(?:fff)?['"]/.test(CODE_PREPARE) &&
  CODE_PREPARE.indexOf('fillRect') < CODE_PREPARE.indexOf('drawImage'),
  'fillRect 必须在 drawImage 之前');

check('缩完更大时保留原图（不为「压缩」白掉画质）',
  CODE_PREPARE !== null && /\.length\s*<\s*original\.length\s*\?\s*\w+\s*:\s*original/.test(CODE_PREPARE));

check('上传前先校验 MIME 白名单，不把非图片丢给 FileReader',
  CODE_PREPARE !== null && /\^image\\\/\(png\|jpeg\|webp\)\$/.test(CODE_PREPARE));

check('不再使用 createObjectURL（原图已经是 data URL，多开一个 blob 只是多一处 revoke 时序风险）',
  CODE_PREPARE !== null && !/URL\.createObjectURL\s*\(/.test(CODE_PREPARE));

// ---------- DOM 桩 ----------

function makeEnv({ naturalWidth, naturalHeight, encodedLength }) {
  const calls = { drawImage: [], fillRect: [], toDataURL: [], encodedWith: [] };

  class FakeImage {
    set src(value) {
      this._src = value;
      this.naturalWidth = naturalWidth;
      this.naturalHeight = naturalHeight;
      if (this.onload) this.onload();
    }
    get src() { return this._src; }
  }

  class FakeFileReader {
    readAsDataURL(file) {
      this.result = file.__dataUrl;
      if (this.onload) this.onload({ target: { result: this.result } });
    }
  }

  const context2d = {
    fillStyle: '',
    fillRect(x, y, w, h) { calls.fillRect.push({ x, y, w, h, fillStyle: context2d.fillStyle }); },
    drawImage(img, x, y, w, h) { calls.drawImage.push({ x, y, w, h }); },
  };

  const document = {
    createElement(tag) {
      if (tag !== 'canvas') throw new Error('只应创建 canvas，实际创建了 ' + tag);
      const canvas = {
        width: 0, height: 0,
        getContext(kind) { return kind === '2d' ? context2d : null; },
        toDataURL(type, quality) {
          calls.toDataURL.push({ type, quality, w: canvas.width, h: canvas.height });
          calls.encodedWith.push(type);
          return 'data:' + type + ';base64,' + 'A'.repeat(encodedLength);
        },
      };
      return canvas;
    },
  };

  const sandbox = {
    console,
    document,
    Image: FakeImage,
    FileReader: FakeFileReader,
    // 故意让 createObjectURL 抛错：一旦有人把它加回来，测试立刻炸。
    URL: {
      createObjectURL() { throw new Error('不应使用 createObjectURL'); },
      revokeObjectURL() {},
    },
  };
  vm.createContext(sandbox);

  const methods = {};
  for (const [name, src] of [['fileToDataUrl', SRC_FILE_TO_DATA_URL], ['prepareLogoUpload', SRC_PREPARE]]) {
    if (src === null) continue;
    // 源码里可能是 `async prepareLogoUpload(...) {...}`。
    // 直接拼 `function async x()` 是语法错误，得把 async 提到 function 前面。
    const isAsync = /^async[ \t]/.test(src);
    const body = isAsync ? src.replace(/^async[ \t]+/, '') : src;
    methods[name] = vm.runInContext('(' + (isAsync ? 'async ' : '') + 'function ' + body + ')', sandbox, { filename: name });
  }
  return { methods, calls };
}

function fakeFile({ type, dataUrl }) {
  return { type, name: 'logo.' + type.split('/')[1], __dataUrl: dataUrl };
}

const PNG_URL = 'data:image/png;base64,' + 'P'.repeat(3000);
const JPEG_URL = 'data:image/jpeg;base64,' + 'J'.repeat(3000);
const WEBP_URL = 'data:image/webp;base64,' + 'W'.repeat(3000);

async function behaviorTests() {
  // ---------- 小图不缩放，原样返回 ----------
  {
    const { methods, calls } = makeEnv({ naturalWidth: 200, naturalHeight: 80, encodedLength: 3000 });
    const out = await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/png', dataUrl: PNG_URL }));
    check('小 PNG 原样返回（没白跑一次 canvas）', out === PNG_URL, '实际：' + String(out).slice(0, 40));
    check('小图不创建 canvas 编码', calls.toDataURL.length === 0);
  }

  // ---------- 大图缩放，且 PNG 保持 PNG ----------
  {
    const { methods, calls } = makeEnv({ naturalWidth: 4000, naturalHeight: 2000, encodedLength: 500 });
    const out = await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/png', dataUrl: PNG_URL }));
    check('大 PNG 缩放后仍以 image/png 编码（透明底不丢）',
      calls.encodedWith.includes('image/png'),
      '实际编码格式：' + JSON.stringify(calls.encodedWith));
    check('大 PNG 的输出前缀仍是 data:image/png', /^data:image\/png;base64,/.test(out), '实际：' + String(out).slice(0, 40));
    check('长边缩到 maxEdge=1200', calls.toDataURL.length === 1 && calls.toDataURL[0].w === 1200, JSON.stringify(calls.toDataURL[0]));
    check('短边按比例缩放（4000x2000 → 1200x600）', calls.toDataURL[0].h === 600, JSON.stringify(calls.toDataURL[0]));
    check('PNG 不铺白底（铺了就等于毁掉透明通道）', calls.fillRect.length === 0);
  }

  // ---------- JPEG 铺白底 ----------
  {
    const { methods, calls } = makeEnv({ naturalWidth: 4000, naturalHeight: 2000, encodedLength: 500 });
    const out = await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/jpeg', dataUrl: JPEG_URL }));
    check('JPEG 缩放时先铺白底再画',
      calls.fillRect.length === 1 && calls.drawImage.length === 1,
      JSON.stringify({ fillRect: calls.fillRect, drawImage: calls.drawImage }));
    check('JPEG 输出仍是 image/jpeg', /^data:image\/jpeg;base64,/.test(out), '实际：' + String(out).slice(0, 40));
  }

  // ---------- WebP 保持 WebP ----------
  {
    const { methods, calls } = makeEnv({ naturalWidth: 3000, naturalHeight: 3000, encodedLength: 500 });
    await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/webp', dataUrl: WEBP_URL }));
    check('WebP 保持 WebP（不被改成 JPEG）', calls.encodedWith.includes('image/webp'), JSON.stringify(calls.encodedWith));
  }

  // ---------- 缩完更大就保留原图 ----------
  {
    const { methods } = makeEnv({ naturalWidth: 4000, naturalHeight: 2000, encodedLength: 9000 });
    const out = await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/png', dataUrl: PNG_URL }));
    check('缩完比原图更大时保留原图', out === PNG_URL, '缩完反而涨到 9000 字符还是被采用了');
  }

  // ---------- 小尺寸但体积超标，仍要压 ----------
  {
    const { methods, calls } = makeEnv({ naturalWidth: 800, naturalHeight: 400, encodedLength: 100 });
    const big = 'data:image/png;base64,' + 'P'.repeat(2000000);
    const out = await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'image/png', dataUrl: big }));
    check('尺寸达标但体积超 maxDataUrl 时仍走压缩', calls.toDataURL.length === 1, '实际编码次数：' + calls.toDataURL.length);
    check('压完更小就采用压缩结果', out !== big && out.length < big.length);
  }

  // ---------- 非图片格式直接拒 ----------
  {
    const { methods } = makeEnv({ naturalWidth: 10, naturalHeight: 10, encodedLength: 10 });
    let caught = null;
    try {
      await methods.prepareLogoUpload.call(methods, fakeFile({ type: 'application/pdf', dataUrl: 'data:application/pdf;base64,AAAA' }));
    } catch (e) { caught = e; }
    check('非 PNG/JPG/WebP 在进 FileReader 之前就被拒',
      caught !== null && /仅支持/.test(caught.message), caught ? caught.message : '没有抛错');
  }
}

// ---------- 跨文件守卫：前端上限不能超过后端上限 ----------

function findBackendLogos() {
  const candidates = [];
  if (process.env.SITELOG_BACKEND) {
    candidates.push(path.join(process.env.SITELOG_BACKEND, 'client_logos.py'));
    candidates.push(process.env.SITELOG_BACKEND);
  }
  candidates.push(path.join(HERE, 'client_logos.py'));
  candidates.push(path.join(HERE, '..', 'sitelog-p0-verify', 'client_logos.py'));
  candidates.push(path.join(HERE, '..', 'cj-share', 'current', 'client_logos.py'));
  return candidates.find((p) => fs.existsSync(p)) || null;
}

const backendLogos = findBackendLogos();
const backendSource = backendLogos ? fs.readFileSync(backendLogos, 'utf8') : null;
const backendMax = backendSource
  ? /(?<![A-Za-z0-9_])MAX_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024/.exec(backendSource)
  : null;

check('找到后端 client_logos.py 并解析出 MAX_BYTES', backendMax !== null, '查找路径：' + String(backendLogos));

if (backendMax !== null) {
  const limit = Number(backendMax[1]) * 1024 * 1024;
  const frontendDefault = /prepareLogoUpload\s*\([^)]*maxDataUrl\s*=\s*(\d+)/.exec(SRC_PREPARE || '');
  check('解析出 prepareLogoUpload 的 maxDataUrl 默认值', frontendDefault !== null);
  if (frontendDefault !== null) {
    const chars = Number(frontendDefault[1]);
    const approxBytes = Math.floor((chars * 3) / 4);
    check('前端目标体积 < 后端上限（否则员工会看到后端报错）',
      approxBytes < limit,
      `前端约 ${approxBytes} 字节 vs 后端 ${limit} 字节`);
  }
  // 界面文案里的「8MB」必须和后端真实上限一致，不能各说各话。
  const copy = /LOGO（PNG\s*\/\s*JPG\s*\/\s*WebP，最大\s*(\d+)\s*MB）/.exec(html);
  check('LOGO 库说明文案里的体积与后端 MAX_BYTES 一致',
    copy !== null && Number(copy[1]) * 1024 * 1024 === limit,
    copy ? `文案写 ${copy[1]}MB，后端是 ${limit / 1024 / 1024}MB` : '没找到说明文案');
}

// ---------- 主流程 ----------

behaviorTests().then(() => {
  console.log('');
  console.log('LOGO 上传检查：' + passed + ' 项通过' + (failures.length ? '，' + failures.length + ' 项失败' : ''));
  for (const f of failures) console.log('  ✗ ' + f);
  console.log('');
  if (failures.length) {
    console.log('LOGO 上传检查未通过。');
    process.exit(1);
  }
  console.log('LOGO 上传检查通过。');
}).catch((e) => {
  console.error('测试自身出错：', e);
  process.exit(2);
});
