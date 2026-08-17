terraform {
  required_version = ">= 1.6.0"

  # 默认启用 tencentcloud（见 main.tf）。覆写 provider（aws / alibabacloud）时，
  # 在下方取消对应 required_providers 块注释并删除 tencentcloud 块即可；无需同时声明三者。
  required_providers {
    tencentcloud = {
      source  = "tencentcloudstack/tencentcloud"
      version = ">= 1.81.0"
    }
  }

  # ---- 备选 provider（provider-agnostic 说明，默认不启用，避免强制下载） ----
  # aws = {
  #   source  = "hashicorp/aws"
  #   version = ">= 5.0.0"
  # }
  # alibabacloud = {
  #   source  = "aliyun/alicloud"
  #   version = ">= 1.200.0"
  # }
}
