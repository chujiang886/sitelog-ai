#!/usr/bin/env python3
"""Phase 3.9.10 —— External Staging Qualification Package Generator（Task 23）。

确定性生成 ``.ai/staging/external_staging_qualification_package.json``：

- canonical payload + SHA-256；
- 相同事实 → semantic payload 稳定（哈希稳定）。

用法：``python scripts/generate_external_staging_qualification_package.py [--source-commit HASH] [--out PATH]``
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.external_staging_qualification import (
    ExternalStagingEnvironmentIdentity,
    QualificationPipeline,
)


def _default_source_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate External Staging Qualification Package")
    parser.add_argument("--source-commit", default=None,
                        help="evidence_source_commit：真正包含本阶段实现的 commit")
    parser.add_argument("--baseline-commit", default=None,
                        help="基线 commit（Phase 3.9.9 real-staging tip）")
    parser.add_argument("--generated-from-commit", default=None,
                        help="实际生成本包的 HEAD（R1 终态 HEAD）")
    parser.add_argument("--out", default=".ai/staging/external_staging_qualification_package.json")
    args = parser.parse_args(argv)

    commit = args.source_commit or _default_source_commit()
    baseline = args.baseline_commit or commit
    generated_from = args.generated_from_commit or commit
    identity = ExternalStagingEnvironmentIdentity()
    pipeline = QualificationPipeline(
        source_commit=commit,
        baseline_commit=baseline,
        package_generated_from_commit=generated_from,
        environment_identity=identity,
    )
    result = pipeline.run()
    package = result.package

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] 生成资格包：{out_path}")
    print(f"  source_commit={package['source_commit']}")
    print(f"  baseline_commit={package['baseline_commit']}")
    print(f"  evidence_source_commit={package['evidence_source_commit']}")
    print(f"  package_generated_from_commit={package['package_generated_from_commit']}")
    print(f"  gate.status={package['gate']['status']}")
    print(f"  package_hash={package['package_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
