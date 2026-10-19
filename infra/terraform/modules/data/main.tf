# Stateful building blocks: container registry, game database, and secrets.

variable "name" { type = string }
variable "admin_passcode_version" {
  description = "Bump to rotate the admin passcode"
  type        = number
  default     = 1
}
variable "deletion_protection" {
  type    = bool
  default = false
}

# ---------------------------------------------------------------- ECR
resource "aws_ecr_repository" "api" {
  name                 = "${var.name}-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = !var.deletion_protection
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 15 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 15 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------- DynamoDB (single-table design)
resource "aws_dynamodb_table" "games" {
  name                        = "${var.name}-games"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  attribute {
    name = "gsi1pk"
    type = "S"
  }
  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    projection_type = "ALL"
    key_schema {
      attribute_name = "gsi1pk"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "gsi1sk"
      key_type       = "RANGE"
    }
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# ---------------------------------------------------------------- Secrets
# Ephemeral + write-only: the generated passcode exists only in Secrets Manager, never in
# Terraform state. Read it with the `admin_passcode_command` output.
ephemeral "random_password" "admin" {
  length  = 24
  special = false
}

resource "aws_secretsmanager_secret" "admin_passcode" {
  name                    = "${var.name}/admin-passcode"
  description             = "Passcode required to start live games"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin_passcode" {
  secret_id                = aws_secretsmanager_secret.admin_passcode.id
  secret_string_wo         = ephemeral.random_password.admin.result
  secret_string_wo_version = var.admin_passcode_version
}


output "ecr_repository_url" { value = aws_ecr_repository.api.repository_url }
output "ecr_repository_arn" { value = aws_ecr_repository.api.arn }
output "table_name" { value = aws_dynamodb_table.games.name }
output "table_arn" { value = aws_dynamodb_table.games.arn }
output "admin_passcode_secret_arn" { value = aws_secretsmanager_secret.admin_passcode.arn }
