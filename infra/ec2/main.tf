/**
 * Yaadhum on one machine, in ap-south-1.
 *
 * For one school this is the honest shape: a single instance running the same image
 * production runs, with Postgres beside it and page images in S3. It costs roughly a
 * quarter of the Fargate stack because it has neither a load balancer nor a NAT gateway,
 * and it asks for that back in operational work -- you patch it, and you check the backups.
 *
 * Three deliberate choices:
 *
 *   * **No SSH.** Access is through SSM Session Manager, so there is no open port 22 and
 *     no key to lose. `deploy.sh` restarts the service the same way.
 *   * **Pages in S3, not on the disk.** The database is small and dumps in seconds; page
 *     images are the part that grows, and putting them in S3 keeps the backup a text file
 *     rather than a disk image.
 *   * **Postgres in a container on its own volume.** Separate from the root disk so it
 *     survives a rebuild of the instance and can be snapshotted on its own.
 *
 * When there are five schools, this stops being right and infra/aws is where to go.
 */

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = "yaadhum"
      Env     = var.environment
      Data    = "student-records"
    }
  }
}

locals {
  name = "yaadhum-${var.environment}"
}

# The default VPC on purpose. A single public instance needs no private subnets, no NAT
# and no endpoints, and building them anyway is how this option loses the saving that is
# its whole reason to exist.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.*-${var.architecture}"]
  }
}

# ── who can reach it ───────────────────────────────────────────────────────────────────

resource "aws_security_group" "instance" {
  name        = local.name
  description = "Yaadhum: web in, everything out. No SSH -- access is through SSM."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP. Redirects to HTTPS when a domain is set; the only way in without one."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS, terminated by Caddy with a certificate it gets itself."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Postgres is not here. It listens on the docker network only, so it has no port to open.

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── what it may do ─────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = local.name
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

# Session Manager, so there is no SSH port and no key.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

data "aws_iam_policy_document" "data_access" {
  # Page images. Scoped to the prefix the application writes, so a compromised instance
  # cannot enumerate the bucket.
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data.arn}/schools/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["schools/*", "backups/*"]
    }
  }
  # Database dumps. Write and read, never delete: retention is the bucket's lifecycle
  # rule, so a mistake on the instance cannot remove a backup.
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/backups/*"]
  }
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      aws_secretsmanager_secret.app.arn,
      var.anthropic_api_key_secret_arn,
      var.jina_api_key_secret_arn,
    ])
  }
}

resource "aws_iam_role_policy" "data_access" {
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.data_access.json
}

resource "aws_iam_instance_profile" "instance" {
  name = local.name
  role = aws_iam_role.instance.name
}
