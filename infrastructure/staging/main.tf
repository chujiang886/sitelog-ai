# Phase 3.9.12 External Staging — Provider 配置（provider-agnostic, 默认 tencentcloud）
# 红线：绝不在此硬编码真实 access_key / secret_key / token。凭据经 provider 环境变量
# (TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY 等) 或 secret_provider 注入，由真人提供。

# ---- 默认 provider: tencentcloud ----
provider "tencentcloud" {
  # 真实凭据由真人通过环境变量注入；此处不声明 secret。
  # region 取自变量；project_id 仅作标签隔离参考，不写入生产项目。
  region = var.region
  # assume_role / 独立子账号可在 Track B 由真人补充，确保与 production 隔离。
}

# ---- 覆写 provider 时取消下列注释并删除上方 tencentcloud block ----
# provider "aws" {
#   region     = var.region
#   # access_key/secret_key 经环境变量 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY 注入
# }
# provider "alibabacloud" {
#   region = var.region
#   # access_key/secret_key 经环境变量 ALICLOUD_ACCESS_KEY / ALICLOUD_SECRET_KEY 注入
# }

# 统一标签定位（供各资源 .tf 引用）
locals {
  staging_tags = merge(var.tags, {
    provider = var.provider
  })
}
