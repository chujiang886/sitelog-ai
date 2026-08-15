# T11 对象存储 — 独立 staging 桶（provider-agnostic, 默认 tencentcloud COS）
# 红线：独立桶，不与 production 共享；CORS 仅 staging 子域；公共读默认关闭。

resource "tencentcloud_cos_bucket" "staging" {
  count    = 0 # 占位：AI 不代开真实桶；真人取消 count 后 apply
  bucket   = "boip-external-staging-${var.project_id}"
  acl      = "private"
  tags     = local.staging_tags
}

# CORS 仅放行 staging 子域
resource "tencentcloud_cos_bucket_cors" "staging" {
  count  = 0
  bucket = tencentcloud_cos_bucket.staging[0].bucket
  rules {
    allowed_origins    = ["https://${var.staging_subdomain}"]
    allowed_methods    = ["GET", "PUT", "POST"]
    allowed_headers    = ["*"]
    max_age_seconds    = 300
  }
}

# AWS 映射: aws_s3_bucket (+ aws_s3_bucket_cors_configuration)
# Alibaba 映射: alicloud_oss_bucket

output "object_storage_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
