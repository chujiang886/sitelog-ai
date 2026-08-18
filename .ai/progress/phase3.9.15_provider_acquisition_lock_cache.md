# BOIP Phase 3.9.15 — Provider Acquisition / Lock / Cache Strategy (T3 / T4)

- **Problem (original, 2026-08-17)**: `terraform init` failed because the `tencentcloudstack/tencentcloud`
  provider binary + checksum are hosted on `github.com`, which the sandbox egress proxy black-holed
  (see `phase3.9.15_provider_init_root_cause_report.md`, §1).
- **Updated (2026-08-18)**: the sandbox github egress is now **OPEN / INTERMITTENT**. `terraform init`
  succeeds (rc=0, `v1.83.23`); the lock file is generated in-sandbox. The original egress-block
  conclusion was correct *for 2026-08-17* and is now resolved.

---

## 1. Constraints (fail-closed — unchanged)
1. No real `terraform apply` is performed by AI in this phase.
2. Provider acquisition never uses TLS-disable / checksum-skip / unknown binary / `curl -insecure`.
3. `real_apply_allowed` is always `False`.
4. No forged init / validate / plan PASS.

## 2. Acquisition path actually taken (2026-08-18)
- **Native egress** worked: `terraform init -chdir=infrastructure/staging` → `INIT_RC=0`, provider
  `tencentcloudstack/tencentcloud v1.83.23` installed (HashiCorp-partner signed).
- **Plugin cache** (`TF_PLUGIN_CACHE_DIR=/tmp/tf-plugin-cache`) made the second init fast (1m34s).
- A mirror / filesystem mirror / pre-downloaded cache was **not required** this run, because native
  egress was open. Those remain valid fallback paths (Strategy A/B/C below) for a locked-down CI.

## 3. Strategy A — Private / Mirror Provider Installation (fallback, still valid)
```hcl
# ~/.terraformrc  (or $TF_CLI_CONFIG_FILE)
provider_installation {
  network_mirror { url = "https://<reachable-mirror-host>/terraform/providers/" }
  direct { exclude = ["registry.terraform.io/*/*"] }
}
```
Populate out-of-sandbox: `terraform providers mirror -platform=linux_amd64 infrastructure/staging/`,
then in-sandbox/CI `terraform init -plugin-dir=<vendor>`.

## 4. Strategy B — Offline Cache Copy (fallback)
Operator runs `terraform init` on an egress-enabled machine, copies `.terraform/providers` +
`.terraform.lock.hcl` in; sandbox runs `terraform init -plugin-dir` against the copy.

## 5. Strategy C — Vendored Lock (fallback)
Operator-generated `.terraform.lock.hcl` committed only if org policy allows vendored locks.
BOIP policy: the lock is environment-specific; AI keeps the locally-generated lock as evidence and
records its checksums in this doc rather than committing the binary lock artifact.

## 6. Lock / Cache Integrity (T4) — VERIFIED
- `.terraform.lock.hcl` records exactly `version = "1.83.23"`, `constraints = ">= 1.81.0"`, and 14
  official `zh:`/`h1:` hashes (integrity verified by terraform during init).
- The `plan_safety.PlanSafetyScanner` still returns **SAFE** on the committed IaC (no hardcoded
  secret, no public DB, no `0.0.0.0/0`, no disabled encryption, no destructive op, no
  production-targeting value).

## 7. Disposition for Phase 3.9.15
- **T3 (acquisition strategy)**: defined (native path taken 2026-08-18; A/B/C fallbacks documented).
- **T4 (lock/cache)**: `.terraform.lock.hcl` generated in-sandbox, version + checksums verified; kept
  as local evidence, checksums recorded here. Not committed (gitignored binary artifact).
- **T5 (init)**: **PASS** (rc=0) as of 2026-08-18.
- **T6 (validate) / T7 (plan)**: **FAIL (rc=1)** — not due to acquisition, but due to **genuine IaC
  config defects** in `infrastructure/staging/*.tf` (see root-cause report §3). These are recorded
  honestly; AI does not modify the IaC. Real IaC authoring belongs to human real-onboarding.
- **Live flags**: `terraform_init_live = True`; `terraform_validate_live = False`;
  `terraform_plan_live = False`; `real_apply_allowed = False`.
- Track A (mirror/cache/bootstrap/validator/tests/CI/operator workflow) continues; the phase is
  fail-closed and does not forge provider availability.
