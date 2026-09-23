// 按框分组（1 对 1 阶段）的核心算法单测。
//
// 【为什么必须测】
// normalizeFrames 的错都是**静默错**：分组错了不报错，只是业主打开报告时
// 发现某个门洞的照片不见了，或者同一张照片在两个门洞里各出现一次。
// 这类问题上线后极难定位（师傅已经拍完、现场已经撤场），所以在这里拦住。
//
// sanitizeFrames 的错则是**发布级**的：它喂给 snapshot()，而 snapshot() 的
// 结果要前后比对两次，只要不幂等，师傅点「生成分享码」就永远报「保存期间
// 内容有修改」。所以那一组用例的核心是幂等性，不是业务规则。
//
// 用法：node test-frame-client.cjs
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const context = { window: {}, setTimeout };
vm.createContext(context);
vm.runInContext(fs.readFileSync('frame-client.js', 'utf8'), context);
const { normalizeFrames, sanitizeFrames, sectionNum, FRAMED_TEMPLATES, FRAME_LIMIT } = context.window.sitelogFrames;

// 可复现的 id 生成器，避免测试依赖 Date.now()
function idGen() { let n = 0; return () => 'fr' + (++n); }
// vm 里创建的对象属于另一个 realm，prototype 不同，deepStrictEqual 会误报。
// 走一次 JSON 往返把它拉回本 realm —— 与 test-workflow-unit.cjs 同一手法。
const copy = x => JSON.parse(JSON.stringify(x));
const nf = (frames, arrivals, nodes) => copy(normalizeFrames(frames, arrivals, nodes, idGen()));
const sf = (frames, arrivals, nodes) => copy(sanitizeFrames(frames, arrivals, nodes));

test('sectionNum 用中文序号，超出表长回落阿拉伯数字', () => {
  assert.equal(sectionNum(1), '一');
  assert.equal(sectionNum(6), '六');
  assert.equal(sectionNum(10), '十');
  assert.equal(sectionNum(11), '十一');
  assert.equal(sectionNum(20), '二十');
  // 20 段 = 9 个门洞，实际到不了；真到了也不能拼出「二十一」这种别扭的长串。
  assert.equal(sectionNum(21), '21');
});

test('只有两个 1 对 1 阶段按框循环', () => {
  assert.deepEqual(copy(FRAMED_TEMPLATES), ['框架1对1', '玻扇1对1']);
});

test('老工程没有 frames 时建一个框，把已有照片全部归入', () => {
  const frames = nf(undefined, ['a1', 'a2'], ['n1']);
  assert.equal(frames.length, 1);
  assert.equal(frames[0].label, '');
  assert.deepEqual(frames[0].arrivalIds, ['a1', 'a2']);
  assert.deepEqual(frames[0].nodeIds, ['n1']);
});

test('没有照片也没有 frames 时仍然给一个空框（编辑器不能没有框可上传）', () => {
  const frames = nf([], [], []);
  assert.equal(frames.length, 1);
  assert.deepEqual(frames[0].arrivalIds, []);
  assert.deepEqual(frames[0].nodeIds, []);
});

test('删框留下的孤儿照片归入第一框，不静默丢弃', () => {
  // f2 被删掉，它的两张照片变成孤儿
  const frames = nf([{ id: 'f1', label: '主卧窗', arrivalIds: ['a1'], nodeIds: ['n1'] }],
    ['a1'], ['n1', 'n2', 'n3']);
  assert.deepEqual(frames[0].nodeIds, ['n1', 'n2', 'n3']);
  assert.deepEqual(frames[0].arrivalIds, ['a1']);
});

test('照片被删后 frames 里的悬空引用被清掉', () => {
  // 悬空引用会被后端 checked_frames 判「窗框照片与所属分组不匹配」而拒绝整份草稿，
  // 师傅只会看到一句读不懂的报错。
  const frames = nf([{ id: 'f1', label: '主卧窗', arrivalIds: ['a1', '已删除'], nodeIds: ['n1', '也没了'] }],
    ['a1'], ['n1']);
  assert.deepEqual(frames[0].arrivalIds, ['a1']);
  assert.deepEqual(frames[0].nodeIds, ['n1']);
});

test('同一张照片不会同时留在两个框里（否则报告重复出图）', () => {
  const frames = nf([
    { id: 'f1', label: '主卧窗', arrivalIds: [], nodeIds: ['n1'] },
    { id: 'f2', label: '阳台', arrivalIds: [], nodeIds: ['n1', 'n2'] },
  ], [], ['n1', 'n2']);
  assert.deepEqual(frames[0].nodeIds, ['n1']);
  assert.deepEqual(frames[1].nodeIds, ['n2'], '重复的那张应只留在先出现的框里');
});

test('入场照片与校正节点的归属互不串台', () => {
  // arrivalIds 只认 arrivalImages，nodeIds 只认 images。放错数组的 id 视为悬空引用。
  const frames = nf([{ id: 'f1', label: '', arrivalIds: ['n1'], nodeIds: ['a1'] }], ['a1'], ['n1']);
  assert.deepEqual(frames[0].arrivalIds, ['a1'], 'a1 是进场照片，应被移回 arrivalIds');
  assert.deepEqual(frames[0].nodeIds, ['n1'], 'n1 是节点照片，应被移回 nodeIds');
});

test('空框不会被丢掉（用户刚点完「增加一个框」还没传照片）', () => {
  const frames = nf([
    { id: 'f1', label: '主卧窗', arrivalIds: ['a1'], nodeIds: [] },
    { id: 'f2', label: '阳台', arrivalIds: [], nodeIds: [] },
    { id: 'f3', label: '厨房', arrivalIds: [], nodeIds: [] },
  ], ['a1'], []);
  assert.equal(frames.length, 3);
  assert.deepEqual(frames.map(f => f.label), ['主卧窗', '阳台', '厨房']);
});

test('不改入参（snapshot 与 undoSnapshot 会共用同一份数据）', () => {
  const input = [{ id: 'f1', label: '主卧窗', arrivalIds: ['a1'], nodeIds: ['n1'] }];
  const before = copy(input);
  normalizeFrames(input, ['a1'], ['n1', 'n2'], idGen());
  assert.deepEqual(input, before, 'normalizeFrames 必须是纯函数，否则撤销会把两份状态一起改掉');
});

test('损坏的框记录被补齐成合法形状而不是抛错', () => {
  const frames = nf([
    { id: 'f1', label: '主卧窗' },                 // 缺两个 id 数组
    { label: '阳台', arrivalIds: 'not-an-array' },  // 缺 id 且类型错
  ], [], []);
  assert.equal(frames.length, 2);
  assert.deepEqual(frames[0].arrivalIds, []);
  assert.deepEqual(frames[0].nodeIds, []);
  assert.deepEqual(frames[1].arrivalIds, []);
  assert.ok(frames[1].id, '缺 id 的框要补一个，否则 DOM 上的 data-frame-id 全是 undefined');
  assert.notEqual(frames[0].id, frames[1].id);
});

test('框数超过上限时被截断，不产生一份后端拒绝的草稿', () => {
  const many = Array.from({ length: FRAME_LIMIT + 5 }, (_, i) => ({ id: 'f' + i, label: '窗' + i, arrivalIds: [], nodeIds: [] }));
  const frames = nf(many, [], []);
  assert.equal(frames.length, FRAME_LIMIT);
});

// ── sanitizeFrames：草稿落盘前的只读净化 ──────────────────────────────
//
// 这一组守的是**发布链路**而不是界面：saveCloudProject() 用第一次 snapshot()
// 算 bodyKey，发布前用第二次 snapshot() 重算比对（project-client.js 的
// unchanged()），两次不同即判「保存期间内容有修改」并拒绝发布。所以这里的
// 每个用例都可以归结成一句话——**同输入必须得同输出**。

test('sanitizeFrames 是幂等的：同一份输入连算两次结果必须完全相同', () => {
  // 这是本次事故的回归点。曾经 snapshot() 用 normalizeFrames() + newFrameId()，
  // frames 为空时每次编一个新随机 id，导致每次发布都被自己判成「内容有修改」。
  const cases = [
    [[], [], []],
    [[{ id: 'f1', label: '主卧窗', arrivalIds: ['a1'], nodeIds: ['n1'] }], ['a1'], ['n1']],
    [[{ id: 'f1', label: '主卧窗', arrivalIds: ['ghost'], nodeIds: ['n1', 'n1'] }], ['a1'], ['n1']],
  ];
  for (const [frames, arrivals, nodes] of cases) {
    const once = sanitizeFrames(frames, arrivals, nodes);
    const twice = sanitizeFrames(once, arrivals, nodes);
    assert.deepEqual(copy(once), copy(twice), '净化结果必须稳定，否则发布会被自己拦下：' + JSON.stringify(frames));
  }
});

test('sanitizeFrames 对空 frames 返回空数组，不凭空造框', () => {
  // 非按框循环的阶段 frames 恒为空。若这里补一个框，就等于给每个普通工程
  // 都塞了一个不存在的门洞。
  assert.deepEqual(sf([], ['a1'], ['n1']), []);
  assert.deepEqual(sf(null, [], []), []);
  assert.deepEqual(sf(undefined, [], []), []);
});

test('sanitizeFrames 清悬空引用并跨框去重，规则与 normalizeFrames 一致', () => {
  const frames = sf([
    { id: 'f1', label: '主卧窗', arrivalIds: ['a1', 'ghost'], nodeIds: ['n1', 'n2'] },
    { id: 'f2', label: '阳台', arrivalIds: [], nodeIds: ['n1'] },
  ], ['a1'], ['n1', 'n2']);
  assert.deepEqual(frames[0].arrivalIds, ['a1'], '指向已删照片的悬空引用要清掉');
  assert.deepEqual(frames[0].nodeIds, ['n1', 'n2']);
  assert.deepEqual(frames[1].nodeIds, [], '同一张照片不能同时留在两个框里');
});

test('sanitizeFrames 丢弃编号非法的框，但绝不替它编一个新 id', () => {
  // 与 normalizeFrames 的关键分歧：那边缺 id 就补一个（UI 自愈），这边直接丢
  // （只读净化）。补 id 会引入随机性，而 snapshot() 必须是确定性的。
  const frames = sf([
    { label: '阳台', arrivalIds: ['a1'], nodeIds: [] },   // 缺 id
    { id: 'has space', label: '厨房', nodeIds: ['n1'] },  // 编号含非法字符
    { id: 'f3', label: '主卧窗', arrivalIds: [], nodeIds: ['n1'] },
  ], ['a1'], ['n1']);
  assert.equal(frames.length, 1, '只有编号合法的框留下');
  assert.equal(frames[0].id, 'f3');
  // 被丢掉的框里的照片仍留在 images/arrivalImages 扁平数组里（调用方传进来
  // 的 arrivals 未被动过），所以一张都不会丢，只是丢了分组标签。
});

test('sanitizeFrames 不修改入参', () => {
  const input = [{ id: 'f1', label: '主卧窗', arrivalIds: ['a1', 'ghost'], nodeIds: ['n1'] }];
  const before = copy(input);
  sanitizeFrames(input, ['a1'], ['n1']);
  assert.deepEqual(copy(input), before, 'snapshot() 与 undoSnapshot 会共用同一份数据');
});

test('sanitizeFrames 补齐字段形状，保证后端 checked_frames 不拒收', () => {
  const frames = sf([{ id: 'f1' }], [], []);
  assert.deepEqual(frames, [{ id: 'f1', label: '', arrivalIds: [], nodeIds: [] }]);
  // 窗号在编辑时已限长 200，这里只是兜底。
  assert.equal(sf([{ id: 'f1', label: '窗'.repeat(300) }], [], [])[0].label.length, 200);
  // 超上限截断。
  const many = Array.from({ length: FRAME_LIMIT + 5 }, (_, i) => ({ id: 'f' + i, label: '窗' + i }));
  assert.equal(sf(many, [], []).length, FRAME_LIMIT);
});
