terraform {
  required_version = ">= 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region              = "ap-northeast-2"
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = "meterengine"
      Component = "discussion-notifier"
      ManagedBy = "terraform"
    }
  }
}
