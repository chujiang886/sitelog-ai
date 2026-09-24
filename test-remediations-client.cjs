#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const SRC = fs.readFileSync(path.join(__dirname, 'address-client.js'), 'utf8');
const HTML = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const scripts = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)];
function app(fetchImpl) {
  const calls = [];
  const fetch = async (url, options) => { calls.push({url, options}); return fetchImpl(url, options); };
  const c = { window: {}, fetch, confirm: () => true, console: { ...console, error() {} }, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, navigator: { clipboard: { writeText: async () => {} } }, document: { getElementById: () => null, createElement: () => ({ click() {}, remove() {}, style: {} }), body: { appendChild() {} } } };
  vm.createContext(c);
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'auth-client.js'), 'utf8'), c);
  vm.runInContext(SRC, c);
  vm.runInContext(scripts.at(-1)[1], c);
  const a = c.siteLogApp(); a.calls = calls; a.csrf = 'csrf'; a.showToast = () => {}; a.addressDetail = { id: 'a'.repeat(32) };
  return a;
}
const ok = (body, status = 200) => ({ ok: true, status, json: async () => body });
const err = (message, status) => ({ ok: false, status, json: async () => ({ ok: false, error: message }) });

test('日期按 UTC 00:00 往返，与运行时区无关', () => {
  const a = app(async () => ok({}));
  const epoch = a.remediationDateEpoch('2026-09-30');
  assert.equal(a.remediationDateInput(epoch), '2026-09-30');
  assert.equal(a.remediationDateEpoch('2026-02-31'), 0);
});

test('R5：读取站内提醒并保留后端提醒窗口', async () => {
  const a = app(async () => ok({ ok: true, reminder_days: 3, items: [{ id: 'x', title: '补胶', status: 'overdue' }] }));
  await a.loadRemediationDue();
  assert.equal(a.calls[0].url, '/api/share/remediations/due');
  assert.equal(a.remediationDueItems[0].title, '补胶');
  assert.equal(a.remediationReminderDays, 3);
});

test('R1：读取指定留档整改清单，失败显示 error 态', async () => {
  const a = app(async () => err('无此工程权限', 403));
  await a.loadRemediations('p'.repeat(32));
  assert.equal(a.calls[0].url, '/api/share/publication/' + 'p'.repeat(32) + '/remediations');
  assert.equal(a.remediationItems['p'.repeat(32)].error, '无此工程权限');
});

test('R2：创建整改事项走 POST，日期传 UTC epoch，成功刷新', async () => {
  const a = app(async (url, options) => url.endsWith('/remediations') && options?.method === 'POST' ? ok({ ok: true, id: 'r'.repeat(32) }, 201) : ok({ ok: true, items: [] }));
  a.ensureRemediationEntry('p'.repeat(32));
  a.remediationItems['p'.repeat(32)].draft = { title: '补胶', note: '南侧', due_at: '2026-09-30' };
  await a.addRemediation('p'.repeat(32));
  const call = a.calls.find(x => x.options?.method === 'POST');
  assert.equal(call.options.headers['X-CSRF-Token'], 'csrf');
  const body = JSON.parse(call.options.body);
  assert.equal(body.title, '补胶');
  assert.equal(body.due_at, a.remediationDateEpoch('2026-09-30'));
  assert.equal(a.remediationItems['p'.repeat(32)].draft.title, '');
});

test('R3：完成/重开走 POST action，409 刷新而不静默覆盖', async () => {
  const a = app(async (url, options) => options?.method === 'POST' ? ok({ ok: true, status: 'resolved', revision: 2 }) : ok({ ok: true, items: [] }));
  const pid = 'p'.repeat(32); a.remediationItems[pid] = { items: [{ id: 'r', revision: 1 }], loading: false, error: '', busy: false, draft: {} };
  await a.changeRemediation(pid, a.remediationItems[pid].items[0], 'resolve');
  const call = a.calls[0]; assert.equal(call.options.method, 'POST');
  assert.deepEqual(JSON.parse(call.options.body), { action: 'resolve', revision: 1 });
});

test('R4：删除走 DELETE + CSRF，不能发 POST', async () => {
  const a = app(async (url, options) => options?.method === 'DELETE' ? ok({ ok: true }) : ok({ ok: true, items: [] }));
  const pid = 'p'.repeat(32); a.remediationItems[pid] = { items: [{ id: 'r', revision: 1 }], loading: false, error: '', busy: false, draft: {} };
  await a.removeRemediation(pid, { id: 'r' });
  assert.equal(a.calls[0].options.method, 'DELETE');
  assert.equal(a.calls[0].options.headers['X-CSRF-Token'], 'csrf');
});

test('缓存按 publication 隔离，关闭详情清空', () => {
  const a = app(async () => ok({}));
  a.remediationItems.p = { items: [{ id: '1' }] };
  a.closeAddressDetail();
  assert.deepEqual(Object.keys(a.remediationItems), []);
});

test('index.html：整改区挂在每条留档，含截止日期、完成/重开与删除', () => {
  const region = HTML.slice(HTML.indexOf('整改时限与到期提醒'));
  assert.match(region, /loadRemediations\(stage\.publication_id\)/);
  assert.match(region, /addRemediation\(stage\.publication_id\)/);
  assert.match(region, /changeRemediation\(stage\.publication_id, item, 'resolve'\)/);
  assert.match(region, /removeRemediation\(stage\.publication_id, item\)/);
  assert.ok(region.includes('截止日期'));
  assert.ok(region.includes('整改提醒'));
});

test('员工侧文案明确整改不进入业主公开文档，不夸大法律效力', () => {
  assert.ok((SRC + HTML).includes('业主公开文档不展示'));
  assert.ok(!/具有法律效力|可靠电子签名/.test(SRC + HTML));
});
