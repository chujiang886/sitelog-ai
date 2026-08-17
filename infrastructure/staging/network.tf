# T7 网络/安全 — 独立 staging VPC/子网/安全组（provider-agnostic, 默认 tencentcloud）
# 红线：不与 production VPC peering/共享；数据子网无公网；default-deny 入站。
# Phase 3.9.14 修正：全部资源 count=0 占位骨架；跨文件/同文件引用改由变量注入
# （不再引用 count=0 资源属性），保证 `tofu validate` 通过且 `tofu plan`（默认变量）
# 产出 0 资源变更（real_apply_allowed=False, fail-closed）。

resource "tencentcloud_vpc" "staging" {
  count      = 0 # 占位：AI 不代开真实 VPC；真人于 Track B 取消 count 并注入 var.vpc_id 引用
  name       = "boip-external-staging-vpc"
  cidr_block = var.vpc_cidr
  tags       = local.staging_tags
}

resource "tencentcloud_subnet" "public" {
  count             = 0
  name              = "boip-staging-public"
  vpc_id            = var.vpc_id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 0)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_subnet" "private" {
  count             = 0
  name              = "boip-staging-private"
  vpc_id            = var.vpc_id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 1)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_subnet" "data" {
  count             = 0
  name              = "boip-staging-data"
  vpc_id            = var.vpc_id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 2)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_security_group" "staging" {
  count       = 0
  name        = "boip-staging-sg"
  description = "default-deny; 仅 ALB/Ingress 暴露 staging 子域"
  tags        = local.staging_tags
}

# 入站 default-deny 由安全组默认规则保证；显式放行仅 ALB/Ingress 端口（由 deployment_target.tf 关联）。
# AWS 映射: aws_vpc / aws_subnet / aws_security_group
# Alibaba 映射: alicloud_vpc / alicloud_vswitch / alicloud_security_group

output "staging_vpc_id" {
  value = var.vpc_id
}
output "staging_subnet_data_id" {
  value = var.data_subnet_id
}
