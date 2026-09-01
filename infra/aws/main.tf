/**
 * Yaadhum on AWS, in ap-south-1.
 *
 * The region is not a preference. Answer scripts are children's handwriting and the marks
 * derived from them are about named minors, so where that data RESTS is a DPDP Act
 * question. Mumbai keeps it in India; every other decision here follows from that one.
 *
 * Shape: an ALB in public subnets, the API as a Fargate service in private subnets, RDS
 * and S3 reached over private networking. The container never has a public address and
 * the database never leaves the VPC.
 *
 * What this file does NOT do, on purpose:
 *   * create a domain or a certificate -- pass an ACM ARN and the listener becomes HTTPS
 *   * build or push the image -- see push.sh, so a deploy is a script somebody can read
 *   * hold any secret -- the database URL and API keys are Secrets Manager entries you
 *     create once, referenced here by ARN
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
      # Tagged because a data-residency claim is only as good as the ability to show
      # which resources hold student work.
      Data = "student-records"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "yaadhum-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}

# ── network ────────────────────────────────────────────────────────────────────────────
# Two AZs because RDS requires a subnet group spanning two, and because one AZ is not a
# deployment, it is a single point of failure with extra steps.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = local.name }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${local.name}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# The task needs egress for the Anthropic and Jina APIs, and there are two ways to give it
# that. A NAT gateway keeps the task unroutable from the internet and costs about as much
# per month as the database. A public IP on the task costs a fraction of that and leaves
# the task addressable, though still refusing everything: its security group accepts
# nothing but the load balancer.
#
# For one pilot school the second is the honest trade. Before several schools' data sits
# behind it, buy the NAT back -- it is one variable.
locals {
  nat_count = var.task_egress == "nat" ? (var.nat_per_az ? 2 : 1) : 0
  # Where the task runs follows from that choice: with no NAT there is no route out of a
  # private subnet, so the task has to sit in a public one to reach anything.
  task_subnets   = var.task_egress == "nat" ? aws_subnet.private[*].id : aws_subnet.public[*].id
  task_public_ip = var.task_egress != "nat"
}

resource "aws_eip" "nat" {
  count  = local.nat_count
  domain = "vpc"
  tags   = { Name = "${local.name}-nat-${count.index}" }
}

resource "aws_nat_gateway" "main" {
  count         = local.nat_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  depends_on    = [aws_internet_gateway.main]
  tags          = { Name = "${local.name}-nat-${count.index}" }
}

# The private subnets hold the database either way. With no NAT they have no route out at
# all, which is what you want for a database and is why RDS stays here regardless.
resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.main.id

  dynamic "route" {
    for_each = local.nat_count > 0 ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.main[var.nat_per_az ? count.index : 0].id
    }
  }

  tags = { Name = "${local.name}-private-${count.index}" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# S3 over a gateway endpoint: page images never traverse the NAT, which is both cheaper
# and one less place the traffic can leave the VPC.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id
  tags              = { Name = "${local.name}-s3" }
}
