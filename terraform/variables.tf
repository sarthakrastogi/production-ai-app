variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "app_image_tag" {
  description = "Docker image tag for the main app"
  type        = string
  default     = "latest"
}

variable "rival_image_tag" {
  description = "Docker image tag for the rival-service"
  type        = string
  default     = "latest"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "support_bot"
}

variable "db_user" {
  description = "PostgreSQL user"
  type        = string
  default     = "support_bot_app"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "mongodb_uri" {
  description = "MongoDB Atlas connection URI"
  type        = string
  sensitive   = true
}

variable "gptcache_url" {
  description = "GPTCache service URL"
  type        = string
  default     = "http://gptcache:8001"
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
}

variable "alarm_sns_topic_arns" {
  description = "SNS topic ARNs for CloudWatch alarm notifications"
  type        = list(string)
  default     = []
}
