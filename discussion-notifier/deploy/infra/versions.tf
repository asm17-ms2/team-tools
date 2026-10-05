terraform {
  required_version = ">= 1.16"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region              = "ap-northeast-2"
  allowed_account_ids = [var.aws_account_id]
}
