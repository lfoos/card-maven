variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "allowed_origins" {
  description = "Web origins allowed to upload with presigned URLs."
  type        = list(string)
  validation {
    condition     = length(var.allowed_origins) > 0 && !contains(var.allowed_origins, "*")
    error_message = "allowed_origins must list explicit origins (no wildcard)."
  }
}

variable "noncurrent_version_days" {
  description = "Days to keep overwritten or deleted image versions."
  type        = number
  default     = 30
}

variable "force_destroy" {
  description = "Allow destroying a non-empty bucket. Never true in prod."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
