# BOIP Phase 3.9.15 — Provider Init Root Cause Report (T2 / T5)

- **Scope**: Real `terraform init` / `validate` / `plan` against `infrastructure/staging/*.tf`
- **Disposition summary**:
  - **T5 `terraform init`**: **PASS (rc=0)** as of 2026-08-18 (provider acquired). On 2026-08-17 it FAILED due to a sandbox egress block.
  - **T6 `terraform validate`**: **FAIL (rc=1)** — genuine **IaC config defects** (not environment, not egress).
  - **T7 `terraform plan`**: **FAIL (rc=1)** — same IaC config defects.

---

## 1. Original finding (2026-08-17) — PROVIDER INIT ROOT CAUSE

### 1.1 Command (real, reproducible)
```bash
terraform -chdir=infrastructure/staging init -no-color
```

### 1.2 Result (2026-08-17)
❌ **FAIL (rc=1, reproducible)** — provider installation structurally impossible in-sandbox at that time.

### 1.3 Network probe (2026-08-17)
| Host | Role | Result |
|------|------|--------|
| `registry.terraform.io` | provider **metadata** (version query) | ✅ HTTP 200, 0.74s |
| `github.com` (provider **binary + checksum** host) | provider **artifact** download | ❌ HTTP 000 / `curl (56) CONNECT tunnel failed, response 502` |

```bash
$ curl -m 12 -o /dev/null -w "http=%{http_code} time=%{time_total}s" https://registry.terraform.io/
http=200 time=0.738595s

$ curl -m 20 -o /dev/null -w "http=%{http_code} time=%{time_total}s" \
    https://github.com/tencentcloudstack/terraform-provider-tencentcloud/releases/download/v1.83.23/terraform-provider-tencentcloud_1.83.23_SHA256SUMS
curl: (56) CONNECT tunnel failed, response 502
http=000 time=10.004067s
```

### 1.4 Terraform error (2026-08-17)
```
Error: Failed to install provider
Error while installing tencentcloudstack/tencentcloud v1.83.23: could not
query provider registry for registry.terraform.io/tencentcloudstack/tencentcloud:
failed to retrieve authentication checksums for provider: the request failed
after 2 attempts ... Get
"https://github.com/tencentcloudstack/terraform-provider-tencentcloud/releases/download/v1.83.23/terraform-provider-tencentcloud_1.83.23_SHA256SUMS":
net/http: request canceled while waiting for connection (Client.Timeout
exceeded while awaiting headers)
```

### 1.5 Formal classification (2026-08-17)
- **PROVIDER_REGISTRY_METADATA_REACHABLE**
- **PROVIDER_BINARY_EGRESS_BLOCKED**
- **SANDBOX_GITHUB_EGRESS_UNAVAILABLE**

=> Track B **environment limitation**, **not an IaC code/config defect**. The provider block uses
`region = var.region` with no hardcoded secret; `versions.tf` `required_providers` source/version
are correct. The init failure was purely the egress proxy black-holing github binary egress.

---

## 2. Updated observation (2026-08-18) — the environment limitation has CLEARED

The 2026-08-17 egress block was a real, reproducible Track B environment limitation *at that time*,
and its classification (not a code defect) **stands**. As of 2026-08-18 the sandbox github egress is
**OPEN / INTERMITTENT** — `terraform init` now succeeds and the provider binary is acquired.

### 2.1 Re-run evidence (real, reproducible)
| Timestamp (CST) | Command | Result |
|-----------------|---------|--------|
| 2026-08-18 17:00:13 | `terraform -chdir=infrastructure/staging init` | **INIT_RC=0** — "Installed tencentcloudstack/tencentcloud v1.83.23 (signed by a HashiCorp partner, key ID 84F69E1C1BECF459)" |
| 2026-08-18 17:00:13 | `curl github.com/.../v1.83.23_SHA256SUMS` | **HTTP 302** (redirect, reachable — NOT the 502 black-hole) |
| 2026-08-18 17:15:48 | `terraform init` (plugin-cache retry) | **INIT_RC=0** (1m34s, cache-assisted) |

### 2.2 Conclusion
- The init failure was **never an IaC code defect** — the 2026-08-17 classification is correct and
  permanent for that incident.
- The environment egress condition has since cleared; `terraform init` is now **live-successful**
  (`terraform_init_live = True`). The earlier "BLOCKED" verdict does **not** apply to the current
  environment and must not be forged/retained.

---

## 3. NEW finding (2026-08-18) — validate / plan surface genuine IaC CONFIG defects

With the provider now available, `terraform validate` and `terraform plan` **run but FAIL (rc=1)**
due to **IaC authoring defects** in `infrastructure/staging/*.tf` — these are **not environment,
not egress**:

| File:Line | Resource | Defect |
|-----------|----------|--------|
| `deployment_target.tf:9` | `tencentcloud_kubernetes_cluster.staging` | unsupported argument `subnet_ids` |
| `deployment_target.tf:14` | `tencentcloud_tcr_instance.staging` | missing required argument `name` |
| `deployment_target.tf:14` | `tencentcloud_tcr_instance.staging` | missing required argument `instance_type` |
| `deployment_target.tf:16` | `tencentcloud_tcr_instance.staging` | unsupported argument `instance_name` |
| `object_storage.tf:13` | `tencentcloud_cos_bucket_cors.staging` | invalid / unsupported resource type |
| `secret_provider.tf:5` | `tencentcloud_ssm.staging` | invalid / unsupported resource type |

### 3.1 Disposition (fail-closed — AI does NOT author/fix real IaC)
- These are **IaC authoring gaps** in the staging scaffolding. Per Phase 3.9.15 governance, real
  External Staging resources are onboarded by the **HUMAN** (with dual-key authorization); AI does
  not author or fix real infrastructure IaC.
- **AI does NOT modify `infrastructure/staging/*.tf`** to chase terraform validity. The defects are
  recorded honestly (exact errors above).
- `terraform_validate_live = False`, `terraform_plan_live = False` (they ran, but failed on config;
  **not** forged to PASS).
- `real_apply_allowed = False` always (governance; no `apply`).
- Resolution of these IaC config defects belongs to the **human real-onboarding** task, out of AI
  software-phase scope.

---

## 4. Provider lock (T4)
- `.terraform.lock.hcl` generated (gitignored locally; checksum evidence recorded here).
- provider: `registry.terraform.io/tencentcloudstack/tencentcloud`, version **1.83.23**,
  constraints `>= 1.81.0`.
- 14 official hashes recorded (integrity verified by terraform), e.g.
  `h1:eSrhYW2BzH+KZsOR3jVze4n8aYdiXTLn0xtfMSuo4Qc=` and
  `zh:07279cd487f11cf5f2255751e551b24abfdb62edf2104b55d5d8cf1ee5ae6ad9`.

---

## 5. Anti-fabrication note
No workaround that would fake a successful `init`/`validate`/`plan` was applied. Init success is
real (rc=0). Validate/plan failures are real (rc=1, exact errors in §3). No historical success is
substituted. All downstream gates remain fail-closed (`BLOCKED` / `PENDING_HUMAN_AUTHORIZATION`).
No `infrastructure/staging/*.tf` file was edited to "fix" any terraform error.
