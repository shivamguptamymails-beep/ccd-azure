variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "location" {
  type = string
}

variable "cosmos_location" {
  type    = string
  default = null
}

variable "resource_group_name" {
  type = string
}

variable "suffix" {
  type = string
}

variable "blob_reader_principal_id" {
  description = "Principal (the apps' managed identity) allowed to read model blobs."
  type        = string
}

variable "tags" {
  type = map(string)
}
