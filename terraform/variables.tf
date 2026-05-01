variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (e.g. dev, staging, prod)."
  default     = "dev"
}

variable "project_name" {
  type        = string
  description = "Short name used in resource names and tags."
  default     = "rcm-guardian"
}

variable "vpc_cidr" {
  type        = string
  description = "IPv4 CIDR for the dedicated VPC."
  default     = "10.0.0.0/16"
}

variable "ecs_desired_count" {
  type        = number
  description = "Number of Fargate tasks to run behind the ALB."
  default     = 2
}

variable "ecs_cpu" {
  type        = number
  description = "Fargate task CPU units (e.g. 512)."
  default     = 512
}

variable "ecs_memory" {
  type        = number
  description = "Fargate task memory (MiB), must match valid CPU/memory pairs."
  default     = 1024
}

variable "db_allocated_storage" {
  type        = number
  description = "RDS allocated storage in GB."
  default     = 20
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class (use larger sizes for production)."
  default     = "db.t4g.micro"
}

variable "db_multi_az" {
  type        = bool
  description = "Enable Multi-AZ for RDS (recommended for production)."
  default     = false
}

variable "db_deletion_protection" {
  type        = bool
  description = "Prevent accidental RDS deletion."
  default     = false
}

variable "db_skip_final_snapshot" {
  type        = bool
  description = "If true, no final snapshot when RDS is destroyed (dev only)."
  default     = true
}

variable "db_name" {
  type        = string
  description = "PostgreSQL database name."
  default     = "rcm_guardian"
}

variable "db_username" {
  type        = string
  description = "PostgreSQL master username."
  default     = "rcmadmin"
}

variable "openai_api_secret_arn" {
  type        = string
  description = "Secrets Manager secret ARN holding OPENAI_API_KEY as plaintext or JSON key api_key."
  default     = ""
}

variable "openai_api_secret_json_key" {
  type        = string
  description = "If the OpenAI secret is JSON, the key containing the API key (e.g. api_key)."
  default     = ""
}

variable "openai_vision_model" {
  type        = string
  description = "OpenAI multimodal model for document extraction."
  default     = "gpt-4o"
}

variable "openai_embedding_model" {
  type        = string
  description = "OpenAI embedding model for payer-rules RAG."
  default     = "text-embedding-3-small"
}

variable "anthropic_api_secret_arn" {
  type        = string
  description = "Optional Secrets Manager secret ARN for ANTHROPIC_API_KEY (vision fallback)."
  default     = ""
}

variable "anthropic_api_secret_json_key" {
  type        = string
  description = "If the Anthropic secret is JSON, the key containing the API key."
  default     = ""
}

variable "anthropic_vision_model" {
  type        = string
  description = "Anthropic Claude model when using vision fallback."
  default     = "claude-3-5-sonnet-20241022"
}

variable "certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN for HTTPS listener on port 443. Leave empty for HTTP-only."
  default     = ""
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to reach the ALB on ports 80/443."
  default     = ["0.0.0.0/0"]
}
