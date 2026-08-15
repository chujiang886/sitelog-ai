# T7 网络/安全 — 独立 staging VPC/子网/安全组（provider-agnostic, 默认 tencentcloud）
# 红线：不与 production VPC peering/共享；数据子网无公网；default-deny 入站。

resource "tencentcloud_vpc" "staging" {
  name       = "boip-external-staging-vpc"
  cidr_block = var.vpc_cidr
  tags       = local.staging_tags
}

resource "tencentcloud_subnet" "public" {
  name              = "boip-staging-public"
  vpc_id            = tencentcloud_vpc.staging.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 0)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_subnet" "private" {
  name              = "boip-staging-private"
  vpc_id            = tencentcloud_vpc.staging.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 1)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_subnet" "data" {
  name              = "boip-staging-data"
  vpc_id            = tencentcloud_vpc.staging.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 2)
  availability_zone = "${var.region}-1"
  tags              = local.staging_tags
}

resource "tencentcloud_security_group" "staging" {
  name        = "boip-staging-sg"
  description = "default-deny; 仅 ALB/Ingress 暴露 staging 子域"
  tags        = local.staging_tags
}

# 入站 default-deny 由安全组默认规则保证；显式放行仅 ALB/Ingress 端口（由 deployment_target.tf 关联）。
# AWS 映射: aws_vpc / aws_subnet / aws_security_group
# Alibaba 映射: alicloud_vpc / alicloud_vswitch / alicloud_security_group

output "staging_vpc_id" {
  value = tencentcloud_vpc.staging.id
}
output "staging_subnet_data_id" {
  value = tencentcloud_subnet.data.id
}
