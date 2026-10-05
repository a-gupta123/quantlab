variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "quantlab"
}

variable "environment" {
  description = "Deployment name, e.g. demo or prod."
  type        = string
  default     = "demo"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "certificate_arn" {
  description = "ARN of an issued ACM certificate (same region) for the HTTPS listener."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:acm:", var.certificate_arn))
    error_message = "certificate_arn must be an ACM certificate ARN."
  }
}

variable "domain_name" {
  description = "Hostname users visit, e.g. quantlab.example.com. Must match the certificate."
  type        = string
}

variable "route53_zone_id" {
  description = "Optional Route 53 hosted zone ID; when set, an alias record for domain_name is created."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Container image tag the frontend, API and worker services run (set by deploy.sh)."
  type        = string
  default     = ""
}

variable "migrate_image_tag" {
  description = "Image tag for the one-off migration task. Defaults to image_tag."
  type        = string
  default     = ""
}

variable "run_services" {
  description = "Run the ECS services. deploy.sh sets false only for the very first apply, before images exist."
  type        = bool
  default     = true
}

variable "cpu_architecture" {
  description = "ARM64 (Graviton, cheaper) or X86_64. Images must be built for the same platform."
  type        = string
  default     = "ARM64"

  validation {
    condition     = contains(["ARM64", "X86_64"], var.cpu_architecture)
    error_message = "cpu_architecture must be ARM64 or X86_64."
  }
}

variable "az_count" {
  description = "Availability zones to spread subnets over (ALB and RDS subnet groups need at least 2)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "single_nat_gateway" {
  description = "One NAT gateway for all AZs (cheaper, not AZ-redundant). false = one per AZ."
  type        = bool
  default     = true
}

variable "frontend" {
  description = "Fargate size and count for the Next.js service."
  type        = object({ cpu = number, memory = number, count = number })
  default     = { cpu = 256, memory = 512, count = 1 }
}

variable "api" {
  description = "Fargate size and count for the FastAPI service."
  type        = object({ cpu = number, memory = number, count = number })
  default     = { cpu = 512, memory = 1024, count = 1 }
}

variable "worker" {
  description = "Fargate size and count for the worker (FinBERT needs ~1.2 GB RSS)."
  type        = object({ cpu = number, memory = number, count = number })
  default     = { cpu = 1024, memory = 3072, count = 1 }
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "PostgreSQL major version; AWS selects the current minor and applies minor upgrades."
  type        = string
  default     = "17"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  description = "Protect the database (and keep bucket/ECR contents) from terraform destroy. Set false only to tear down."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "secret_recovery_window_days" {
  description = "Days a deleted secret can be restored (0 deletes immediately, useful for trial teardown)."
  type        = number
  default     = 7
}
