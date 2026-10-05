# Offline checks: `terraform test` with a mocked AWS provider. Nothing is
# created and no AWS credentials are needed. This checks the configuration's
# logic and security-relevant settings, not that AWS accepts every value.

mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address = "quantlab-demo.abc.us-east-1.rds.amazonaws.com"
      port    = 5432
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds!db-123"
        kms_key_id    = ""
        secret_status = "active"
      }]
    }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/quantlab-demo/x" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:quantlab-demo/x" }
  }
}

variables {
  domain_name     = "quantlab.example.com"
  certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/test"
}

run "first_apply_creates_infra_without_running_services" {
  command = apply
  variables {
    run_services = false
  }

  assert {
    condition     = aws_ecs_service.frontend.desired_count == 0 && aws_ecs_service.api.desired_count == 0 && aws_ecs_service.worker.desired_count == 0
    error_message = "Services must stay at zero before images exist."
  }
  assert {
    condition     = output.deployed_image_tag == ""
    error_message = "deployed_image_tag must be empty before the first deploy."
  }
}

run "deploy_runs_services_with_the_given_tag" {
  command = apply
  variables {
    image_tag         = "abc123"
    migrate_image_tag = "def456"
  }

  assert {
    condition     = aws_ecs_service.api.desired_count == 1 && aws_ecs_service.worker.desired_count == 1
    error_message = "Services should run when run_services is true."
  }
  assert {
    condition     = endswith(jsondecode(aws_ecs_task_definition.api.container_definitions)[0].image, ":abc123")
    error_message = "API must run image_tag."
  }
  assert {
    condition     = endswith(jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].image, ":def456")
    error_message = "Migration must run migrate_image_tag, independent of the services."
  }
  assert {
    condition     = output.deployed_image_tag == "abc123"
    error_message = "deployed_image_tag should report the running tag."
  }
}

run "nothing_private_is_public" {
  command = apply
  variables {
    image_tag = "abc123"
  }

  assert {
    condition     = aws_db_instance.this.publicly_accessible == false && aws_db_instance.this.storage_encrypted
    error_message = "RDS must be private and encrypted."
  }
  assert {
    condition     = aws_db_instance.this.manage_master_user_password == true
    error_message = "DB password must be RDS-managed, not in state."
  }
  assert {
    condition = alltrue([
      for s in [aws_ecs_service.frontend, aws_ecs_service.api, aws_ecs_service.worker] :
      s.network_configuration[0].assign_public_ip == false
    ])
    error_message = "Tasks must not get public IPs."
  }
  assert {
    condition     = alltrue([for k, v in aws_vpc_security_group_ingress_rule.db_from_tasks : v.from_port == 5432 && v.cidr_ipv4 == null])
    error_message = "Postgres must accept only security-group references, never CIDRs."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.api_from_frontend.referenced_security_group_id == aws_security_group.frontend.id
    error_message = "Only the frontend may reach the API."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.data.block_public_policy && aws_s3_bucket_public_access_block.data.restrict_public_buckets
    error_message = "Data bucket must block public access."
  }
  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.image_tag_mutability == "IMMUTABLE"])
    error_message = "Image tags must be immutable so rollbacks are exact."
  }
  assert {
    condition     = aws_lb_listener.https.protocol == "HTTPS" && aws_lb_listener.http_redirect.default_action[0].type == "redirect"
    error_message = "HTTP must redirect to HTTPS."
  }
}

run "secrets_are_injected_not_inlined" {
  command = apply
  variables {
    image_tag = "abc123"
  }

  assert {
    condition = alltrue([
      for td in [aws_ecs_task_definition.frontend, aws_ecs_task_definition.api, aws_ecs_task_definition.worker] :
      alltrue([for e in jsondecode(td.container_definitions)[0].environment :
      !contains(["API_INTERNAL_TOKEN", "SESSION_SECRET", "APP_PASSWORD", "DB_PASSWORD"], e.name)])
    ])
    error_message = "Secrets must come from Secrets Manager (secrets block), never plain environment."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.frontend.container_definitions)[0].environment[1].value == "true"
    error_message = "COOKIE_SECURE must be true behind HTTPS."
  }
}

run "rejects_non_acm_certificate" {
  command = plan
  variables {
    certificate_arn = "not-an-arn"
  }
  expect_failures = [var.certificate_arn]
}
