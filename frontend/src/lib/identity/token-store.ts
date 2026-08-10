/**
 * 浏览器侧凭据接入点（Phase 3.8.28 建立，3.8.29 改为 Cookie 优先）。
 *
 * ## 3.8.29 的变化：凭据不再由 JS 保管
 *
 * 3.8.28 把 token 存在 ``sessionStorage``，并把"存在 XSS 即可窃取治理凭据"
 * 登记为已知残余风险。本阶段兑现了那笔债：凭据改由后端以
 * **HttpOnly Cookie**（``boip_access_token``）签发，JS 根本读不到它，
 * 于是 XSS 也偷不走 —— 这是 sessionStorage 方案无论怎么写都达不到的。
 *
 * 代价是 Cookie 会被浏览器**自动附带**，因此必须配套 CSRF 防护：后端同时
 * 签发一条**非** HttpOnly 的 ``boip_csrf_token``，由本模块读出、经
 * ``X-CSRF-Token`` 头回传，后端比对一致才放行（双提交）。
 *
 * ## 于是本模块的职责变了
 *
 * - **不再保管凭据**（凭据在 HttpOnly Cookie 里，JS 无权触碰）；
 * - 只负责读出 CSRF 令牌，供请求层回填；
 * - 保留 sessionStorage 读写口子，仅供 **Bearer 模式**（非浏览器客户端、
 *   E2E 脚本、以及尚未迁移的调用点）使用，并已标注为不推荐。
 *
 * ## 本模块不做的事
 *
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
 * 默认 token 源：从 sessionStorage 读（**Bearer 模式专用**）。
 *
 * @deprecated 3.8.29 起浏览器走 Cookie 模式，凭据不经 JS。此函数仅保留给
 * 非浏览器客户端与 E2E 脚本；在页面里继续用它等于放弃 HttpOnly 的全部收益。
 */
export function sessionTokenSource(): string | null {
  return readGovernanceToken();
}

// --------------------------------------------------------------------------- //
// Cookie 模式：CSRF 双提交令牌                                                  //
// --------------------------------------------------------------------------- //

/** CSRF Cookie 名（与后端 ``settings.csrf_cookie_name`` 对齐）。 */
export const CSRF_COOKIE_NAME = "boip_csrf_token";

/** CSRF 请求头名（与后端 ``settings.csrf_header_name`` 对齐）。 */
export const CSRF_HEADER_NAME = "X-CSRF-Token";

/**
 * 从 ``document.cookie`` 读出 CSRF 令牌。
 *
 * 这条 Cookie **故意不是** HttpOnly —— 双提交机制要求 JS 能读到它并回填到
 * 请求头。它被读走本身不构成凭据泄露：单独持有一个随机串无法伪装身份，
 * 真正的凭据在同名不同条的 HttpOnly Cookie 里，JS 永远拿不到。
 */
export function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const raw = document.cookie || "";
  for (const part of raw.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === CSRF_COOKIE_NAME) {
      const value = decodeURIComponent(rest.join("="));
      return value.trim() ? value : null;
    }
  }
  return null;
}

/**
 * 构造状态变更请求所需的 CSRF 头。
 *
 * 读不到令牌时返回空对象而**不是**抛错：请求照发，由后端以 403 拒绝。
 * 让服务端做最终裁决，避免前端因自身状态误判而把合法请求提前拦掉 ——
 * 安全结论必须由后端给出，前端只负责把该带的东西带上。
 */
export function csrfHeaders(): Readonly<Record<string, string>> {
  const token = readCsrfToken();
  return token ? { [CSRF_HEADER_NAME]: token } : {};
}
