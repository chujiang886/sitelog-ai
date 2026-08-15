terraform {
  required_version = ">= 1.6.0"

  required_providers {
    tencentcloud = {
      source  = "tencentcloudstack/tencentcloud"
      version = ">= 1.81.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    alibabacloud = {
      source  = "aliyun/alicloud"
      version = ">= 1.200.0"
    }
  }
}

# NOTE: 仅默认启用 tencentcloud（见 main.tf）。覆写 provider 时取消对应 required_providers 注释块。
