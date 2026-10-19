variable "region" {
  description = "Region hosting all roster models + the analyst on Bedrock (us-west-2 has them all)"
  type        = string
  default     = "us-west-2"
}

variable "image_tag" {
  description = "Image tag for the first deploy (later deploys come from CI or scripts/deploy.sh)"
  type        = string
  default     = "bootstrap"
}

variable "bedrock_model_ids" {
  description = "Bedrock model IDs the API may invoke (keep in sync with backend/models.yaml)"
  type        = list(string)
  default = [
    "openai.gpt-oss-20b-1:0",
    "google.gemma-3-27b-it",
    "mistral.magistral-small-2509",
    "qwen.qwen3-32b-v1:0",
  ]
}

variable "admin_passcode_version" {
  description = "Bump to rotate the generated admin passcode"
  type        = number
  default     = 1
}

variable "enable_waf" {
  description = "AWS WAF on CloudFront: per-IP API rate limit + IP reputation list (~$7/month)"
  type        = bool
  default     = true
}

variable "analyst_enabled" {
  description = "Run the AI commentator/judge on Bedrock (otherwise template commentary)"
  type        = bool
  default     = true
}

variable "analyst_model_id" {
  description = "Bedrock model for the commentator/judge: a lab with no player at the table"
  type        = string
  default     = "deepseek.v3-v1:0"
}

variable "alert_email" {
  description = "Receives CloudWatch alarms and budget alerts (confirm the SNS email!)"
  type        = string
}

variable "monthly_budget_usd" {
  type    = number
  default = 60
}

variable "max_games_per_day" {
  type    = number
  default = 20
}

variable "task_cpu" {
  type    = number
  default = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "github_repo" {
  description = "owner/repo for the GitHub Actions deploy role (empty = no role)"
  type        = string
  default     = ""
}

variable "create_github_oidc_provider" {
  type    = bool
  default = true
}

variable "deletion_protection" {
  description = "Protect the DynamoDB table and ECR repo from `terraform destroy`"
  type        = bool
  default     = false
}
