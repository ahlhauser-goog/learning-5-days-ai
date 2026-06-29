provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type        = string
  description = "The GCP project ID to deploy resources to."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "The GCP region for deployments."
}

variable "secret_name" {
  type        = string
  default     = "GEMINI_API_KEY"
  description = "Name of the secret in Secret Manager."
}

# Define Secret Manager Secret
resource "google_secret_manager_secret" "gemini_key" {
  secret_id = var.secret_name

  replication {
    automatic = true
  }
}

# Service Account for the Agent VM/Container
resource "google_service_account" "agent_sa" {
  account_id   = "bash-refactor-agent-sa"
  display_name = "Service Account for Bash Refactoring Agent"
}

# Grant the Service Account access to read the Secret Value
resource "google_secret_manager_secret_iam_member" "secret_reader" {
  project   = google_secret_manager_secret.gemini_key.project
  secret_id = google_secret_manager_secret.gemini_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}

# Output the Service Account Email for CI/CD setup
output "agent_service_account_email" {
  value       = google_service_account.agent_sa.email
  description = "The service account email the agent runs as."
}
