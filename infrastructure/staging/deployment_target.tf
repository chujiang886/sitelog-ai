# T15 容器运行时 — 独立 staging 集群 + 镜像仓库（provider-agnostic, 默认 tencentcloud TKE + TCR）
# 红线：独立集群/命名空间，不与 production 共享；镜像 digest 经真实 build/push 后引用登记。
# Phase 3.9.14 修正：vpc/subnet 引用改由变量注入，count 保持 0（real_apply_allowed=False）。

resource "tencentcloud_kubernetes_cluster" "staging" {
  count           = 0 # 占位：AI 不代开真实集群；真人取消 count 后 apply
  cluster_name    = "boip-external-staging-tke"
  vpc_id          = var.vpc_id
  subnet_ids      = [var.private_subnet_id]
  cluster_version = "1.28.3"
  tags            = local.staging_tags
}

resource "tencentcloud_tcr_instance" "staging" {
  count         = 0 # 占位：AI 不代开真实仓库；真人取消 count 后 apply
  instance_name = "boipstagingtcr"
  tags          = local.staging_tags
}

# AWS 映射: aws_eks_cluster + aws_ecr_repository
# Alibaba 映射: alicloud_cs_managed_kubernetes + alicloud_cr_repo

output "deployment_target_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
