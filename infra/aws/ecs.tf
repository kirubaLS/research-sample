/**
 * The task, its permissions, and the service that keeps it running.
 *
 * The task role can read and write exactly one prefix of one bucket and read exactly the
 * secrets this app needs. Nothing here has a wildcard on student data.
 */

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = var.container_insights ? "enabled" : "disabled"
  }
}

# --- roles -----------------------------------------------------------------------------

data "aws_iam_policy_document" "assume_task" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Used by the agent to pull the image and read secrets INTO the container. Distinct from
# the task role: the agent's power ends once the container is running.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.assume_task.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      # The one the task cannot start without. Leaving it out of this list is a deploy
      # that pulls the image, passes its plan, and dies on the first connection.
      aws_secretsmanager_secret.database_url.arn,
      aws_db_instance.main.master_user_secret[0].secret_arn,
      var.anthropic_api_key_secret_arn,
      var.jina_api_key_secret_arn,
      var.platform_admin_key_secret_arn,
    ])
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

# Used by the application itself.
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume_task.json
}

data "aws_iam_policy_document" "pages" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.pages.arn}/schools/*"]
  }
  # ListBucket is scoped to the same prefix: the app never needs to enumerate the bucket,
  # and a role that can would make one leaked credential a directory of every school.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.pages.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["schools/*"]
    }
  }
}

resource "aws_iam_role_policy" "task_pages" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.pages.json
}

# --- the task ---------------------------------------------------------------------------

locals {
  image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"

  # The database URL is assembled from the RDS-managed secret rather than stored again.
  # One copy of a credential is one place it can leak.
  environment = [
    { name = "YAADHUM_ENVIRONMENT", value = var.environment },
    { name = "YAADHUM_CORS_ORIGINS", value = join(",", var.cors_origins) },
    { name = "YAADHUM_STORAGE_BACKEND", value = "s3" },
    { name = "YAADHUM_S3_BUCKET", value = aws_s3_bucket.pages.bucket },
    { name = "YAADHUM_S3_REGION", value = var.region },
    { name = "YAADHUM_TRUSTED_HOSTS", value = join(",", var.trusted_hosts) },
  ]

  secrets = concat(
    [
      { name = "YAADHUM_DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
      { name = "YAADHUM_MIGRATION_DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    ],
    var.anthropic_api_key_secret_arn == null ? [] : [
      { name = "YAADHUM_ANTHROPIC_API_KEY", valueFrom = var.anthropic_api_key_secret_arn }
    ],
    var.jina_api_key_secret_arn == null ? [] : [
      { name = "YAADHUM_JINA_API_KEY", valueFrom = var.jina_api_key_secret_arn }
    ],
    var.platform_admin_key_secret_arn == null ? [] : [
      { name = "YAADHUM_PLATFORM_ADMIN_KEY", valueFrom = var.platform_admin_key_secret_arn }
    ],
  )
}

# Written once by hand after the database exists, holding the full SQLAlchemy URL. Kept
# out of Terraform state by having Terraform create the container and never the value.
resource "aws_secretsmanager_secret" "database_url" {
  name = "${local.name}/database-url"
}

resource "aws_ecs_task_definition" "api" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "api"
    image        = local.image
    essential    = true
    command      = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = local.environment
    secrets      = local.secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
}

# The same image with a different command. Run it before shifting traffic; it is not part
# of the service, so several tasks cannot race to migrate one database.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name        = "migrate"
    image       = local.image
    essential   = true
    command     = ["alembic", "upgrade", "head"]
    environment = local.environment
    secrets     = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # A new task has to pass its health check before the old one is drained.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true # a bad image rolls back rather than leaving the school with nothing
  }

  depends_on = [aws_lb_listener.http, aws_lb_listener.https]

  lifecycle {
    # deploy.sh moves the tag; Terraform should not fight it back on the next plan.
    ignore_changes = [task_definition, desired_count]
  }
}
