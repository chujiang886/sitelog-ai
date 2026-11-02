const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const parser = require('postcss-selector-parser');

test('所有锁定的选择器解析器版本均避开 GHSA-rj75-hqrm-r3gf', () => {
  const versions = Object.entries(require('./package-lock.json').packages)
    .filter(([name]) => name.endsWith('/postcss-selector-parser')).map(([, entry]) => entry.version);
  assert.ok(versions.length);
  for (const version of versions) {
    const [major, minor, patch] = version.split('.').map(Number);
    assert.ok(major > 7 || (major === 7 && (minor > 1 || minor === 1 && patch >= 6)) ||
      (major === 6 && (minor > 1 || minor === 1 && patch >= 5)), version);
  }
});

test('报告、打印及阶段选择器保持原样', () => {
  for (const selector of ['.report table > tbody > tr', '.sop-photo[data-stage="吊装施工"]',
    String.raw`.print\:hidden:hover`, '.archive:not(.hidden), #signoff canvas',
    '[contenteditable="true"] + .photo-caption']) {
    assert.equal(parser().processSync(selector, { lossless: true }), selector);
  }
});

test('大平面选择器在受限子进程中完成，不阻塞构建进程', { timeout: 8000 }, () => {
  // 公告中的 class-index 二次扫描；子进程超时会被终止，避免旧库卡住测试机。
  const output = execFileSync(process.execPath, ['-e', `
    const parser = require('postcss-selector-parser');
    const root = parser().astSync('.a'.repeat(200000));
    console.log(root.nodes[0].nodes.length);
  `], { cwd: __dirname, timeout: 5000, encoding: 'utf8', maxBuffer: 1024 });
  assert.equal(output.trim(), '200000');
});
