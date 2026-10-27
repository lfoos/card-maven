variable "repositories" {
  description = "Repository names, e.g. [\"card-maven-api\", \"card-maven-workers\"]."
  type        = list(string)
}

variable "keep_images" {
  description = "How many images to retain per repository."
  type        = number
  default     = 50
}

variable "force_delete" {
  description = "Allow deleting repositories that still contain images."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
