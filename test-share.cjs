const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
for (const script of scripts) new vm.Script(script[1]);
function appWithFetch(fetch) {
  const context = { fetch, console, window: {}, localStorage: { setItem() {} }, confirm: () => true, URLSearchParams, setTimeout, clearTimeout };
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
