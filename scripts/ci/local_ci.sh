#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_PYTHON="python"
BACKEND_RUFF="ruff"
BACKEND_ALEMBIC="alembic"

if [[ -x "${PROJECT_ROOT}/backend/.venv/bin/python" ]]; then
  BACKEND_PYTHON="${PROJECT_ROOT}/backend/.venv/bin/python"
fi
if [[ -x "${PROJECT_ROOT}/backend/.venv/bin/ruff" ]]; then
  BACKEND_RUFF="${PROJECT_ROOT}/backend/.venv/bin/ruff"
fi
if [[ -x "${PROJECT_ROOT}/backend/.venv/bin/alembic" ]]; then
  BACKEND_ALEMBIC="${PROJECT_ROOT}/backend/.venv/bin/alembic"
fi

# 步骤总数：10。7~10 为静态安全门禁（不依赖服务启动，最先失败最省时间，
# 但放在最后是为了让"代码到底能不能跑"先有结论）。
printf '%s\n' '[1/10] Backend lint (Ruff)'
(
  cd "${PROJECT_ROOT}/backend"
  "${BACKEND_RUFF}" check app tests ../agents ../tests/agents ../tests/e2e
)

printf '%s\n' '[2/10] Backend pytest with coverage (minimum 60%)'
(
  cd "${PROJECT_ROOT}/backend"
  "${BACKEND_PYTHON}" -m pytest \
    --cov=app \
    --cov=agents \
    --cov-report=term-missing \
    --cov-report=xml:coverage.xml \
    --cov-fail-under=60
)

printf '%s\n' '[3/10] Frontend lint (ESLint)'
(
  cd "${PROJECT_ROOT}/frontend"
  npm run lint
)

printf '%s\n' '[4/10] Frontend Jest with coverage (minimum 50%)'
(
  cd "${PROJECT_ROOT}/frontend"
  npm test -- --runInBand --coverage
)

printf '%s\n' '[5/10] Alembic upgrade head and downgrade base'
(
  cd "${PROJECT_ROOT}/backend"
  TMP_DB="$(mktemp -t boip_alembic.XXXXXX.db)"
  trap 'rm -f "${TMP_DB}"' EXIT
  DATABASE_URL="sqlite+pysqlite:///${TMP_DB}" "${BACKEND_ALEMBIC}" upgrade head
  DATABASE_URL="sqlite+pysqlite:///${TMP_DB}" "${BACKEND_ALEMBIC}" downgrade base
)

printf '%s\n' '[6/10] Seed script'
(
  cd "${PROJECT_ROOT}/backend"
  "${BACKEND_PYTHON}" scripts/seed.py
)

printf '%s\n' '[7/10] Fabricated business-number scan'
"${BACKEND_PYTHON}" "${PROJECT_ROOT}/scripts/lint/check_fabrication.py" --root "${PROJECT_ROOT}"

printf '%s\n' '[8/10] Hard-coded business-configuration scan'
"${BACKEND_PYTHON}" "${PROJECT_ROOT}/scripts/lint/check_hardcoded.py" --root "${PROJECT_ROOT}"

printf '%s\n' '[9/10] Legacy identity-header trust-regression scan (Phase 3.8.28)'
"${BACKEND_PYTHON}" "${PROJECT_ROOT}/scripts/lint/check_legacy_identity_headers.py" --root "${PROJECT_ROOT}"

printf '%s\n' '[10/10] Production security red-line scan (Phase 3.8.29)'
"${BACKEND_PYTHON}" "${PROJECT_ROOT}/scripts/lint/check_production_security.py" --root "${PROJECT_ROOT}"

printf '%s\n' 'Local CI passed.'
