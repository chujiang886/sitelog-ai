const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = __dirname;
const baseline = () => JSON.parse(fs.readFileSync(path.join(root, 'security/production-runtime-baseline.json'), 'utf8'));
function runtimeFiles() {
  const names = fs.readdirSync(root).filter(name => /\.(js|html|css)$/.test(name));
  function walk(directory) {
    for (const entry of fs.readdirSync(path.join(root, directory), { withFileTypes: true })) {
      const name = directory + '/' + entry.name;
      if (entry.isDirectory()) walk(name);
      else if (/\.(js|html|css)$/.test(name)) names.push(name);
    }
  }
  walk('vendor');
  return names.sort();
}

test('纯修复候选不引入生产版之外的页面或运行脚本', () => {
  const data = baseline();
  assert.equal(data.production_frontend_commit, '686c736ff7a3c3a3fa5511a00a5ee78a086ba3d6');
  assert.deepEqual(runtimeFiles(), Object.keys(data.runtime_sha256).sort());
  assert.equal(fs.existsSync(path.join(root, 'sitelog-track.js')), false);
});

test('除批准的 DOMPurify 安全补丁外，生产页面、模板、CSS及业务代码字节不变', () => {
  const data = baseline();
  assert.deepEqual(data.permitted_runtime_changes, ['vendor/purify.min.js']);
  for (const [name, entry] of Object.entries(data.runtime_sha256)) {
    if (data.permitted_runtime_changes.includes(name)) continue;
    assert.match(entry.sha256, /^[a-f0-9]{64}$/, name);
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex');
    assert.equal(actual, entry.sha256, name);
  }
});
