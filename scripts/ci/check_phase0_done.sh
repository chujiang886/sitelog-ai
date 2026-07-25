#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"
PLAN_FILE="${PROJECT_ROOT}/../BOIP_AI_Documents/BOIP_PHASE0_INIT_PLAN.md"

required_files=(
  "README.md"
  "frontend/src/app/page.tsx"
  "backend/app/main.py"
  "backend/alembic/versions/d17f02429ce9_phase0_init_schema.py"
  "agents/base.py"
  "agents/config.yaml"
  "backend/conftest.py"
  "backend/tests/test_smoke.py"
  "frontend/src/__tests__/lib/api.test.ts"
  "tests/e2e/test_smoke_e2e.py"
  ".github/workflows/ci.yml"
  ".github/workflows/docs-check.yml"
  "docs/TESTING.md"
  "docs/PHASE0_DONE.md"
)

printf '%s\n' '[phase0] Verifying required artifacts'
for relative_path in "${required_files[@]}"; do
  if [[ ! -f "${PROJECT_ROOT}/${relative_path}" ]]; then
    printf 'Missing Phase 0 artifact: %s\n' "${relative_path}" >&2
    exit 1
  fi
done

if [[ ! -f "${PLAN_FILE}" ]]; then
  printf 'Missing Phase 0 source plan: %s\n' "${PLAN_FILE}" >&2
  exit 1
fi

printf '%s\n' '[phase0] Running the complete local CI gate'
bash "${PROJECT_ROOT}/scripts/ci/local_ci.sh"

printf '%s\n' '[phase0] Verifying completion records'
PROJECT_ROOT="${PROJECT_ROOT}" PLAN_FILE="${PLAN_FILE}" python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

project_root = Path(os.environ["PROJECT_ROOT"])
plan_file = Path(os.environ["PLAN_FILE"])
checks = {
    project_root / "docs" / "PHASE0_DONE.md": ("IS_PASS：YES", "T05"),
    project_root / "docs" / "PHASE0_LOG.md": ("## T05", "IS_PASS：YES"),
    project_root / "docs" / "CHANGELOG.md": ("T05",),
    plan_file: ("Phase 0 完成标记", "IS_PASS：YES"),
}
for path, markers in checks.items():
    content = path.read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise SystemExit(f"{path} is missing completion markers: {missing}")
print("Phase 0 completion records are consistent.")
PY

printf '%s\n' 'Phase 0 verification passed.'
