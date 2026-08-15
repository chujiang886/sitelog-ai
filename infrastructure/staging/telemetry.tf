# T12 可观测 — 独立 staging 日志/指标 workspace（provider-agnostic, 默认 tencentcloud CLS）
# 红线：独立 workspace，不与 production 混用；保留期短于 production（T6）。

locals {
  telemetry_plan = {
    workspace      = "boip-external-staging"
    retention_days = 15 # staging 短保留
    sources        = ["app", "deployment_target"]
    isolation      = "independent-from-production"
  }
}

# 腾讯云 CLS 经控制台/CLI 开通 logset/topic；此处以计划描述，真实开通 Track B PENDING。
# AWS 映射: aws_cloudwatch_log_group / aws_prometheus_workspace
# Alibaba 映射: alicloud_log_project / alicloud_arms_prometheus

output "telemetry_plan" {
  value = local.telemetry_plan
}
output "telemetry_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
