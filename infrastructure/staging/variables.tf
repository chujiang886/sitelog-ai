# Phase 3.9.12 External Staging — 变量定义（provider-agnostic）
# 来源：T3 Provider ADR、T5 BOM、T6 成本模型、T16 IaC 策略 ADR
# 红线：本文件绝不含真实密钥/Token/私钥；所有凭据经 secret_provider 以引用表达。

variable "cloud_provider" {
  description = "IaC 供给方；默认 tencentcloud（T3 ADR 首选）。可覆写 aws / alibabacloud。"
  type        = string
  default     = "tencentcloud"
  validation {
    condition     = contains(["tencentcloud", "aws", "alibabacloud"], var.cloud_provider)
    error_message = "cloud_provider 必须是 tencentcloud / aws / alibabacloud 之一。"
  }
}

variable "environment" {
  description = "环境标识，恒为 external_staging；禁止 production。"
  type        = string
  default     = "external_staging"
  validation {
    condition     = var.environment == "external_staging"
    error_message = "environment 必须为 external_staging，禁止 production。"
  }
}

variable "region" {
  description = "云区域（由真人按 Track B 真实输入覆写）。"
  type        = string
  default     = "ap-guangzhou"
}

variable "project_id" {
  description = "独立 staging 项目/账号 ID（与 production 隔离，Track B PENDING）。"
  type        = string
  default     = "PENDING_EXTERNAL_STAGING_RESOURCE"
}

variable "vpc_cidr" {
  description = "staging VPC CIDR（须与 production 不重叠，Track B 规划）。"
  type        = string
  default     = "10.20.0.0/16"
}

variable "cost_budget" {
  description = "月度成本预算上限（¥），供 StagingCostGuard(T31) 校验；默认档位 B 上限。"
  type        = number
  default     = 6000
}

variable "db_instance_class" {
  description = "数据库实例规格档位：A/B/C（见 T6 成本模型）。"
  type        = string
  default     = "B"
  validation {
    condition     = contains(["A", "B", "C"], var.db_instance_class)
    error_message = "db_instance_class 必须是 A / B / C。"
  }
}

variable "staging_subdomain" {
  description = "staging 专用子域（T14，Track B PENDING）。"
  type        = string
  default     = "staging.example.com"
}

variable "tags" {
  description = "统一资源标签；含 env=staging / phase=3.9.12，禁止 production 标签。"
  type        = map(string)
  default = {
    env     = "staging"
    phase   = "3.9.12"
    managed = "boip-external-staging"
  }
}

# ---- Phase 3.9.14 解耦变量：跨资源引用一律经变量注入，避免引用 count=0 资源属性 ----
# 红线：以下默认值均为 PENDING 占位；真实值由真人于 Track B 经 -var 或 tfvars 注入。
# AI 不代填真实 VPC/子网/桶名；count=0 骨架下 `tofu plan`（默认）产出 0 资源变更。

variable "vpc_id" {
  description = "Staging VPC ID（Track B PENDING；Phase 3.9.14 仅占位，AI 不代开真实 VPC）。"
  type        = string
  default     = "PENDING_EXTERNAL_STAGING_RESOURCE"
}

variable "private_subnet_id" {
  description = "Staging 私有子网 ID（Track B PENDING）。"
  type        = string
  default     = "PENDING_EXTERNAL_STAGING_RESOURCE"
}

variable "data_subnet_id" {
  description = "Staging 数据子网 ID（Track B PENDING）。"
  type        = string
  default     = "PENDING_EXTERNAL_STAGING_RESOURCE"
}

variable "bucket_name" {
  description = "Staging 对象存储桶名（Track B PENDING）。"
  type        = string
  default     = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
