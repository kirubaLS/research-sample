variable "region" {
  description = "Mumbai. Student work rests in India; this is a DPDP decision, not a latency one."
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "task_egress" {
  description = <<-TEXT
    How the task reaches the Anthropic and Jina APIs.

    "nat"    a NAT gateway. The task is unroutable from the internet and this costs about
             as much per month as the database.
    "public" a public IP on the task, at a fraction of that. The task is addressable but
             answers nothing: its security group accepts only the load balancer.

    "public" is the honest trade for one pilot school. Buy the NAT back before several
    schools' data sits behind it.
  TEXT
  type        = string
  default     = "nat"

  validation {
    condition     = contains(["nat", "public"], var.task_egress)
    error_message = "task_egress must be \"nat\" or \"public\"."
  }
}

variable "cpu_architecture" {
  description = <<-TEXT
    ARM64 (Graviton) is about 20% cheaper per vCPU-hour and every dependency here has an
    arm64 wheel. deploy.sh builds for whatever this says, so the two cannot disagree.

    Left at X86_64 because that is the only architecture this image has been built for.
    Switch it, run one deploy, and keep the saving if the build is clean.
  TEXT
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be \"X86_64\" or \"ARM64\"."
  }
}

variable "nat_per_az" {
  description = "A NAT gateway in each AZ. Doubles a real monthly cost to remove a failure mode that takes one school offline for minutes."
  type        = bool
  default     = false
}

# --- the image ---------------------------------------------------------------------------

variable "image_tag" {
  description = "Set by deploy.sh to the commit being released. Never 'latest': a tag has to name one image so a rollback is exact."
  type        = string
  default     = "bootstrap"
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "task_cpu" {
  description = "PyMuPDF rendering a page and Tesseract reading it are both CPU-bound; 512 makes a scan upload feel broken."
  type        = string
  default     = "1024"
}

variable "task_memory" {
  description = "numpy and scipy are about 150 MB resident each before a page is loaded."
  type        = string
  default     = "2048"
}

# --- the front door ------------------------------------------------------------------------

variable "certificate_arn" {
  description = "An ACM certificate in this region. Leave null only for a scratch environment: without it the listener is plain HTTP, and student data must not travel it."
  type        = string
  default     = null
}

variable "cors_origins" {
  description = "Exact origins of the web app. Never '*' -- the student test route is unauthenticated by design."
  type        = list(string)
  default     = []
}

variable "trusted_hosts" {
  description = "Host headers the API will answer to."
  type        = list(string)
  default     = ["*"]
}

# --- data -------------------------------------------------------------------------------

variable "pages_bucket_name" {
  description = "Globally unique. Holds children's handwriting, so keep it boring and unguessable."
  type        = string
}

variable "superseded_page_retention_days" {
  description = "How long a page the application deleted is kept as a noncurrent version."
  type        = number
  default     = 30
}

variable "postgres_version" {
  type    = string
  default = "16.4"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_storage_gb" {
  type    = number
  default = 20
}

variable "db_max_storage_gb" {
  type    = number
  default = 100
}

variable "db_username" {
  type    = string
  default = "yaadhum"
}

variable "db_multi_az" {
  description = "Off for a single-school pilot. On before a second school's marks are in it."
  type        = bool
  default     = false
}

variable "db_backup_days" {
  description = "A term of marking cannot be redone. Seven days is the floor, not a target."
  type        = number
  default     = 7
}

variable "db_performance_insights" {
  type    = bool
  default = false
}

# --- secrets, by ARN. Terraform never sees a value. ---------------------------------------

variable "anthropic_api_key_secret_arn" {
  type    = string
  default = null
}

variable "jina_api_key_secret_arn" {
  type    = string
  default = null
}

variable "platform_admin_key_secret_arn" {
  description = "Leave null and the operator console stays off, which is the right default."
  type        = string
  default     = null
}

# --- observability -------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Logs can carry a roll number. Keep them long enough to debug a term and no longer."
  type        = number
  default     = 30
}

variable "container_insights" {
  type    = bool
  default = false
}
