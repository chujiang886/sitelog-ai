/**
 * Phase 3.8.27 T3 —— 身份层错误类型（全部 fail-closed）。
 *
 * 设计原则：身份层**只会抛错，不会兜底**。
 * 任何"取不到身份就用默认责任人"的写法都是治理事故，本层不提供这种可能性。
 */

/** 身份层错误基类，便于调用方一次性捕获。 */
export class IdentityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IdentityError";
    // 兼容 ES5 target 下的 instanceof（Next 默认 target ES2017，此处仍保守处理）
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 适配器未配置（缺 env / 缺网关）。禁止退化为默认身份。 */
export class IdentityProviderNotConfiguredError extends IdentityError {
  constructor(providerId: string, hint: string) {
    super(`身份适配器「${providerId}」未完成配置：${hint}`);
    this.name = "IdentityProviderNotConfiguredError";
  }
}

/** 未登录 / 凭证缺失 / 凭证过期。 */
export class IdentityUnauthenticatedError extends IdentityError {
  constructor(reason: string) {
    super(`未取得有效的责任人身份：${reason}`);
    this.name = "IdentityUnauthenticatedError";
  }
}

/**
 * 主体不是真人（红线⑥）。
 *
 * 对应后端 ``require_human_actor(AuditActorKind.USER)``：
 * agent / system / service 一律不得进入治理动作路径。
 */
export class IdentityNotHumanError extends IdentityError {
  constructor(actorKind: string) {
    super(
      `治理动作仅对真实责任人（USER）开放，当前主体类型为「${actorKind}」；` +
        `AI 与系统主体不得代替人工承担治理责任。`
    );
    this.name = "IdentityNotHumanError";
  }
}

/** 权限不足（RBAC）。 */
export class IdentityPermissionDeniedError extends IdentityError {
  constructor(actorId: string, permission: string) {
    super(`责任人「${actorId}」缺少权限「${permission}」。`);
    this.name = "IdentityPermissionDeniedError";
  }
}

/**
 * 适配器返回了越过红线的权限声明（红线②/③）。
 *
 * 例如某个 JWT 里塞了 "governance:review:auto_approve"——
 * 这类声明一律视为攻击/配置事故，直接拒绝整个身份，而不是过滤掉后放行。
 */
export class IdentityRedLineViolationError extends IdentityError {
  constructor(detail: string) {
    super(`身份声明触碰治理红线，已整体拒绝：${detail}`);
    this.name = "IdentityRedLineViolationError";
  }
}

/** static-dev 适配器被用于生产环境。 */
export class IdentityInsecureEnvironmentError extends IdentityError {
  constructor(providerId: string) {
    super(
      `身份适配器「${providerId}」仅允许在开发/演示环境使用，` +
        `生产环境必须配置真实鉴权（JWT / SSO / 可信网关）。`
    );
    this.name = "IdentityInsecureEnvironmentError";
  }
}
