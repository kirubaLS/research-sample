/**
 * What runs on the box, and what terminates TLS in front of it.
 *
 * Caddy is here for one reason: without a load balancer something has to hold the
 * certificate, and Caddy gets and renews one on its own. Set `domain` and it is HTTPS with
 * no further work. Leave it null and it serves plain HTTP, which is a demo and must not
 * carry a school's data.
 */

locals {
  compose = templatefile("${path.module}/compose.yaml.tftpl", {
    repository_url = aws_ecr_repository.api.repository_url
    environment    = var.environment
    bucket         = aws_s3_bucket.data.bucket
    region         = var.region
  })

  caddyfile = var.domain == null ? "  :80 {\n    reverse_proxy api:8000\n  }\n" : join("\n", [
    "${var.domain} {",
    "  reverse_proxy api:8000",
    "  encode gzip",
    "  request_body {",
    # A scan is several photographs; Caddy's default is smaller than one page of one.
    "    max_size 25MB",
    "  }",
    "}",
  ])

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    compose    = local.compose
    caddyfile  = local.caddyfile
    region     = var.region
    bucket     = aws_s3_bucket.data.bucket
    registry   = split("/", aws_ecr_repository.api.repository_url)[0]
    app_secret = aws_secretsmanager_secret.app.arn
  })
}
