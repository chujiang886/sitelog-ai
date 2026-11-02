const test = require('node:test');
const assert = require('node:assert/strict');
const { SourceMapConsumer, SourceNode } = require('source-map-js');

const basic = () => ({ version: 3, sources: ['report.js'], names: [], mappings: 'AAAA',
  sourcesContent: ['document.title = "归档";\n'] });
const indexed = (line, column = 0, map = basic()) => ({ version: 3,
  sections: [{ offset: { line, column }, map }] });

test('所有锁定的 source-map-js 避开 GHSA-68fv-2mgg-jv7q', () => {
  const versions = Object.entries(require('./package-lock.json').packages)
    .filter(([name]) => name.endsWith('/source-map-js')).map(([, entry]) => entry.version);
  assert.ok(versions.length);
  for (const version of versions) {
    const [major, minor, patch] = version.split('.').map(Number);
    assert.ok(major > 1 || major === 1 && (minor > 2 || minor === 2 && patch >= 2), version);
  }
});

test('巨大或非法偏移在生成映射之前被拒绝，不进入放大循环', () => {
  for (const line of [1e12, -1, 0.5, Infinity, NaN, '1']) {
    assert.throws(() => new SourceMapConsumer(indexed(line)), /offset|integer|exceed/i, String(line));
  }
  for (const column of [-1, 0.5, Infinity, NaN, '1']) {
    assert.throws(() => new SourceMapConsumer(indexed(0, column)), /offset|integer|exceed/i, String(column));
  }
});

test('嵌套索引的累计偏移也受限', () => {
  assert.throws(() => new SourceMapConsumer(indexed(6000000, 0, indexed(6000000))), /offset|exceed/i);
});

test('正常归档脚本及中文内容映射往返保持一致', () => {
  const consumer = new SourceMapConsumer(basic());
  assert.deepEqual(consumer.originalPositionFor({ line: 1, column: 0 }),
    { source: 'report.js', line: 1, column: 0, name: null });
  const code = 'document.title = "归档";\n';
  const result = SourceNode.fromStringWithSourceMap(code, consumer).toStringWithSourceMap({ file: 'report.min.js' });
  assert.equal(result.code, code);
  const restored = new SourceMapConsumer(result.map.toJSON());
  assert.equal(restored.originalPositionFor({ line: 1, column: 0 }).source, 'report.js');
  assert.equal(restored.sourceContentFor('report.js'), code);
  assert.equal(new SourceMapConsumer(indexed(10, 3)).originalPositionFor({ line: 11, column: 4 }).source, 'report.js');
});
