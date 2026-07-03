output "app_url" {
  description = "ALB DNS name for the support bot"
  value       = aws_lb.app.dns_name
}

output "ecr_app_repo" {
  description = "ECR repository URL for the app image"
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_rival_repo" {
  description = "ECR repository URL for the rival-service image"
  value       = aws_ecr_repository.rival.repository_url
}

output "postgres_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}
