# Application secrets are generated here and injected into containers by ECS at
# start-up; they never appear in images, task definitions, or variables. They do
# appear in Terraform state, which is why state must be stored encrypted.
# The database password is separate: RDS manages it (see rds.tf).

resource "random_password" "api_token" {
  length  = 48
  special = false
}

resource "random_password" "session_secret" {
  length  = 64
  special = false
}

resource "random_password" "app_password" {
  length  = 24
  special = false
}

locals {
  app_secrets = {
    api-internal-token = random_password.api_token.result
    session-secret     = random_password.session_secret.result
    app-password       = random_password.app_password.result
  }
}

resource "aws_secretsmanager_secret" "app" {
  for_each                = local.app_secrets
  name                    = "${local.name}/${each.key}"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each      = local.app_secrets
  secret_id     = aws_secretsmanager_secret.app[each.key].id
  secret_string = each.value
}
