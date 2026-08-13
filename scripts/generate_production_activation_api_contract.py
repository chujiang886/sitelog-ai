"""Generate the deterministic production-activation API contract snapshot (Phase 3.9.6).

Parses ``backend/app/api/governance_activation.py`` with the ``ast`` module (no app import, so it
runs in CI without a backend runtime) and emits ``.ai/baselines/production_activation_api_contract.json``.

The contract is the SSOT for the Layer A + Layer B control-plane surface. CI runs this generator and
does ``git diff --exit-code`` on the output: if anyone adds/removes a route, changes a method, or
changes a required permission, the generated contract diverges from the committed one and the gate
fails — forcing an explicit, reviewed reconciliation (closing the "API 8→? routes" drift).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER_FILE = ROOT / "backend" / "app" / "api" / "governance_activation.py"

# Layer B 路径（与 governance_activation.py 的文档注释一致）。
_LAYER_B_PATHS = {
    "/governance/activation/intake-summary",
    "/governance/activation/decision-ledger",
    "/governance/activation/evidence-list",
    "/governance/activation/evidence",
    "/governance/activation/evidence-decision",
    "/governance/activation/review-package",
    "/governance/activation/final-decision",
}

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def _extract_route(dec: ast.AST) -> tuple[str | None, str | None]:
    """从装饰器 ``@router.<method>("<path>")`` 提取 (method, path)。"""

    if not isinstance(dec, ast.Call):
        return None, None
    func = dec.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "router"):
        return None, None
    if func.attr not in _HTTP_METHODS:
        return None, None
    if not dec.args or not isinstance(dec.args[0], ast.Constant):
        return None, None
    return func.attr.upper(), dec.args[0].value


def _arg_defaults(node: ast.FunctionDef) -> dict[str, ast.AST | None]:
    """Python AST 把默认值存在 ``node.args.defaults``（与 args 尾部对齐），arg 节点本身不带
    default。这里重建 参数名→默认值 映射（含 kwonlyargs / kw_defaults）。"""

    out: dict[str, ast.AST | None] = {}
    args = node.args.args
    defaults = list(node.args.defaults)
    padded = [None] * (len(args) - len(defaults)) + defaults
    for a, d in zip(args, padded):
        out[a.arg] = d
    for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults):
        out[a.arg] = d
    return out


def _extract_permission(node: ast.FunctionDef) -> str | None:
    """从函数参数默认值 ``Depends(require_governance_permission(GovernancePermission.X))`` 提取 X。

    ``require_governance_permission`` 可能是直接导入的 Name，也可能是 ``module.attr`` 形式，
    两者都兼容。
    """

    for default in _arg_defaults(node).values():
        if default is None or not isinstance(default, ast.Call):
            continue
        if not (isinstance(default.func, ast.Name) and default.func.id == "Depends"):
            continue
        if not default.args:
            continue
        inner = default.args[0]
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        is_req = (isinstance(func, ast.Name) and func.id == "require_governance_permission") or (
            isinstance(func, ast.Attribute) and func.attr == "require_governance_permission"
        )
        if not is_req:
            continue
        if inner.args and isinstance(inner.args[0], ast.Attribute):
            return inner.args[0].attr  # e.g. RELEASE_READ
    return None


def _extract_router_prefix(tree: ast.Module) -> str:
    """从 ``router = APIRouter(prefix="...", ...)`` 提取路由前缀。"""

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == "router" and isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return str(kw.value.value)
    return ""


def _join_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if prefix.endswith("/"):
        prefix = prefix[:-1]
    if not path.startswith("/"):
        path = "/" + path
    return prefix + path


def main() -> int:
    if not ROUTER_FILE.exists():
        raise SystemExit(f"[FAIL] router not found: {ROUTER_FILE}")
    src = ROUTER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    prefix = _extract_router_prefix(tree)

    routes: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        method = path = None
        for dec in node.decorator_list:
            m, p = _extract_route(dec)
            if m and p:
                method, path = m, p
                break
        if not (method and path):
            continue
        full_path = _join_path(prefix, path)
        perm = _extract_permission(node)
        layer = "B" if full_path in _LAYER_B_PATHS else "A"
        audit = "append-only AuditService" if method != "GET" else "read-only"
        routes.append(
            {
                "method": method,
                "path": full_path,
                "handler": node.name,
                "layer": layer,
                "actor_kind": "user",  # 所有端点强制真实 USER（Bearer 即真实 USER，AI/SYSTEM 403）
                "permission": perm,
                "csrf_protected": True,  # 路由级 dependencies=[Depends(csrf_protect)]
                "audit": audit,
            }
        )

    routes.sort(key=lambda r: (r["path"], r["method"]))

    # fail-closed：禁止出现放行端点。
    for r in routes:
        if r["path"].endswith("/activate") or r["path"].endswith("/deploy-production"):
            raise SystemExit(f"[FAIL] forbidden endpoint present: {r['path']}")

    contract = {
        "schema_version": "1.0.0",
        "artifact": "production_activation_api_contract",
        "rc_id": "RC-3.9.6",
        "generated_from": "backend/app/api/governance_activation.py",
        "route_count": len(routes),
        "layers": {
            "A": sorted({r["path"] for r in routes if r["layer"] == "A"}),
            "B": sorted({r["path"] for r in routes if r["layer"] == "B"}),
        },
        "forbidden_endpoints": ["/activate", "/deploy-production", "/go", "engineering_approved 输出"],
        "routes": routes,
        "note": (
            "本契约是 Layer A（客观就绪）+ Layer B（人工证据受理与裁决登记）控制面的唯一事实源；"
            "任何路由增删/方法/权限变更都必须同步本文件并经 CI 漂移检测"
        ),
    }

    out_path = ROOT / ".ai" / "baselines" / "production_activation_api_contract.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[ok] wrote {out_path} (route_count={contract['route_count']}, "
        f"layerA={len(contract['layers']['A'])}, layerB={len(contract['layers']['B'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
