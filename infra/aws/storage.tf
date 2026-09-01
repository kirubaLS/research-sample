/**
 * Where student work rests.
 *
 * Both of these hold data about named children. Everything here is the consequence:
 * encryption on, public access off at the account boundary for this bucket, versioning so
 * a mistaken overwrite is recoverable, and deletion of the bucket blocked while it has
 * anything in it.
 */

resource "aws_s3_bucket" "pages" {
  bucket = var.pages_bucket_name
}

resource "aws_s3_bucket_public_access_block" "pages" {
  bucket                  = aws_s3_bucket.pages.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pages" {
  bucket = aws_s3_bucket.pages.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A page is overwritten only by a re-scan, which writes a new key. Versioning is here for
# the case this design does not cover: somebody with credentials making a mistake.
resource "aws_s3_bucket_versioning" "pages" {
  bucket = aws_s3_bucket.pages.id
  versioning_configuration { status = "Enabled" }
}

# The application deletes a superseded page. Versioning would otherwise keep it for ever,
# which is a retention decision nobody made.
resource "aws_s3_bucket_lifecycle_configuration" "pages" {
  bucket = aws_s3_bucket.pages.id
  rule {
    id     = "expire-superseded-pages"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = var.superseded_page_retention_days }
  }
}

# Pages are read from the app, never from a browser directly: the app checks which school
# is asking. A CORS rule would be the beginning of a public bucket.

# ── database ───────────────────────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "Postgres, reachable only from the API task"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_storage_gb
  max_allocated_storage = var.db_max_storage_gb
  storage_encrypted     = true

  db_name  = "yaadhum"
  username = var.db_username
  # Managed by RDS in Secrets Manager, so the password is never in state or in a variable.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period = var.db_backup_days
  # A pilot's worth of marks is small and irreplaceable: the scripts can be re-photographed
  # in principle, the teacher's marking cannot be done again.
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-final"

  auto_minor_version_upgrade   = true
  performance_insights_enabled = var.db_performance_insights
}
