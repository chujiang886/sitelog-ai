# T8 密钥后端 — 独立 staging 密钥库（provider-agnostic, 默认 tencentcloud SSM）
# 红线：本文件绝不含密钥值；仅声明密钥引用占位，真实值由真人经环境变量/secret_provider 注入。

# 密钥库实例（占位，真实开通 Track B PENDING）
resource "tencentcloud_ssm" "staging" {
  # 腾讯云 SSM 通过 API/控制台开通；此处声明占位，不写入任何 secret 值。
  # 真实 secret 通过 tencentcloud_ssm_secret + tencentcloud_ssm_secret_version 由真人注入。
  count = 0 # 占位：避免 AI 代开真实密钥；真实开通由真人取消 count 并注入引用
  name  = "boip-external-staging-ssm"
  tags  = local.staging_tags
}

# AWS 映射: aws_secretsmanager_secret (+ version 仅引用, 值经 secret_provider 注入)
# Alibaba 映射: alicloud_kms_key + alicloud_ram_secret

locals {
  # 所有凭据以 CredentialReference 表达（仅引用/provider/id），不存明文。
  secret_reference_policy = "least-privilege; staging-only; no production access"
}

output "secret_provider_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
