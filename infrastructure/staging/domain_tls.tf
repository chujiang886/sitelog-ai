# T14 域名/证书 — 独立 staging 子域 + 证书（provider-agnostic, 默认 tencentcloud DNSPod + SSL）
# 红线：staging 证书 SAN 不含 production 域名；私钥经 secret_provider 引用，不存明文。

locals {
  domain_tls_plan = {
    subdomain  = var.staging_subdomain
    cert_san   = [var.staging_subdomain]
    auto_renew = true
    isolation  = "independent-cert-no-production-san"
  }
}

# DNS 记录 + 证书请求经控制台/CLI 配置；此处以计划描述，真实签发 Track B PENDING。
# AWS 映射: aws_route53_record + aws_acm_certificate
# Alibaba 映射: alicloud_dns_record + alicloud_ssl_certificates

output "domain_tls_plan" {
  value = local.domain_tls_plan
}
output "domain_tls_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
