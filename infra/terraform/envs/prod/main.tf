terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Partial config: `terraform init -backend-config=backend.hcl` (see backend.hcl.example).
  backend "s3" {}
}

locals {
  tags = {
    Project     = "outsmart"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}

# CloudFront-scoped resources (WAF) must be created in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = local.tags
  }
}

locals {
  name = "outsmart"
  # Initial image; CI/CD rolls out new tags afterwards (the service ignores task-def drift).
  image = "${module.data.ecr_repository_url}:${var.image_tag}"
}

# Shared secret CloudFront adds to every origin request; the ALB rejects requests without it.
resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

module "network" {
  source = "../../modules/network"
  name   = local.name
}

module "data" {
  source                 = "../../modules/data"
  name                   = local.name
  admin_passcode_version = var.admin_passcode_version
  deletion_protection    = var.deletion_protection
}

module "service" {
  source                    = "../../modules/service"
  name                      = local.name
  region                    = var.region
  vpc_id                    = module.network.vpc_id
  task_subnet_ids           = module.network.public_subnet_ids
  alb_subnet_ids            = module.network.private_subnet_ids
  image                     = local.image
  cpu                       = var.task_cpu
  memory                    = var.task_memory
  table_name                = module.data.table_name
  table_arn                 = module.data.table_arn
  admin_passcode_secret_arn = module.data.admin_passcode_secret_arn
  bedrock_model_ids         = concat(var.bedrock_model_ids, var.analyst_enabled ? [var.analyst_model_id] : [])
  origin_verify_secret      = random_password.origin_verify.result
  env = {
    ANALYST_BACKEND      = var.analyst_enabled ? "bedrock" : "none"
    ANALYST_MODEL        = var.analyst_model_id
    MAX_GAMES_PER_DAY    = tostring(var.max_games_per_day)
    MAX_CONCURRENT_GAMES = "2"
    EVENT_PACING_MS      = "700"
  }
}

module "edge" {
  source = "../../modules/edge"
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
  name                 = local.name
  alb_arn              = module.service.alb_arn
  alb_dns_name         = module.service.alb_dns_name
  origin_verify_secret = random_password.origin_verify.result
  enable_waf           = var.enable_waf

  # the VPC origin needs the internet gateway to exist first
  depends_on = [module.network]
}

module "ops" {
  source                      = "../../modules/ops"
  name                        = local.name
  alert_email                 = var.alert_email
  monthly_budget_usd          = var.monthly_budget_usd
  alb_arn_suffix              = module.service.alb_arn_suffix
  target_group_arn_suffix     = module.service.target_group_arn_suffix
  cluster_name                = module.service.cluster_name
  service_name                = module.service.service_name
  service_arn                 = module.service.service_arn
  cluster_arn                 = module.service.cluster_arn
  github_repo                 = var.github_repo
  create_github_oidc_provider = var.create_github_oidc_provider
  ecr_repository_arn          = module.data.ecr_repository_arn
  site_bucket_arn             = module.edge.site_bucket_arn
  distribution_arn            = module.edge.distribution_arn
  pass_role_arns              = [module.service.execution_role_arn, module.service.task_role_arn]
}
