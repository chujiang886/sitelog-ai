#!/usr/bin/env python3
"""静态扫描：生产安全红线（Phase 3.8.29 T5）。

本脚本是 CI 的**结构级门禁**，与测试互补：测试证明「当前实现是对的」，
扫描证明「以后也回不到错的写法」。测试可以被 skip、被改断言，而这里检查的是
危险写法**能否出现在源码里**——出现即失败，不看它在运行时会不会被触发。

七条规则，每条都对应一次真实事故或一条最高红线：

1. **凭据 Cookie 只能由统一出口种下**
   ``set_cookie`` / ``delete_cookie`` 仅允许出现在 ``app/core/auth_cookies.py``。
   任何路由自己种 cookie，都可能漏掉 ``httponly`` / ``secure`` / ``samesite``
   中的某一个——而漏掉哪一个都足以让 HttpOnly 方案归零。收敛到唯一出口后，
   Cookie 属性只有一处可改，审计也只需要看一个文件。

2. **治理凭据禁止落 JS 可读存储**
   页面/组件层禁止调用 ``writeGovernanceToken`` / ``readGovernanceToken`` /
   ``sessionTokenSource``，也禁止把 token 直接塞进 ``sessionStorage`` /
   ``localStorage``。3.8.28 正是这么做的，代价是"页面上任一处 XSS 即可窃取
   治理凭据"。这些函数保留给 bearer 模式（非浏览器客户端），不该回到页面里。

3. **CORS 通配符**
   ``allow_origins=["*"]`` 与 ``allow_credentials=True`` 并存，等于允许任意站点
   携带用户凭据发起请求。生产配置校验已在运行时拦截，这里再从源码层堵死。

4. **禁止关闭 TLS 校验 / 假验签**
   ``verify=False`` / ``verify_signature: False`` / ``check_hostname=False`` /
   ``_create_unverified_context``。身份链路一旦"验签但不验"，后面所有权限判定
   都建立在可伪造的凭据上。

5. **测试密钥字面量不得进入生产源码**
   ``test-jwt-secret-not-for-production`` 只允许出现在密钥黑名单定义处、测试与
   CI 配置里。出现在别处，意味着有人把它当成了可用默认值。

6. **最高红线：``engineering_enabled`` 必须为 false**
   这是六条最高红线的第一条。它只能由主理人在人类终端显式打开，任何提交把它
   置 true 都必须在 CI 阶段就被拦下。

7. **生产禁用身份提供方不得成为缺省值**
   ``static-dev`` 不得作为 ``IDENTITY_PROVIDER`` 的默认值写进配置类——它是
   开发逃生舱，缺省即等于"忘了配就自动有身份"。

用法（被 CI 与 local_ci.sh 调用）：
    python scripts/lint/check_production_security.py --root <PROJECT_ROOT>
退出码 0 = 通过；1 = 发现违规。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# 通用工具                                                                      #
# --------------------------------------------------------------------------- #

#: 一律跳过的目录（构建产物、依赖、缓存、虚拟环境）。
SKIP_DIR_PARTS: tuple[str, ...] = (
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
    ".next",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
)

_TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests|__tests__)/|(?:^|/)test_[^/]*\.py$|\.(?:test|spec)\.[jt]sx?$"
)


def _is_skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(f"/{part}/" in f"/{rel}" for part in SKIP_DIR_PARTS)


def _is_test(rel_posix: str) -> bool:
    return bool(_TEST_PATH_RE.search(rel_posix))


def _iter_files(root: Path, subdirs: tuple[str, ...], suffixes: tuple[str, ...]):
    """遍历指定子目录下的源码文件，产出 ``(相对路径, 绝对路径)``。"""

    for sub in subdirs:
        base = root / sub
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if _is_skipped(path, root):
                continue
            yield path.relative_to(root).as_posix(), path


@dataclass(frozen=True)
class Violation:
    rule: str
    rel_path: str
    line_no: int
    line: str
    hint: str

    def render(self) -> str:
        return (
            f"  [{self.rule}] {self.rel_path}:{self.line_no}\n"
            f"      {self.line.strip()[:160]}\n"
            f"      → {self.hint}"
        )


# --------------------------------------------------------------------------- #
# 规则 1：Cookie 只能由统一出口种下                                              #
# --------------------------------------------------------------------------- #

COOKIE_WRITE_RE = re.compile(r"\b(?:set_cookie|delete_cookie)\s*\(")
COOKIE_BLESSED = ("backend/app/core/auth_cookies.py",)


def rule_cookie_single_exit(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for rel, path in _iter_files(root, ("backend/app",), (".py",)):
        if rel in COOKIE_BLESSED:
            continue
        for i, line in enumerate(_lines(path), start=1):
            if COOKIE_WRITE_RE.search(line):
                out.append(
                    Violation(
                        "cookie-single-exit",
                        rel,
                        i,
                        line,
                        "Cookie 只能经 app.core.auth_cookies 的 set_auth_cookie / "
                        "set_csrf_cookie 等出口写入，避免漏掉 HttpOnly/Secure/SameSite。",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 规则 2：治理凭据禁止落 JS 可读存储                                             #
# --------------------------------------------------------------------------- #

TOKEN_STORE_CALL_RE = re.compile(
    r"\b(?:writeGovernanceToken|readGovernanceToken|sessionTokenSource)\s*\("
)
#: 同一行里既出现 web storage 又出现凭据词，视为把凭据写进可读存储。
STORAGE_TOKEN_RE = re.compile(
    r"(?:session|local)Storage[^\n]*"
    r"(?:access_token|accessToken|authToken|bearer|credential|凭据|token)",
    re.IGNORECASE,
)
#: 凭据存储实现本身（受控），以及仅做类型/常量声明的出口文件。
TOKEN_STORE_BLESSED = (
    "frontend/src/lib/identity/token-store.ts",
    "frontend/src/lib/identity/index.ts",
    "frontend/src/lib/identity/registry.ts",
    "frontend/src/lib/identity/providers/jwt.ts",
)


def rule_no_js_credential_storage(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for rel, path in _iter_files(root, ("frontend/src",), (".ts", ".tsx")):
        if rel in TOKEN_STORE_BLESSED or _is_test(rel):
            continue
        for i, line in enumerate(_lines(path), start=1):
            stripped = line.strip()
            # 注释里提一句不构成风险，但**调用**必须拦（注释另有规则 5 那类约束）。
            if stripped.startswith(("*", "//", "/*")):
                continue
            if TOKEN_STORE_CALL_RE.search(line):
                out.append(
                    Violation(
                        "no-js-credential-storage",
                        rel,
                        i,
                        line,
                        "浏览器侧凭据一律走 HttpOnly Cookie；token-store 的读写函数"
                        "仅供 bearer 模式（非浏览器客户端 / E2E），不得在页面层调用。",
                    )
                )
            elif STORAGE_TOKEN_RE.search(line):
                out.append(
                    Violation(
                        "no-js-credential-storage",
                        rel,
                        i,
                        line,
                        "禁止把凭据写入 sessionStorage/localStorage —— "
                        "任一处 XSS 即可读走治理凭据。",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 规则 3：CORS 通配符                                                            #
# --------------------------------------------------------------------------- #

CORS_WILDCARD_RE = re.compile(r"allow_origins\s*=\s*\[[^\]]*[\"']\*[\"']")


def rule_no_cors_wildcard(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for rel, path in _iter_files(root, ("backend/app",), (".py",)):
        for i, line in enumerate(_lines(path), start=1):
            if CORS_WILDCARD_RE.search(line):
                out.append(
                    Violation(
                        "no-cors-wildcard",
                        rel,
                        i,
                        line,
                        "本服务对跨域请求放行凭据 Cookie；allow_origins 含 '*' "
                        "等于允许任意站点携带用户凭据发起请求。",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 规则 4：禁止关闭 TLS 校验 / 假验签                                             #
# --------------------------------------------------------------------------- #

INSECURE_TLS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bverify\s*=\s*False\b"),
        "关闭 TLS 证书校验会让 JWKS / IdP 通信可被中间人替换。",
    ),
    (
        re.compile(r"verify_signature[\"']?\s*[:=]\s*False"),
        "关闭签名校验等于接受任意伪造凭据；OIDC 缺后端时必须 fail-closed 而非跳过验签。",
    ),
    (
        re.compile(r"check_hostname\s*=\s*False"),
        "关闭主机名校验会让证书校验形同虚设。",
    ),
    (
        re.compile(r"_create_unverified_context"),
        "禁止创建不校验证书的 SSL 上下文。",
    ),
)


def rule_no_insecure_tls(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for rel, path in _iter_files(root, ("backend/app", "agents"), (".py",)):
        if _is_test(rel):
            continue
        for i, line in enumerate(_lines(path), start=1):
            for pattern, hint in INSECURE_TLS_PATTERNS:
                if pattern.search(line):
                    out.append(
                        Violation("no-insecure-tls", rel, i, line, hint)
                    )
    return out


# --------------------------------------------------------------------------- #
# 规则 5：测试密钥字面量                                                          #
# --------------------------------------------------------------------------- #

TEST_SECRET_LITERAL = "test-jwt-secret-not-for-production"
TEST_SECRET_BLESSED = (
    # 黑名单定义处：正因为要拒绝它，才必须写出它。
    "backend/app/core/config.py",
)


def rule_no_test_secret_in_source(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for rel, path in _iter_files(
        root, ("backend/app", "agents", "frontend/src"), (".py", ".ts", ".tsx")
    ):
        if rel in TEST_SECRET_BLESSED or _is_test(rel):
            continue
        for i, line in enumerate(_lines(path), start=1):
            if TEST_SECRET_LITERAL in line:
                out.append(
                    Violation(
                        "no-test-secret",
                        rel,
                        i,
                        line,
                        "已知测试密钥不得出现在生产源码；它只能存在于黑名单定义、"
                        "测试与 CI 配置中。",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 规则 6：最高红线 engineering_enabled                                           #
# --------------------------------------------------------------------------- #

ENGINEERING_FLAG_RE = re.compile(
    r"^\s*engineering_enabled\s*:\s*(?P<value>\S+)", re.MULTILINE
)


def rule_engineering_flag_disabled(root: Path) -> list[Violation]:
    config = root / "agents" / "config.yaml"
    if not config.exists():
        return []
    out: list[Violation] = []
    for i, line in enumerate(_lines(config), start=1):
        match = ENGINEERING_FLAG_RE.match(line)
        if not match:
            continue
        value = match.group("value").strip().strip("\"'").lower()
        if value not in ("false", "no", "off", "0"):
            out.append(
                Violation(
                    "engineering-flag-must-be-false",
                    "agents/config.yaml",
                    i,
                    line,
                    "最高红线①：engineering_enabled 只能由主理人在人类终端显式开启，"
                    "任何提交都不得把它置真。",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# 规则 7：生产禁用身份提供方不得成为缺省值                                        #
# --------------------------------------------------------------------------- #

DEFAULT_STATIC_DEV_RE = re.compile(
    r"identity_provider\s*:[^=]*=\s*Field\(\s*default\s*=\s*[\"']static-dev[\"']"
)


def rule_no_static_dev_default(root: Path) -> list[Violation]:
    config = root / "backend" / "app" / "core" / "config.py"
    if not config.exists():
        return []
    text = "\n".join(_lines(config))
    if DEFAULT_STATIC_DEV_RE.search(text):
        return [
            Violation(
                "no-static-dev-default",
                "backend/app/core/config.py",
                0,
                "identity_provider default='static-dev'",
                "static-dev 是开发逃生舱；作为缺省值等于'忘了配就自动有身份'。",
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# 驱动                                                                          #
# --------------------------------------------------------------------------- #


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


RULES = (
    ("凭据 Cookie 统一出口", rule_cookie_single_exit),
    ("凭据不落 JS 可读存储", rule_no_js_credential_storage),
    ("CORS 无通配符", rule_no_cors_wildcard),
    ("TLS/验签不得关闭", rule_no_insecure_tls),
    ("测试密钥不进生产源码", rule_no_test_secret_in_source),
    ("engineering_enabled 保持 false", rule_engineering_flag_disabled),
    ("static-dev 不得为缺省身份", rule_no_static_dev_default),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="项目根目录")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    all_violations: list[Violation] = []
    print("生产安全红线扫描（Phase 3.8.29 T5）")
    for name, rule in RULES:
        found = rule(root)
        status = "FAIL" if found else "ok"
        print(f"  [{status:>4}] {name}（{len(found)} 处）")
        all_violations.extend(found)

    if not all_violations:
        print("生产安全红线扫描通过。")
        return 0

    print("\n发现生产安全红线违规：")
    for violation in all_violations:
        print(violation.render())
    print(
        f"\n共 {len(all_violations)} 处违规。这些是 fail-closed 门禁，"
        "必须修复后才能合并——不接受'先合并再改'。"
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())
