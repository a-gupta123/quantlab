data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  name = "${var.project}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  migrate_tag = var.migrate_image_tag != "" ? var.migrate_image_tag : var.image_tag

  images = {
    frontend = "${aws_ecr_repository.this["frontend"].repository_url}:${var.image_tag}"
    api      = "${aws_ecr_repository.this["api"].repository_url}:${var.image_tag}"
    worker   = "${aws_ecr_repository.this["worker"].repository_url}:${var.image_tag}"
    migrate  = "${aws_ecr_repository.this["api"].repository_url}:${local.migrate_tag}"
  }
}

check "image_tag_set_when_running" {
  assert {
    condition     = !var.run_services || var.image_tag != ""
    error_message = "run_services is true but image_tag is empty; deploy with infra/scripts/deploy.sh."
  }
}
