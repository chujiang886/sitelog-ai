const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('页面加载的 DOMPurify 与无已知公告的锁定版本一致', () => {
  const root = __dirname;
  const lock = require('./package-lock.json');
  assert.equal(lock.packages['node_modules/dompurify'].version, '3.4.17');
  assert.equal(require('./package.json').devDependencies.dompurify, '3.4.17');
  assert.deepEqual(fs.readFileSync(path.join(root, 'vendor/purify.min.js')),
    fs.readFileSync(path.join(root, 'node_modules/dompurify/dist/purify.min.js')));
  assert.match(fs.readFileSync(path.join(root, 'index.html'), 'utf8'), /src="vendor\/purify\.min\.js"/);
});
