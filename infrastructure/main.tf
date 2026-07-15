terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: use S3 backend for remote state
  # backend "s3" {
  #   bucket  = "my-terraform-state"
  #   key     = "beer-site/terraform.tfstate"
  #   region  = "ap-southeast-2"
  #   profile = "your-aws-profile"
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# CloudFront requires ACM certificates to be in us-east-1 regardless of
# where the bucket lives. This second provider alias handles that.
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile
}

# ─── Variables ───────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-2"
}

variable "aws_profile" {
  description = "Local AWS CLI profile to use"
  type        = string
  default     = "your-aws-profile"
}

variable "bucket_name" {
  description = "S3 bucket name for beer photo storage (must be globally unique)"
  type        = string
}

variable "cdn_domain" {
  description = "Subdomain for CloudFront CDN — serves photos and manifest"
  type        = string
  default     = "cdn.beer.example.com"
}

variable "allowed_origins" {
  description = "Origins allowed to access the bucket via CORS (your site domain, e.g. https://beer.example.com)"
  type        = list(string)
  default     = []
}

# ─── S3 Bucket ───────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "beer" {
  bucket = var.bucket_name

  tags = {
    Project = "beer-site"
  }
}

# Bucket is fully private — CloudFront OAC is the only way in
resource "aws_s3_bucket_public_access_block" "beer" {
  bucket = aws_s3_bucket.beer.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Disables object-level ACLs — bucket policy is the sole access control mechanism
resource "aws_s3_bucket_ownership_controls" "beer" {
  bucket = aws_s3_bucket.beer.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# CORS allows the browser (at beer.example.com) to fetch from cdn.beer.example.com
resource "aws_s3_bucket_cors_configuration" "beer" {
  bucket = aws_s3_bucket.beer.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# ─── CloudFront Origin Access Control ────────────────────────────────────────
#
# OAC grants CloudFront permission to read from the private S3 bucket using
# SigV4 request signing (the modern replacement for OAI).

resource "aws_cloudfront_origin_access_control" "beer" {
  name                              = "${var.bucket_name}-oac"
  description                       = "OAC for beer site S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ─── S3 Bucket Policy (allow CloudFront OAC only) ────────────────────────────

resource "aws_s3_bucket_policy" "beer_cloudfront_read" {
  bucket     = aws_s3_bucket.beer.id
  depends_on = [aws_s3_bucket_public_access_block.beer]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.beer.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.beer.arn
          }
        }
      }
    ]
  })
}

# ─── ACM Certificate ─────────────────────────────────────────────────────────
#
# Must live in us-east-1 — required by CloudFront regardless of bucket region.
# After the first apply, validate by adding the output CNAME at your registrar.
# Wait for status "Issued" in the ACM console (us-east-1) before the full apply.

resource "aws_acm_certificate" "beer" {
  provider          = aws.us_east_1
  domain_name       = var.cdn_domain
  validation_method = "DNS"

  tags = {
    Project = "beer-site"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ─── CloudFront Distribution ──────────────────────────────────────────────────
#
# Serves photos and manifest from S3 via cdn.beer.example.com.
# The Netlify site at beer.example.com fetches from here.

resource "aws_cloudfront_distribution" "beer" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "Beer site CDN — ${var.cdn_domain}"
  aliases         = [var.cdn_domain]

  origin {
    domain_name              = aws_s3_bucket.beer.bucket_regional_domain_name
    origin_id                = "s3-${var.bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.beer.id
  }

  # Default: cache photos aggressively (1 year, immutable)
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
    response_headers_policy_id = "60669652-455b-4ae9-85a4-c4c02393f86c" # Managed-SimpleCORS
  }

  # manifest.json: never cache so updates propagate immediately
  ordered_cache_behavior {
    path_pattern           = "manifest.json"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.bucket_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.beer.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Project = "beer-site"
  }
}

# ─── IAM User for CLI uploads ─────────────────────────────────────────────────

resource "aws_iam_user" "uploader" {
  name = "${var.bucket_name}-uploader"

  tags = {
    Project = "beer-site"
  }
}

resource "aws_iam_user_policy" "uploader" {
  name = "${var.bucket_name}-uploader-policy"
  user = aws_iam_user.uploader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.beer.arn,
          "${aws_s3_bucket.beer.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_access_key" "uploader" {
  user = aws_iam_user.uploader.name
}

# ─── Outputs ─────────────────────────────────────────────────────────────────

output "bucket_name" {
  value       = aws_s3_bucket.beer.bucket
  description = "S3 bucket name — set as S3_BUCKET in .env"
}

output "cloudfront_domain" {
  value       = aws_cloudfront_distribution.beer.domain_name
  description = "CloudFront domain — add as CNAME for cdn.beer.example.com at your registrar"
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.beer.id
  description = "CloudFront distribution ID"
}

output "acm_certificate_validation_options" {
  value       = aws_acm_certificate.beer.domain_validation_options
  description = "CNAME record to add at your registrar to validate the ACM certificate"
}

output "manifest_url" {
  value       = "https://${var.cdn_domain}/manifest.json"
  description = "Set this as BEER_MANIFEST_URL in Netlify environment variables"
}

output "uploader_access_key_id" {
  value       = aws_iam_access_key.uploader.id
  description = "AWS Access Key ID for CLI uploader — put in .env"
  sensitive   = true
}

output "uploader_secret_access_key" {
  value       = aws_iam_access_key.uploader.secret
  description = "AWS Secret Access Key for CLI uploader — put in .env"
  sensitive   = true
}
