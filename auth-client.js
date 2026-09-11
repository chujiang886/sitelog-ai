// 员工登录与管理员设置。真实会话仅由服务器 HttpOnly Cookie 保存。
window.accountFeatures = {
  accountUser: null, csrf: '', authBusy: false, authError: '',
  showLogin: false, showPassword: false, showAdmin: false,
  aiConfigured: false, aiProvider: 'qwen', adminMessage: '',
  loginForm: { username: '', password: '' },
  passwordForm: { current: '', next: '', confirm: '' },
  employeeForm: { username: '', display_name: '', password: '', role: 'staff' },
  employeeList: [], editingUser: null, editForm: {}, auditItems: [],
  companyAI: { provider: 'qwen', key: '' },

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
    if (!response.ok || data.ok === false) throw new Error(data.error || '操作未完成，请重试');
    return data;
  },

  async refreshSession() {
    try {
      const response = await fetch('/api/share/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 401) { this.accountUser = null; this.showLogin = true; return; }
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || '无法连接账号服务');
      this.accountUser = data.user;
      this.csrf = data.csrf;
      this.aiConfigured = data.ai.configured;
      this.apiProvider = data.ai.provider;
      this.companyAI.provider = data.ai.provider;
      this.showLogin = false;
      this.showPassword = !!data.user.must_change_password;
      if (!this.archivePerson) this.archivePerson = data.user.display_name;
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
    } catch (error) { this.authError = error.message; }
    finally { this.authBusy = false; }
  },

  async logoutAccount() {
    if (!confirm('退出登录将清空本页未保存的工程内容，请先导出留底。确定退出？')) return;
    try {
      await this.accountJSON('/auth/logout', {});
      this.accountUser = null; this.csrf = ''; this.showLogin = true;
      this.showSettings = false; this.showAdmin = false; this.showPassword = false;
      this.shareDialogOpen = false; this.shareManageOpen = false; this.shareResult = null;
      this.images = []; this.arrivalImages = []; this.finishImages = []; this.sopImages = [];
      this.projectName = ''; this.siteLocation = ''; this.archivePerson = ''; this.pdfFilename = '';
      this.switchTemplate();
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
    this.showAdmin = true; this.adminMessage = '';
    await this.loadEmployees();
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
    this.authBusy = true;
    try {
      await this.accountJSON('/admin/ai', this.companyAI);
      this.companyAI.key = '';
      await this.refreshSession();
      this.adminMessage = '公司 AI 设置已保存，员工重新登录后即可使用。';
    } catch (error) { this.adminMessage = error.message; }
    finally { this.authBusy = false; }
  },
};
