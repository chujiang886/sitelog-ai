// 员工登录与管理员设置。真实会话仅由服务器 HttpOnly Cookie 保存。
window.accountFeatures = {
  accountUser: null, csrf: '', authBusy: false, authError: '',
  showLogin: false, showPassword: false, showAdmin: false,
  aiConfigured: false, aiChecking: false, aiProvider: 'qwen', adminMessage: '',
  loginForm: { username: '', password: '' },
  passwordForm: { current: '', next: '', confirm: '' },
  employeeForm: { username: '', display_name: '', password: '', role: 'staff' },
  employeeList: [], editingUser: null, editForm: {}, auditItems: [],
  operations: null, operationsBusy: false, operationsError: '',
  companyAI: { provider: 'qwen', name: '', protocol: 'openai', base_url: '', model: '', key: '' },
  aiPresets: [], companyAILoaded: false, companyAIModel: '',
  availableAIModels: [], aiModelMessage: '', aiConfigMessage: '',
  aiModelReferences: [
    {name:'Hy4 preview',id:'hy4-preview'}, {name:'Hy3',id:'hy3'},
    {name:'DeepSeek-V4.1-Flash',id:'deepseek-flash'},
    {name:'GLM-5.3',id:'glm-5.3'}, {name:'GLM-5.3-Flash',id:'glm-5.3-flash'},
    {name:'GLM-5.2',id:'glm-5.2'}, {name:'GLM-5.1',id:'glm-5.1'},
    {name:'GLM-5V-Turbo',id:'glm-5v-turbo'}, {name:'MiniMax-M3',id:'MiniMax-M3'},
    {name:'通义千问 Qwen3 VL Plus',id:'qwen3-vl-plus'},
  ],

  async sessionRequest(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.method && options.method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRF-Token'] = this.csrf;
    }
    const response = await fetch('/api/share' + path, { ...options, credentials: 'same-origin', cache: 'no-store', headers });
    if (response.status === 401) {
      this.accountUser = null;
      this.showLogin = true;
      throw new Error('登录已过期，请重新登录；当前审核内容已保留');
    }
    if (response.status === 428) {
      this.showPassword = true;
      throw new Error('请先修改初始密码，再继续操作');
    }
    return response;
  },

  async accountJSON(path, payload) {
    const response = await this.sessionRequest(path, payload === undefined ? {} : { method: 'POST', body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok || data.ok === false) {const error=new Error(data.error || '操作未完成，请重试');error.status=response.status;throw error;}
    return data;
  },

  applySession(data) {
    this.accountUser = data.user;
    this.csrf = data.csrf;
    this.aiConfigured = !!data.ai.configured;
    this.apiProvider = data.ai.provider;
    this.companyAIModel = data.ai.model || ({qwen:'qwen-vl-plus',openai:'gpt-4o-mini',tencent:'HY-Vision-2.0-Instruct'}[data.ai.provider] || '');
    if (!this.showAdmin) this.companyAI.provider = data.ai.provider;
    this.showLogin = false;
    this.showPassword = !!data.user.must_change_password;
    if (!this.archivePerson) this.archivePerson = data.user.display_name;
  },

  async refreshCompanyStatus(quiet = false) {
    if (!this.accountUser) return false;
    try {
      this.applySession(await this.accountJSON('/auth/me'));
      return !this.showPassword;
    } catch (error) {
      if (!quiet) this.showToast(error.message, 'error');
      return false;
    }
  },

  async ensureCompanyAI() {
    if (!await this.refreshCompanyStatus()) return false;
    if (this.aiConfigured) return true;
    this.showSettings = true;
    this.showToast('公司 AI 服务尚未配置；管理员配置一次后即可使用，当前内容已保留', 'error');
    return false;
  },

  async refreshSession() {
    try {
      const response = await fetch('/api/share/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 401) { this.accountUser = null; this.showLogin = true; return; }
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || '无法连接账号服务');
      this.applySession(data);
    } catch (error) { this.authError = error.message; this.showLogin = true; }
  },

  async loginAccount() {
    if (this.authBusy) return;
    this.authBusy = true; this.authError = '';
    try {
      const response = await fetch('/api/share/auth/login', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.loginForm) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '登录失败');
      this.loginForm.password = '';
      await this.refreshSession();
      if (this.editorReady) await this.activateDraftAccount();
    } catch (error) { this.authError = error.message; }
    finally { this.authBusy = false; }
  },

  async logoutAccount() {
    if (this.editorReady && this.draftOwner && !await this.saveLocalDraft()) return;
    if (!confirm('当前工程已保存为此账号的本机草稿。确定退出登录？')) return;
    try {
      await this.accountJSON('/auth/logout', {});
      this.accountUser = null; this.csrf = ''; this.showLogin = true;
      this.showSettings = false; this.showAdmin = false; this.showPassword = false;
      this.shareDialogOpen = false; this.shareManageOpen = false; this.shareResult = null;
      if (this.clearEditorForAccount) await this.clearEditorForAccount();
    } catch (error) { this.showToast(error.message, 'error'); }
  },

  async changeOwnPassword() {
    this.authError = '';
    if (this.passwordForm.next !== this.passwordForm.confirm) { this.authError = '两次新密码输入不一致'; return; }
    this.authBusy = true;
    try {
      await this.accountJSON('/auth/password', { current_password: this.passwordForm.current, new_password: this.passwordForm.next });
      this.passwordForm = { current: '', next: '', confirm: '' };
      this.showPassword = false; this.accountUser = null; this.csrf = ''; this.showLogin = true;
      this.authError = '密码已修改，请使用新密码登录';
    } catch (error) { this.authError = error.message; }
    finally { this.authBusy = false; }
  },

  async openAdmin() {
    this.showAdmin = true; this.adminMessage = ''; this.companyAILoaded = false;
    this.availableAIModels = []; this.aiModelMessage = ''; this.aiConfigMessage = '';
    this.companyAI.key = '';
    try {
      const data = await this.accountJSON('/admin/ai');
      this.aiPresets = data.presets;
      this.companyAI = { ...data.ai, key: '' };
      this.companyAILoaded = true;
    } catch (error) { this.adminMessage = error.message; }
    await Promise.all([this.loadEmployees(), this.refreshOperations()]);
  },

  async refreshOperations() {
    if (this.operationsBusy || this.accountUser?.role !== 'admin') return;
    this.operationsBusy = true; this.operationsError = '';
    try { this.operations = await this.accountJSON('/admin/operations'); }
    catch (error) { this.operationsError = error.message; }
    finally { this.operationsBusy = false; }
  },

  operationLevel(level) { return ({normal:'正常',warning:'需关注',critical:'异常',recovered:'已恢复'})[level] || '待检查'; },
  operationTime(value) { return value ? new Date(value * 1000).toLocaleString('zh-CN', {hour12:false}) : '暂无记录'; },

  selectAIProvider() {
    const preset = this.aiPresets.find(item => item.provider === this.companyAI.provider);
    if (preset) this.companyAI = { ...preset, key: '' };
    this.availableAIModels = []; this.aiModelMessage = '';
    this.adminMessage = '';
  },

  async loadAIModels() {
    if (this.authBusy || !this.companyAILoaded) return;
    this.authBusy = true; this.availableAIModels = []; this.aiModelMessage = '正在读取服务商模型列表…';
    try {
      const data = await this.accountJSON('/admin/ai/models', this.companyAI);
      this.availableAIModels = data.models;
      this.aiModelMessage = '已获取 ' + data.models.length + ' 个模型。列表不代表均支持识图，选定后仍需验证。';
    } catch (error) { this.aiModelMessage = error.message; }
    finally { this.authBusy = false; }
  },

  selectModelReference(id) {
    if (!id) return;
    const tencentAliases = {'deepseek-flash':'deepseek/deepseek-flash','MiniMax-M3':'minimax-m3'};
    this.companyAI.model = this.companyAI.provider === 'tencent' ? (tencentAliases[id] || id) : id;
  },

  async loadEmployees() {
    try { this.employeeList = (await this.accountJSON('/admin/users')).items; }
    catch (error) { this.adminMessage = error.message; }
  },

  async createEmployee() {
    this.adminMessage = ''; this.authBusy = true;
    try {
      await this.accountJSON('/admin/users', this.employeeForm);
      this.employeeForm = { username: '', display_name: '', password: '', role: 'staff' };
      this.adminMessage = '员工账号已创建。将账号和初始密码交给本人，首次登录需修改密码。';
      await this.loadEmployees();
    } catch (error) { this.adminMessage = error.message; }
    finally { this.authBusy = false; }
  },

  editEmployee(user) {
    this.editingUser = user.id;
    this.editForm = { display_name: user.display_name, role: user.role, active: !!user.active, password: '' };
    this.adminMessage = '';
  },

  async saveEmployee() {
    this.authBusy = true;
    try {
      const payload = { ...this.editForm };
      if (!payload.password) delete payload.password;
      await this.accountJSON('/admin/users/' + this.editingUser, payload);
      this.editingUser = null; this.editForm = {};
      this.adminMessage = '账号已更新，该员工的旧登录已失效。';
      await this.loadEmployees();
    } catch (error) { this.adminMessage = error.message; }
    finally { this.authBusy = false; }
  },

  async loadAudit() {
    try { this.auditItems = (await this.accountJSON('/admin/audit')).items; }
    catch (error) { this.adminMessage = error.message; }
  },

  auditLabel(action) {
    return ({ login: '登录', logout: '退出', 'user.create': '创建账号', 'user.update': '更新账号', 'password.change': '修改密码', 'share.create': '创建分享', 'share.revoke': '撤回分享', 'share.restore': '恢复分享', 'settings.update': '更新公司设置' })[action] || '其他操作';
  },

  async saveCompanyAI() {
    if (this.authBusy || !this.companyAILoaded) return;
    this.authBusy = true; this.aiConfigMessage = '正在验证接口与图片识别能力，请稍候…';
    try {
      const saved = await this.accountJSON('/admin/ai', this.companyAI);
      this.companyAI = { ...saved, key: '' };
      await this.refreshSession();
      this.aiConfigMessage = '公司 AI 设置已保存，员工再次点击 AI 整理即可使用，无需重新登录。';
    } catch (error) { this.aiConfigMessage = error.message; }
    finally { this.companyAI.key = ''; this.authBusy = false; }
  },
};
