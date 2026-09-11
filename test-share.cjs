const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
for (const script of scripts) new vm.Script(script[1]);
function appWithFetch(fetch, saved = new Map()) {
  const context = { fetch, console, window: { location: { search: '' } }, localStorage: { getItem(key) { return saved.get(key) || null; }, setItem(key, value) { saved.set(key, value); } }, confirm: () => true, URLSearchParams, setTimeout, clearTimeout };
  vm.createContext(context);
  vm.runInContext(scripts.at(-1)[1], context);
  const app = context.siteLogApp();
  app.showToast = () => {};
  app.shareToken = 'test-credential-abcdefghijklmnopqrstuvwxyz';
  return app;
}
test('生成分享、加载列表和撤回均发送凭据，成功后触发二维码绘制', async () => {
  const requests = [];
  const app = appWithFetch(async (url, options) => {
    requests.push({ url, options });
    return { status: 200, ok: true, json: async () => ({ ok: true, id: 'ABC234', url: 'https://cj-az.cn/s/ABC234', items: [] }) };
  });
  app.images = [{}];
  app.syncCoverMeta = () => {};
  app.buildSharePayload = async () => ({ html: '<p>测试</p>' });
  app.$nextTick = async () => {};
  let qrUrl;
  app.drawShareCard = (url) => { qrUrl = url; };
  await app.doShare();
  await app.loadShareList();
  await app.shareAction('ABC234', '/revoke');
  assert.equal(qrUrl, 'https://cj-az.cn/s/ABC234');
  for (const request of requests) assert.equal(request.options.headers['X-Share-Token'], app.shareToken);
  assert.ok(requests.some(r => r.url.endsWith('/revoke')));
  assert.ok(requests.some(r => r.url.endsWith('/list')));
});
test('无凭据时不发送请求，并打开配置界面', async () => {
  const app = appWithFetch(() => { throw new Error('不应请求'); });
  app.shareToken = '';
  await assert.rejects(app.shareRequest(), /导入分享配置/);
  assert.equal(app.showSettings, true);
});
test('凭据过期时提示重新导入', async () => {
  const app = appWithFetch(async () => ({ status: 401 }));
  await assert.rejects(app.shareRequest(), /凭据无效/);
  assert.equal(app.showSettings, true);
});
test('导入配置仅接受分享服务凭据', async () => {
  const app = appWithFetch(() => {});
  const token = 'imported-test-credential-abcdefghijklmnopqrstuvwxyz';
  await app.importShareConfig({ target: { files: [{ text: async () => JSON.stringify({ service: 'cj-share', token }) }], value: 'config.json' } });
  assert.equal(app.shareToken, token);
  await app.importShareConfig({ target: { files: [{ text: async () => JSON.stringify({ service: 'other', token: 'bad' }) }], value: 'config.json' } });
  assert.equal(app.shareToken, token);
});
test('本地二维码组件可编码工程分享链接', () => {
  const context = {};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('vendor/qrcode.min.js', 'utf8'), context);
  const qr = context.qrcode(0, 'M');
  qr.addData('https://cj-az.cn/s/ABC234');
  qr.make();
  assert.ok(qr.getModuleCount() >= 21);
  assert.equal(typeof qr.isDark(0, 0), 'boolean');
});
test('仅配置分享凭据时关闭设置不误报 AI Key 缺失', () => {
  const app = appWithFetch(() => {});
  app.showSettings = true;
  app.apiKey = '';
  const messages = [];
  app.showToast = (message, type) => messages.push({ message, type });
  app.closeSettings();
  assert.equal(app.showSettings, false);
  assert.equal(messages.length, 1);
  assert.notEqual(messages[0].type, 'error');
  assert.match(messages[0].message, /设置已保存/);
});
test('设置未打开时关闭回调不会保存或弹出提示', () => {
  const app = appWithFetch(() => {});
  app.showSettings = false;
  app.saveSettings = () => { throw new Error('不应保存'); };
  app.showToast = () => { throw new Error('不应提示'); };
  app.closeSettings();
});
test('两项配置均为空时也允许正常关闭设置', () => {
  const app = appWithFetch(() => {});
  app.apiKey = '';
  app.shareToken = '';
  app.showSettings = true;
  app.showToast = (_message, type) => assert.notEqual(type, 'error');
  app.closeSettings();
  assert.equal(app.showSettings, false);
});
test('用户实际调用 AI 时仍要求 AI Key', async () => {
  const app = appWithFetch(() => { throw new Error('不应发送 AI 请求'); });
  app.apiKey = '';
  let message;
  app.showToast = (text) => { message = text; };
  await app.aiOrganizeAll();
  assert.equal(app.showSettings, true);
  assert.match(message, /API Key/);
});

test('启动时仅有分享配置不会强制检查 AI，保存后分享凭据仍保留', async () => {
  const token = 'test-credential-abcdefghijklmnopqrstuvwxyz';
  const saved = new Map([['sitelog_share_token', token]]);
  const app = appWithFetch(() => { throw new Error('不应主动请求 AI 健康接口'); }, saved);
  app.switchTemplate = () => {};
  app.showToast = (_message, type) => assert.notEqual(type, 'error');
  await app.init();
  assert.equal(app.shareToken, token);
  assert.equal(app.apiKey, '');
  app.showSettings = true;
  app.closeSettings();
  assert.equal(saved.get('sitelog_share_token'), token);
});
