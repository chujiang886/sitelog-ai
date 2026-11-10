'use strict';
// 只创建临时浏览器页面，不登录生产、不读取客户档案、不调用 AI。
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.TEST_CHROME || undefined, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.goto('about:blank');
    await page.addScriptTag({ path: path.join(__dirname, 'vendor/purify.min.js') });
    await page.addScriptTag({ path: path.join(__dirname, 'editor-state.js') });
    const result = await page.evaluate(() => {
      // GHSA-cg2g-xh64-v4q7：表达式在影子树内被禁用元素拆开。
      const host = document.createElement('div');
      const root = host.attachShadow({ mode: 'open' });
      root.append(document.createTextNode('$'), document.createElement('object'),
        document.createTextNode('{fixtureOnly}'));
      DOMPurify.sanitize(host, { IN_PLACE: true, SAFE_FOR_TEMPLATES: true });
      root.normalize();
      const shadow = root.textContent;
      // 实际编辑器净化入口：归档正文、表格、中文、人工编辑标记应保留，活动内容应删除。
      const report = '<h1>施工归档</h1><p contenteditable="true" data-photo-id="fixture">人工核对完成</p>' +
        '<table><tbody><tr><td>客户已确认</td></tr></tbody></table>' +
        '<script>window.fixtureExecuted=true</script><img src="x" onerror="window.fixtureExecuted=true">' +
        '<iframe src="https://invalid.example"></iframe><a href="javascript:alert(1)">照片说明</a>';
      const clean = sitelogEditor.sanitizeReport(report);
      const template = document.createElement('template');
      template.innerHTML = clean;
      const unsafe = template.content.querySelector('script,iframe,svg,math,[onerror],[onclick],[src],[href]');
      // 2026-11-10：旧草稿 / 云端工程 / 工程包里可能仍存着已下线的「归档合规说明」卡片，
      // 恢复时必须剥掉，否则「打开旧工程再导出」会把话术带回来。
      const legacyReport = '<h1>施工归档</h1>' +
        '<div class="pdf-compliance-note"><div class="pdf-compliance-note-title">归档合规说明</div>' +
        '<p>本记录可作为竣工归档佐证；隐蔽工程留档可追溯。</p></div><p>正文应保留</p>';
      const legacyClean = sitelogEditor.sanitizeReport(legacyReport);
      return { shadow, clean, unsafe: !!unsafe, text: template.content.textContent,
        table: !!template.content.querySelector('table td'),
        editable: !!template.content.querySelector('[contenteditable="true"][data-photo-id="fixture"]'),
        legacyNote: legacyClean.includes('pdf-compliance-note') || legacyClean.includes('归档合规说明'),
        legacyBody: legacyClean.includes('正文应保留'),
        executed: !!window.fixtureExecuted };
    });
    assert.doesNotMatch(result.shadow, /\$\{|\{\{|<%/, '影子树内残留模板表达式');
    assert.equal(result.unsafe, false);
    assert.equal(result.executed, false);
    assert.equal(result.table, true);
    assert.equal(result.editable, true);
    for (const text of ['施工归档', '人工核对完成', '客户已确认', '照片说明']) assert.ok(result.text.includes(text));
    assert.equal(result.legacyNote, false, '旧草稿里的「归档合规说明」卡片没有被剥掉');
    assert.equal(result.legacyBody, true, '剥掉合规卡片时误删了归档正文');
    console.log('PASS：影子树模板绕过被阻断，归档正文、表格和人工编辑保留，活动内容已移除，旧合规话术已剥离');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
