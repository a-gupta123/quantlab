output "app_url" {
  value = "https://${var.domain_name}"
}

output "alb_dns_name" {
  description = "Point domain_name at this (CNAME/alias) if route53_zone_id was not set."
  value       = aws_lb.this.dns_name
}

output "aws_region" {
  value = var.aws_region
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "deployed_image_tag" {
  description = "Image tag the services currently run (empty before the first deploy)."
  value       = var.run_services ? var.image_tag : ""
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "migrate_task_definition" {
  value = aws_ecs_task_definition.migrate.arn
}

output "migrate_network" {
  description = "Network settings migrate.sh passes to aws ecs run-task."
  value = {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.worker.id]
  }
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}

output "app_password_secret_arn" {
  description = "Read the login password with: aws secretsmanager get-secret-value --secret-id <arn>"
  value       = aws_secretsmanager_secret.app["app-password"].arn
}

output "log_groups" {
  value = { for k, g in aws_cloudwatch_log_group.this : k => g.name }
}
