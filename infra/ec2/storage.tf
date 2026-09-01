/**
 * One bucket, two prefixes: `schools/` for page images, `backups/` for database dumps.
 *
 * Together rather than apart because they share a lifecycle, a region and a blast radius,
 * and because a second bucket is a second thing to get the policy wrong on.
 */

resource "aws_s3_bucket" "data" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  # The instance can write a backup and cannot delete one. Retention is here instead, so
  # losing the instance cannot lose the history.
  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    filter { prefix = "backups/" }
    expiration { days = var.backup_retention_days }
  }

  rule {
    id     = "expire-superseded-pages"
    status = "Enabled"
    filter { prefix = "schools/" }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

# ── the application's own settings ─────────────────────────────────────────────────────
#
# One secret holding the whole environment, written once by hand. Terraform creates the
# container and never the value: a secret in a variable is a secret in state.

resource "aws_secretsmanager_secret" "app" {
  name = "${local.name}/app-env"
}

# ── the machine ────────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "api" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# Postgres lives here rather than on the root disk, so rebuilding the instance does not
# touch the data and the volume can be snapshotted on its own.
resource "aws_ebs_volume" "data" {
  availability_zone = aws_instance.main.availability_zone
  size              = var.data_volume_gb
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${local.name}-data" }

  lifecycle {
    # The marks are on this volume. A change that would destroy it is a mistake, always.
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.main.id
}

resource "aws_instance" "main" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  user_data                   = local.user_data
  user_data_replace_on_change = false # changing it must not rebuild the machine under a school

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only: v1 is how a request-forgery bug becomes credentials
  }

  tags = { Name = local.name }

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# A fixed address, so the DNS record does not change every time the instance restarts.
resource "aws_eip" "main" {
  instance = aws_instance.main.id
  domain   = "vpc"
  tags     = { Name = local.name }
}
