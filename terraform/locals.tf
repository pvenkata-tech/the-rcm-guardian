locals {
  name_prefix = var.project_name

  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  container_name = "rcm-guardian-api"
  container_port = 8000

  openai_secret_parts = var.openai_api_secret_arn != "" ? (
    var.openai_api_secret_json_key != "" ? "${var.openai_api_secret_arn}:${var.openai_api_secret_json_key}::" : var.openai_api_secret_arn
  ) : ""

  anthropic_secret_parts = var.anthropic_api_secret_arn != "" ? (
    var.anthropic_api_secret_json_key != "" ? "${var.anthropic_api_secret_arn}:${var.anthropic_api_secret_json_key}::" : var.anthropic_api_secret_arn
  ) : ""

  langsmith_secret_parts = var.langsmith_api_secret_arn != "" ? (
    var.langsmith_api_secret_json_key != "" ? "${var.langsmith_api_secret_arn}:${var.langsmith_api_secret_json_key}::" : var.langsmith_api_secret_arn
  ) : ""
}
