# T9 数据库 — 独立 staging 托管 PostgreSQL（provider-agnostic, 默认 tencentcloud CDB）
# 红线：独立实例，不与 production 共享；DB 密码经 secret_provider 引用，不存明文。
# Phase 3.9.14 修正：vpc/subnet 引用改由变量注入，count 保持 0（real_apply_allowed=False）。

locals {
  db_instance_class_map = {
    A = "cdb.c1.g1.xsmall" # 示意最小规格
    B = "cdb.c1.g2.large"
    C = "cdb.c1.g4.2xlarge"
  }
}

resource "tencentcloud_mysql_instance" "staging" {
  # 真实开通 Track B PENDING；此处声明占位参数，apply 由真人执行。
  count          = 0 # 占位：AI 不代开真实 DB；真人取消 count 后 apply
  instance_name  = "boip-external-staging-db"
  engine_version = "8.0"
  mem_size       = 4000
  volume_size    = 100
  cpu            = 2
  vpc_id         = var.vpc_id
  subnet_id      = var.data_subnet_id
  # 真实 root/应用账号密码经 secret_provider 注入（不在此声明明文）
  tags = local.staging_tags
  # 备份/保留由真人按 T9 计划配置
}

# AWS 映射: aws_db_instance (engine=postgres)
# Alibaba 映射: alicloud_db_instance

output "database_status" {
  value = "PENDING_EXTERNAL_STAGING_RESOURCE"
}
