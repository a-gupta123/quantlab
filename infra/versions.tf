terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.67.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.9.1"
    }
  }

  # State contains generated secrets (API token, session secret, app password).
  # For anything beyond a throwaway trial, keep it in an encrypted, versioned S3
  # bucket you create once by hand; see infra/README.md ("Remote state").
  # backend "s3" {
  #   bucket       = "REPLACE-ME-terraform-state"
  #   key          = "quantlab/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
