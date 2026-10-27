variable "region" {
  type    = string
  default = "us-west-2"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "web_origins" {
  description = "Origins the web app is served from."
  type        = list(string)
  default     = ["http://localhost:5173"]
}
