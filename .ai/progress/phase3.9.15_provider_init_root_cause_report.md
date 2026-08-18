# BOIP Phase 3.9.15 — Provider Init Root Cause Report (T2 / T5)

- **Scope**: Real `terraform init` against `infrastructure/staging/*.tf`
- **Result**: ❌ **FAIL (rc=1, reproducible)** — provider installation structurally impossible in-sandbox
- **Classification**: **Track B environment limitation** (sandbox egress proxy black-holes `github.com` binary egress)
- **Not a code defect · Not a config defect**

---

## 1. Command Executed (real, reproducible)

```bash
terraform -chdir=infrastructure/staging init -no-color
```

## 2. Captured Output (fresh, timestamped 2026-08-17)

```
Initializing the backend...
Initializing provider plugins...
- Finding tencentcloudstack/tencentcloud versions matching ">= 1.81.0"...

Error: Failed to install provider

Error while installing tencentcloudstack/tencentcloud v1.83.23: could not
query provider registry for
registry.terraform.io/tencentcloudstack/tencentcloud: failed to retrieve
authentication checksums for provider: the request failed after 2 attempts,
please try again later: Get
"https://github.com/tencentcloudstack/terraform-provider-tencentcloud/releases/download/v1.83.23/terraform-provider-tencentcloud_1.83.23_SHA256SUMS":
net/http: request canceled while waiting for connection (Client.Timeout
exceeded while awaiting headers)
```

Exit code: `1` (captured via `${PIPESTATUS[0]}`).

## 3. Network Probe — Root-Cause Isolation

| Host | Role | Result |
|------|------|--------|
| `registry.terraform.io` | provider **metadata** (version query) | ✅ HTTP 200, 0.74s |
| `github.com` (provider **binary + checksum** host) | provider **artifact** download | ❌ HTTP 000 / `curl (56) CONNECT tunnel failed, response 502`, 10.0s timeout |

```bash
$ curl -m 12 -o /dev/null -w "http=%{http_code} time=%{time_total}s" https://registry.terraform.io/
http=200 time=0.738595s

$ curl -m 20 -o /dev/null -w "http=%{http_code} time=%{time_total}s" \
    https://github.com/tencentcloudstack/terraform-provider-tencentcloud/releases/download/v1.83.23/terraform-provider-tencentcloud_1.83.23_SHA256SUMS
curl: (56) CONNECT tunnel failed, response 502
http=000 time=10.004067s
```

## 4. Root Cause

The Terraform provider distribution model resolves provider **versions** from
`registry.terraform.io` (reachable here) but fetches the provider **checksum manifest
(`SHA256SUMS`) and zip binary** from `github.com` releases. The sandbox egress proxy
**allows `registry.terraform.io` metadata egress but black-holes `github.com` binary
egress** (HTTP 502 CONNECT tunnel failure). Therefore provider installation is
**structurally impossible inside this sandbox**.

- **Not a code defect**: `infrastructure/staging/*.tf` are syntactically valid; the provider
  block uses `region = var.region` with no hardcoded secret.
- **Not a config error**: `versions.tf` `required_providers` source
  (`tencentcloudstack/tencentcloud`) and version (`>= 1.81.0`) are correct.
- **Track B environment limitation**: the agent sandbox cannot reach the provider binary host.

## 5. Impact on Phase 3.9.15 Tasks

| Task | Disposition | Reason |
|------|-------------|--------|
| T5 Terraform Init | ❌ **FAIL** (recorded) | github.com egress black-holed |
| T6 Terraform Validate | ⛔ **BLOCKED** | cannot fetch provider schema without init |
| T7 Terraform Plan | ⛔ **BLOCKED / SKIP** | cannot plan without provider |
| T25 Runtime Deployment (terraform apply) | ⛔ **BLOCKED in-sandbox** | provider unavailable; real apply also forbidden by red lines |

## 6. Resolution Path (human / out-of-sandbox — NOT AI-executable here)

1. Run `terraform init` in an environment with GitHub egress (real operator workstation or a
   CI runner with internet), **or**
2. Pre-populate a provider cache / private mirror reachable from the sandbox:
   - `terraform providers mirror` on an egress-enabled machine, then
     `terraform init -plugin-dir=<mirror>`; **or**
   - `TF_CLI_CONFIG_FILE` with a `provider_installation` mirror block pointing to a reachable
     host (e.g., Tencent Cloud provider mirror), **or**
3. Vendor `.terraform/providers` from an egress-enabled machine and copy it in (offline init).

## 7. Anti-Fabrication Note

No workaround that would fake a successful `init` was applied. The phase records
`init=FAIL` honestly; all downstream provider-dependent gates are **fail-closed**
(`BLOCKED` / `PENDING_HUMAN_AUTHORIZATION`). No historical success result is substituted
for this phase's real, reproducible evidence.
