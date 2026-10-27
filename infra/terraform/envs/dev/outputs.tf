output "vpc_id" {
  value = module.network.vpc_id
}

output "media_bucket" {
  value = module.media_bucket.bucket_name
}

output "ecr_repositories" {
  value = module.ecr.repository_urls
}
