resource "aws_ecs_cluster" "this" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "disabled" # "enabled" adds per-task CPU/memory metrics at extra CloudWatch cost
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE"]
}

# Service Connect gives the frontend a private DNS name "api" for the API,
# resolved and load-balanced by ECS inside the VPC.
resource "aws_service_discovery_http_namespace" "this" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["frontend", "api", "worker", "migrate"])
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

locals {
  secret_arn = { for k, s in aws_secretsmanager_secret.app : k => s.arn }

  backend_environment = [
    { name = "DB_HOST", value = aws_db_instance.this.address },
    { name = "DB_PORT", value = tostring(aws_db_instance.this.port) },
    { name = "DB_NAME", value = aws_db_instance.this.db_name },
    { name = "DB_USER", value = aws_db_instance.this.username },
    { name = "DB_SSLMODE", value = "require" },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_BUCKET", value = aws_s3_bucket.data.bucket },
    { name = "S3_PREFIX", value = local.s3_prefix },
    { name = "AWS_REGION", value = var.aws_region },
  ]

  backend_secrets = [
    { name = "DB_PASSWORD", valueFrom = "${aws_db_instance.this.master_user_secret[0].secret_arn}:password::" },
    { name = "API_INTERNAL_TOKEN", valueFrom = local.secret_arn["api-internal-token"] },
  ]

  log_config = { for k, g in aws_cloudwatch_log_group.this : k => {
    logDriver = "awslogs"
    options = {
      awslogs-group         = g.name
      awslogs-region        = var.aws_region
      awslogs-stream-prefix = k
    }
  } }

  runtime_platform = {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
}

# ----------------------------------------------------------------- frontend
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend.cpu
  memory                   = var.frontend.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["frontend"].arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name         = "frontend"
    image        = local.images.frontend
    essential    = true
    portMappings = [{ name = "web", containerPort = 3000, protocol = "tcp" }]
    environment = [
      { name = "API_BASE_URL", value = "http://api:8000" },
      { name = "COOKIE_SECURE", value = "true" },
    ]
    secrets = [
      { name = "API_INTERNAL_TOKEN", valueFrom = local.secret_arn["api-internal-token"] },
      { name = "SESSION_SECRET", valueFrom = local.secret_arn["session-secret"] },
      { name = "APP_PASSWORD", valueFrom = local.secret_arn["app-password"] },
    ]
    healthCheck = {
      command     = ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
    logConfiguration = local.log_config["frontend"]
  }])
}

resource "aws_ecs_service" "frontend" {
  name                              = "frontend"
  cluster                           = aws_ecs_cluster.this.id
  task_definition                   = aws_ecs_task_definition.frontend.arn
  desired_count                     = var.run_services ? var.frontend.count : 0
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 30
  propagate_tags                    = "SERVICE"
  wait_for_steady_state             = var.run_services

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.this.arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https, aws_ecs_service.api]
}

# ---------------------------------------------------------------------- api
resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api.cpu
  memory                   = var.api.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["api"].arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name         = "api"
    image        = local.images.api
    essential    = true
    portMappings = [{ name = "api", containerPort = 8000, protocol = "tcp", appProtocol = "http" }]
    environment  = local.backend_environment
    secrets      = local.backend_secrets
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = local.log_config["api"]
  }])
}

resource "aws_ecs_service" "api" {
  name                  = "api"
  cluster               = aws_ecs_cluster.this.id
  task_definition       = aws_ecs_task_definition.api.arn
  desired_count         = var.run_services ? var.api.count : 0
  launch_type           = "FARGATE"
  propagate_tags        = "SERVICE"
  wait_for_steady_state = var.run_services

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.this.arn
    service {
      port_name      = "api"
      discovery_name = "api"
      client_alias {
        dns_name = "api"
        port     = 8000
      }
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

# ------------------------------------------------------------------- worker
resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker.cpu
  memory                   = var.worker.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["worker"].arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = local.images.worker
    essential = true
    # The FinBERT weights are baked into the image (BAKE_MODEL=true in
    # build-push.sh), so the worker never downloads from Hugging Face at runtime.
    environment = concat(local.backend_environment, [
      { name = "SENTIMENT_LOCAL_FILES_ONLY", value = "true" },
      { name = "JOB_LEASE_SECONDS", value = "60" },
    ])
    secrets     = local.backend_secrets
    stopTimeout = 30
    healthCheck = {
      command     = ["CMD", "python", "-m", "quantlab.worker", "--healthcheck"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
    logConfiguration = local.log_config["worker"]
  }])
}

resource "aws_ecs_service" "worker" {
  name                  = "worker"
  cluster               = aws_ecs_cluster.this.id
  task_definition       = aws_ecs_task_definition.worker.arn
  desired_count         = var.run_services ? var.worker.count : 0
  launch_type           = "FARGATE"
  propagate_tags        = "SERVICE"
  wait_for_steady_state = var.run_services

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

# ------------------------------------------------------------------ migrate
# Not a service: infra/scripts/migrate.sh runs it once per deploy, before the
# services are updated, and fails the deploy if it exits non-zero.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["migrate"].arn

  runtime_platform {
    operating_system_family = local.runtime_platform.operating_system_family
    cpu_architecture        = local.runtime_platform.cpu_architecture
  }

  container_definitions = jsonencode([{
    name             = "migrate"
    image            = local.images.migrate
    essential        = true
    command          = ["quantlab", "migrate"]
    environment      = local.backend_environment
    secrets          = local.backend_secrets
    logConfiguration = local.log_config["migrate"]
  }])
}
