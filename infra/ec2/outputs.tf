output "public_ip" {
  description = "Point the domain's A record here."
  value       = aws_eip.main.public_ip
}

output "url" {
  value = var.domain == null ? "http://${aws_eip.main.public_ip}" : "https://${var.domain}"
}

output "instance_id" {
  description = "For `aws ssm start-session --target <this>`. There is no SSH."
  value       = aws_instance.main.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "docker_platform" {
  description = "Read by deploy.sh. An image built for the wrong architecture pulls, starts, and dies with an exec format error that reads like a broken entrypoint."
  value       = var.architecture == "arm64" ? "linux/arm64" : "linux/amd64"
}

output "bucket" {
  value = aws_s3_bucket.data.bucket
}

output "app_secret_arn" {
  description = "Write the environment file here once: POSTGRES_PASSWORD and the rest."
  value       = aws_secretsmanager_secret.app.arn
}
