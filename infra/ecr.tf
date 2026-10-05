resource "aws_ecr_repository" "this" {
  for_each = toset(["frontend", "api", "worker"])

  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag always means the same image, so rollback is exact
  force_delete         = !var.deletion_protection

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 15 most recent images (enough rollback targets)"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 15
      }
      action = { type = "expire" }
    }]
  })
}
