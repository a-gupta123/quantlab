data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

# ---------------------------------------------------------- execution role
# Used by the ECS agent (not your code) to pull images, write logs, and read
# the secrets it injects as environment variables.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [for s in aws_secretsmanager_secret.app : s.arn],
      [aws_db_instance.this.master_user_secret[0].secret_arn],
    )
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-injected-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --------------------------------------------------------------- task roles
# Credentials your application code receives (boto3 picks them up
# automatically). Only the API and worker touch S3, and only under the prefix.
locals {
  s3_prefix = "quantlab/"
}

data "aws_iam_policy_document" "data_access" {
  statement {
    sid       = "ObjectsUnderPrefix"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/${local.s3_prefix}*"]
  }
  statement {
    # Without ListBucket, a missing key returns 403 instead of 404.
    sid       = "ListPrefix"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.s3_prefix}*"]
    }
  }
}

resource "aws_iam_role" "task" {
  for_each           = toset(["frontend", "api", "worker", "migrate"])
  name               = "${local.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "data_access" {
  for_each = toset(["api", "worker"])
  name     = "s3-data-prefix"
  role     = aws_iam_role.task[each.key].id
  policy   = data.aws_iam_policy_document.data_access.json
}
