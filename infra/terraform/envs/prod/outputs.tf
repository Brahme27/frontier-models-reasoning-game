output "app_url" {
  description = "Public HTTPS URL"
  value       = "https://${module.edge.domain_name}"
}

output "admin_passcode_command" {
  description = "Read the generated admin passcode"
  value       = "aws secretsmanager get-secret-value --secret-id ${module.data.admin_passcode_secret_arn} --query SecretString --output text --region ${var.region}"
}

# --- values for scripts/deploy.sh and GitHub repository variables ---
output "ecr_repository_url" { value = module.data.ecr_repository_url }
output "ecs_cluster" { value = module.service.cluster_name }
output "ecs_service" { value = module.service.service_name }
output "ecs_task_family" { value = module.service.task_family }
output "site_bucket" { value = module.edge.site_bucket }
output "cloudfront_distribution_id" { value = module.edge.distribution_id }
output "github_deploy_role_arn" { value = module.ops.github_deploy_role_arn }
output "log_group" { value = module.service.log_group }
output "dynamodb_table" { value = module.data.table_name }

output "region" { value = var.region }
