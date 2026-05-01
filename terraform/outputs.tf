output "alb_dns_name" {
  description = "Public DNS name for the load balancer (HTTP on :80; HTTPS on :443 when certificate_arn is set)."
  value       = aws_lb.main.dns_name
}

output "alb_url_http" {
  description = "Base HTTP URL for quick testing."
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "Docker registry URL to push images."
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}

output "documents_bucket_name" {
  description = "Private SSE-S3 bucket for document storage (maps to Docker ./uploads)."
  value       = aws_s3_bucket.documents.id
}

output "database_secret_arn" {
  description = "Secrets Manager secret holding DATABASE_URL for asyncpg."
  value       = aws_secretsmanager_secret.database_url.arn
}

output "rds_endpoint" {
  description = "RDS hostname (same credentials embedded in DATABASE_URL secret)."
  value       = aws_db_instance.main.address
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}
