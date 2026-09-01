variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "instance_type" {
  description = <<-TEXT
    t4g.small is 2 vCPU and 2 GB for about a third of the Fargate bill, and it is tight:
    numpy and scipy are ~150 MB resident each, Postgres wants a few hundred more, and
    Tesseract reading a page wants a core to itself. It fits one school. Move to
    t4g.medium at the first out-of-memory, not after the second.
  TEXT
  type        = string
  default     = "t4g.small"
}

variable "architecture" {
  description = "Matches instance_type. t4g/t4g/m7g are arm64; t3/m5 are x86_64. deploy.sh builds for whichever this says."
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.architecture)
    error_message = "architecture must be \"arm64\" or \"x86_64\"."
  }
}

variable "data_volume_gb" {
  description = "Postgres only. Page images are in S3, so this holds marks and text and grows slowly."
  type        = number
  default     = 20
}

variable "bucket_name" {
  description = "Globally unique. Holds children's handwriting and the database dumps, so keep it boring and unguessable."
  type        = string
}

variable "backup_retention_days" {
  description = <<-TEXT
    How long a nightly dump is kept. Enforced by the bucket, not the instance -- the
    instance may write a backup and may not delete one, so a mistake on the box cannot
    remove the history.
  TEXT
  type        = number
  default     = 30
}

variable "domain" {
  description = <<-TEXT
    The hostname this answers on, pointed at the Elastic IP output BEFORE the first apply
    finishes booting -- Caddy asks for a certificate on start and needs the name to
    resolve. Leave null for a demo and it serves plain HTTP.
  TEXT
  type        = string
  default     = null
}

variable "anthropic_api_key_secret_arn" {
  type    = string
  default = null
}

variable "jina_api_key_secret_arn" {
  type    = string
  default = null
}
