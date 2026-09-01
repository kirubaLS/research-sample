output "api_url" {
  description = "Point NEXT_PUBLIC_API_BASE at this when building the web app."
  value       = var.certificate_arn == null ? "http://${aws_lb.main.dns_name}" : "https://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_name" {
  value = aws_ecs_service.api.name
}

output "migrate_task_family" {
  value = aws_ecs_task_definition.migrate.family
}

output "task_subnet_ids" {
  description = "Where a one-off task runs. Follows task_egress, so deploy.sh does not have to know which was chosen."
  value       = local.task_subnets
}

output "task_assign_public_ip" {
  value = local.task_public_ip ? "ENABLED" : "DISABLED"
}

output "docker_platform" {
  description = "Read by deploy.sh. An image built for the wrong architecture pulls, starts, and dies with an exec format error that reads like a broken entrypoint."
  value       = var.cpu_architecture == "ARM64" ? "linux/arm64" : "linux/amd64"
}

output "api_security_group_id" {
  value = aws_security_group.api.id
}

output "pages_bucket" {
  value = aws_s3_bucket.pages.bucket
}

output "database_endpoint" {
  value = aws_db_instance.main.address
}

output "database_master_secret_arn" {
  description = "RDS manages the password. Read it once to write the app's database URL secret."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "database_url_secret_arn" {
  description = "Write the full SQLAlchemy URL here after the database exists."
  value       = aws_secretsmanager_secret.database_url.arn
}
