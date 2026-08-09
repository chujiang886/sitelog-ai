/**
 * Phase 3.8.28 T3(c) —— 浏览器侧凭据存放点（唯一一处）。
 *
 * 【为什么用 sessionStorage 而不是 localStorage】
 * localStorage 跨标签页、跨会话长期存活，用户关掉浏览器再打开，治理凭据还在。
 * 治理动作的责任重量决定了它不该有这种"顺手就还登着"的持久性 ——
 * 关闭标签页即失效，是这里刻意接受的一点不便。
 *
 * 【为什么不用 httpOnly Cookie（更安全的那个选项）】
 * httpOnly Cookie 确实能挡住 XSS 读取凭据，但它要求后端签发时设置 Set-Cookie、
 * 且需要配套 CSRF 防护（Cookie 会被浏览器自动附带，而 Authorization 头不会）。
 * 那是一次涉及后端签发链路与跨域策略的改动，属于本阶段范围之外。
 * 现状必须写清楚而不是掩盖：**存在 XSS 即可窃取治理凭据**，
 * 这一条已作为已知残余风险登记进收口报告，不当作已解决。
 *
 * 【本模块不做的事】
 * 不解析 token、不判断过期、不推导身份。凭据是什么、能干什么，
 * 由后端 /governance/me 回答（见 backend-session 适配器）。
 */

/** 存储键。带命名空间前缀，避免与其他应用在同域下互相覆盖。 */
export const GOVERNANCE_TOKEN_KEY = "boip.governance.access_token";

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/**
 * 取当前环境的 sessionStorage；不可用（SSR / 隐私模式禁用）时返回 null。
 *
 * 返回 null 而不是抛错，是因为"没有存储"与"没有登录"在语义上等价，
 * 上层会走同一条 fail-closed 分支（要求登录），不需要区分。
 */
function storage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    // Safari 隐私模式等场景访问 sessionStorage 会抛 SecurityError。
    return null;
  }
}

/** 读取凭据；未登录返回 null。 */
export function readGovernanceToken(): string | null {
  const store = storage();
  if (!store) return null;
  const raw = store.getItem(GOVERNANCE_TOKEN_KEY);
  return raw && raw.trim() ? raw : null;
}

/** 写入凭据（登录成功后调用）。空值视为登出。 */
export function writeGovernanceToken(token: string | null): void {
  const store = storage();
  if (!store) return;
  if (!token || !token.trim()) {
    store.removeItem(GOVERNANCE_TOKEN_KEY);
    return;
  }
  store.setItem(GOVERNANCE_TOKEN_KEY, token.trim());
}

/** 清除凭据（登出 / 凭据被后端判定失效时调用）。 */
export function clearGovernanceToken(): void {
  writeGovernanceToken(null);
}

/**
 * 默认 token 源：从 sessionStorage 读。
 *
 * 这是 registry 装配 backend-session 适配器时的缺省实现；
 * 测试与 SSR 场景可注入自己的 TokenSource，无需碰全局状态。
 */
export function sessionTokenSource(): string | null {
  return readGovernanceToken();
}
