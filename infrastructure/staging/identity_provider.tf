# T10 身份提供方 — 独立 staging OIDC/SSO（provider-agnostic）
# 说明：IdP 多为 SaaS/自建（Authing/Keycloak/云 IdP），常经控制台/CLI 开通，
#       此处以 locals 计划 + output 描述，真实 tenant 由真人配置（Track B PENDING）。

locals {
  idp_plan = {
    tenant            = "boip-external-staging"
    protocol          = "OIDC"
    redirect_uris     = ["https://${var.staging_subdomain}/auth/callback"]
    client_secret_ref = "ext-staging-identity_provider" # 经 secret_provider 引用, 不存明文
    isolation         = "independent-from-production-tenant"
  }
}

# 若选用腾讯云/Authing/Keycloak SaaS，在 Track B 由真人于控制台创建并回填 client_id；
# 若选用 AWS Cognito，可改用 aws_cognito_user_pool / aws_cognito_identity_provider 资源。
# 若选用 Alibaba，可改用 alicloud_resource_manager 等。

output "idp_plan" {
  value = local.idp_plan
}
output "identity_provider_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
