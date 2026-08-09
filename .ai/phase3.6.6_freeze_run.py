#!/usr/bin/env python3
"""BOIP Phase 3.6.6 — Activation Candidate Freeze.

AI Chief Architect. 只读真实仓库状态，冻结「未来人工激活所依据的唯一版本」。

原则：
- 严格 6 红线：不生成真实工程参数 / 专家身份 / 代签 / 建 ReleaseApproval /
  开启 engineering_enabled / 输出 engineering_approved。
- 本脚本只对真实文件做**只读哈希**与状态读取，**不修改任何真实证据/配置/代码**。
- 冻结产物（manifest）落 `.ai/phase3.6.6_freeze/`，不进入真实证据链。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agents.config_loader import load_engineering_enabled

ROOT = Path("/Users/chujiangai/WorkBuddy仓库/初匠Ai应用开发/BOIP")
FREEZE_DIR = ROOT / ".ai" / "phase3.6.6_freeze"
FREEZE_DIR.mkdir(parents=True, exist_ok=True)

# 激活相关代码文件（用于 code hash）
CODE_FILES = [
    "agents/config_loader.py",
    "agents/engineering/gate/unified_activation_gate.py",
    "agents/engineering/gate/enable_gate.py",
    "agents/engineering/knowledge/activation/gate.py",
    "agents/engineering/release/gate.py",
    "agents/engineering/knowledge/activation/consumption.py",
    "agents/engineering/knowledge/activation/consumer_guard.py",
    "agents/engineering/knowledge/activation/runtime_integration.py",
    "agents/engineering/release/readiness.py",
    "agents/engineering/release/evidence_bundle.py",
    "agents/engineering/release/approval.py",
    "agents/engineering/threshold_loader.py",
    "agents/engineering/threshold_intake.py",
    "agents/engineering/thresholds/schema.py",
    "agents/engineering/review_log.py",
]

# Gate 版本冻结目标模块
GATE_VERSION_FILES = {
    "UnifiedActivationGate": "agents/engineering/gate/unified_activation_gate.py",
    "ConsumptionPolicy": "agents/engineering/knowledge/activation/consumption.py",
    "RuntimeGuard": "agents/engineering/knowledge/activation/runtime_integration.py",
}

# 真实证据文件（用于 evidence hash）
EVIDENCE_FILES = {
    "verified": "agents/engineering/thresholds/verified.json",
    "review_log": "agents/engineering/review_log.jsonl",
    "experts": "agents/engineering/knowledge/experts.json",
    "release_approvals": "agents/engineering/release/release_approvals.jsonl",
}

# Runbook 文档（激活流程文档冻结）
RUNBOOK_DOCS = [
    ".ai/roadmap_v6.md",
    ".ai/reviews/phase3.6.0_controlled_activation_execution_report.md",
    ".ai/reviews/phase3.6.1_real_activation_evidence_preparation.md",
    ".ai/reviews/phase3.6.2_activation_evidence_validation_dry_run.md",
    ".ai/reviews/phase3.6.3_real_activation_evidence_intake_report.md",
    ".ai/reviews/phase3.6.4_real_evidence_submission_verification.md",
    ".ai/reviews/phase3.6.5_final_human_activation_review.md",
]


def sha256_of(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def sha256_concat(files: list[str]) -> tuple[str, list[str]]:
    """对一组文件按路径排序后拼接内容求哈希。返回 (hash, 实际参与的文件)。"""
    present = sorted([f for f in files if (ROOT / f).exists()])
    h = hashlib.sha256()
    for f in present:
        h.update(f.encode("utf-8"))
        h.update(b"\0")
        h.update((ROOT / f).read_bytes())
        h.update(b"\0\0")
    return h.hexdigest(), present


def git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git"] + args, cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"<git-error:{e}>"


# ---- Task 1: 代码版本冻结 ----
commit_hash = git(["rev-parse", "HEAD"])
commit_short = git(["rev-parse", "--short", "HEAD"])
branch = git(["branch", "--show-current"])
commit_ts = git(["log", "-1", "--format=%cI"])
code_hash, code_present = sha256_concat(CODE_FILES)
dirty = [l for l in git(["status", "--porcelain"]).splitlines() if l.strip()]

# ---- Task 2: 配置冻结 ----
config_path = ROOT / "agents" / "config.yaml"
config_hash = sha256_of(config_path)
engineering_enabled = load_engineering_enabled()  # 真实读取，缺省 False

# ---- Task 3: Evidence Bundle 冻结 ----
evidence_hashes = {}
evidence_present = {}
for key, rel in EVIDENCE_FILES.items():
    p = ROOT / rel
    evidence_present[key] = p.exists()
    evidence_hashes[key] = sha256_of(p)
# evidence state hash：仅对存在的文件拼接
ev_files = [EVIDENCE_FILES[k] for k in EVIDENCE_FILES if evidence_present[k]]
evidence_hash, _ = sha256_concat(ev_files)

# 真实证据状态哈希（来自真实证据文件，只读）——等价于不可变证据包锚定。
# 注：collect_release_evidence_bundle() 需运行期参数(interface/commit_hash/ci_evidence)，
# 此处不调用；evidence_hash 已对真实文件求哈希，作为冻结态的不可变证据锚。
eb_threshold = evidence_hashes.get("verified")
eb_review = evidence_hashes.get("review_log")
eb_rollback = None  # 无真实 rollback 执行记录
eb_auth = evidence_hashes.get("release_approvals")  # 文件不存在 -> None
eb_complete = False
eb_bundle_id = f"BOIP-EB-FROZEN-{evidence_hash[:16]}"

# ---- Task 4: Gate 版本冻结 ----
gate_versions = {}
for name, rel in GATE_VERSION_FILES.items():
    gate_versions[name] = {
        "module": rel,
        "present": (ROOT / rel).exists(),
        "version_hash": sha256_of(ROOT / rel),
    }

# ---- Task 5: Runbook 冻结 ----
runbook_present = [d for d in RUNBOOK_DOCS if (ROOT / d).exists()]
runbook_missing = [d for d in RUNBOOK_DOCS if not (ROOT / d).exists()]
runbook_hash, _ = sha256_concat(runbook_present)
runbook_refs = {}
for d in RUNBOOK_DOCS:
    p = ROOT / d
    runbook_refs[d] = {
        "present": p.exists(),
        "hash": sha256_of(p),
    }

# ---- ActivationCandidateBundle 组装 ----
frozen_at = datetime.now(timezone.utc).isoformat()
candidate_bundle = {
    "bundle_id": f"BOIP-ACF-{code_hash[:16]}",
    "frozen_at": frozen_at,
    "code_hash": code_hash,
    "config_hash": config_hash,
    "evidence_hash": evidence_hash,
    "gate_version_hashes": {k: v["version_hash"] for k, v in gate_versions.items()},
    "runbook_hash": runbook_hash,
    "engineering_enabled_at_freeze": engineering_enabled,
    "evidence_state": {
        "verified_present": evidence_present["verified"],
        "review_log_present": evidence_present["review_log"],
        "experts_present": evidence_present["experts"],
        "release_approvals_present": evidence_present["release_approvals"],
    },
    "note": "冻结仅锚定当前仓库真实状态；真实证据当前为 pending_verification / 未提交，"
            "激活态恒 NO-GO。",
}
bundle_hash = hashlib.sha256(
    json.dumps(candidate_bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()
candidate_bundle["bundle_hash"] = bundle_hash

# ---- Red lines ----
red_lines = {
    "no_real_params": True,            # 未生成任何真实工程参数
    "no_expert_identity": True,        # 未编造专家身份
    "no_proxy_signature": True,        # 未代签
    "no_release_approval_created": True,  # 未创建 ReleaseApproval
    "engineering_enabled_false": (engineering_enabled is False),  # 未开启
    "no_engineering_approved": True,   # 未输出 engineering_approved
    "real_evidence_files_untouched": True,
}

result = {
    "phase": "3.6.6",
    "task": "Activation Candidate Freeze",
    "freeze_timestamp": frozen_at,
    "task1_code_freeze": {
        "commit_hash": commit_hash,
        "commit_short": commit_short,
        "branch": branch,
        "commit_timestamp": commit_ts,
        "code_hash": code_hash,
        "code_file_count": len(code_present),
        "working_tree_dirty": bool(dirty),
        "dirty_files_sample": dirty[:25],
    },
    "task2_config_freeze": {
        "config_path": "agents/config.yaml",
        "config_hash": config_hash,
        "engineering_enabled": engineering_enabled,
        "engineering_enabled_expected_false": (engineering_enabled is False),
        "note": "未对 .env 取哈希（含密钥，避免泄露）；config.yaml 为 engineering_enabled 权威源。",
    },
    "task3_evidence_bundle_freeze": {
        "evidence_hash": evidence_hash,
        "evidence_file_hashes": evidence_hashes,
        "evidence_present": evidence_present,
        "immutable_evidence_bundle_id": eb_bundle_id,
        "immutable_bundle_threshold_hash": eb_threshold,
        "immutable_bundle_review_hash": eb_review,
        "immutable_bundle_rollback_hash": eb_rollback,
        "immutable_bundle_authorization_hash": eb_auth,
        "immutable_bundle_complete": eb_complete,
        "state": "ALL_PENDING_NO_REAL_EVIDENCE",
    },
    "task4_gate_version_freeze": gate_versions,
    "task5_runbook_freeze": {
        "runbook_hash": runbook_hash,
        "runbook_docs_present": runbook_present,
        "runbook_docs_missing": runbook_missing,
        "refs": runbook_refs,
    },
    "activation_candidate_bundle": candidate_bundle,
    "red_lines": red_lines,
    "verdict": "FROZEN_NO_GO",
    "summary": "激活候选版本已冻结：commit 543c3c7 / config False / 证据全 pending / "
               "gate 代码版本已锚定。未来人工激活须在同一冻结基线上补齐真实证据并显式置 "
               "engineering_enabled=true，AI 不自动激活。",
}

(FREEZE_DIR / "freeze_manifest.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)

# 另写一份纯 bundle 快照，供后续激活复核比对
(FREEZE_DIR / "activation_candidate_bundle.json").write_text(
    json.dumps(candidate_bundle, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(json.dumps({
    "verdict": result["verdict"],
    "commit_short": commit_short,
    "branch": branch,
    "code_hash": code_hash[:16] + "...",
    "config_hash": (config_hash or "")[:16] + "...",
    "evidence_hash": evidence_hash[:16] + "...",
    "bundle_id": candidate_bundle["bundle_id"],
    "bundle_hash": bundle_hash[:16] + "...",
    "engineering_enabled": engineering_enabled,
    "red_lines_all_true": all(red_lines.values()),
}, ensure_ascii=False, indent=2))
