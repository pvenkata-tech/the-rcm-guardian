resource "aws_secretsmanager_secret" "database_url" {
  name_prefix             = "${local.name_prefix}-db-url-"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = {
    Name = "${local.name_prefix}-database-url"
  }
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s",
    var.db_username,
    random_password.db_master.result,
    aws_db_instance.main.address,
    var.db_name
  )

  depends_on = [aws_db_instance.main]
}
