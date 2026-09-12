// 为仍打开 v5.0.0 的员工页面更新 AI 方法，保留 Alpine 数据和人工编辑 DOM。
(async () => {
  try {
    const app = window.Alpine && window.Alpine.$data(document.body);
    if (!app || typeof app.aiOrganizeAll !== 'function') throw Error('请回到原有工程归档页面，再点击此书签。');
    if (app.processing || app.aiChecking) throw Error('正在整理照片，请等待本次整理结束再恢复。');
    const get = async path => {
      const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw Error('更新文件暂时无法读取，请稍后重试。');
      return response.text();
    };
    const [auth, html] = await Promise.all([get('/sitelog/auth-client.js'), get('/sitelog/')]);
    const features = new Function('window', auth + '\nreturn window.accountFeatures;')({});
    const scripts = [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('script:not([src])')];
    const updated = new Function('window', scripts.at(-1).textContent + '\nreturn siteLogApp();')({ accountFeatures: features });
    const methods = ['applySession', 'refreshCompanyStatus', 'ensureCompanyAI', 'aiOrganizeAll', 'reAnalyze', 'analyzeImage', 'callVisionAPI', 'openSettings'];
    for (const name of methods) if (typeof updated[name] !== 'function') throw Error('更新文件不完整，当前工程未更改。');
    for (const name of methods) app[name] = updated[name];
    app.aiChecking = false;
    if (!await app.refreshCompanyStatus()) return;
    app.showSettings = false;
    app.showToast(app.aiConfigured ? 'AI 已恢复，照片和审核文字均已保留，请点击 AI 一键整理。' : '页面已更新，正在等待公司 AI 配置。');
  } catch (error) { alert(error.message || '恢复未完成，请保留当前工程页面。'); }
})();
