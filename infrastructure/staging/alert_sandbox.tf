# T13 告警沙箱 — 独立 staging 通知组（provider-agnostic）
# 红线：通知组与 production 完全隔离；禁发 production on-call；误配 production 成员 → 校验失败。

locals {
  alert_sandbox_plan = {
    notification_group = "boip-external-staging-alerts" # 非生产 IM/邮箱
    routes             = ["staging-only"]
    silence_policy     = "staging-business-hours"
    forbid_prod_notify = true
  }
}

# 云监控告警 + 独立通知组经控制台/CLI 配置；此处以计划描述，真实开通 Track B PENDING。
# AWS 映射: aws_sns_topic (+ subscription 仅 staging 端点)
# Alibaba 映射: alicloud_actiontrail / alicloud_cms_alarm

output "alert_sandbox_plan" {
  value = local.alert_sandbox_plan
}
output "alert_sandbox_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
