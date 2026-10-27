# Dev environment. Written and validated in Phases 0-5; applied in Phase 6.
# EKS, RDS, MSK, and Cognito modules are added in Phase 6 (see docs/IMPLEMENTATION_PLAN.md).

terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }
  # Remote state with native S3 locking. Configure at init time:
  #   terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}

locals {
  name = "card-maven-${var.environment}"
  tags = {
    Project     = "card-maven"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "network" {
  source             = "../../modules/network"
  name               = local.name
  az_count           = 2
  single_nat_gateway = true
  tags               = local.tags
}

module "media_bucket" {
  source          = "../../modules/media_bucket"
  bucket_name     = "${local.name}-media-${data.aws_caller_identity.current.account_id}"
  allowed_origins = var.web_origins
  force_destroy   = true
  tags            = local.tags
}

module "ecr" {
  source       = "../../modules/ecr"
  repositories = ["card-maven-api", "card-maven-workers", "card-maven-web"]
  tags         = local.tags
}

data "aws_caller_identity" "current" {}
