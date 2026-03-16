# ─────────────────────────────────────────────────────────────
#  SafeVoice AI — Terraform Infrastructure
#  Deploys the complete GCP stack in one command:
#  terraform init && terraform apply
# ─────────────────────────────────────────────────────────────

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "safevoice-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}


# ─────────────────────────────────────────
#  Variables
# ─────────────────────────────────────────
variable "project_id" {
  description = "Your GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "asia-south1"   # Mumbai — closest to India
}

variable "twilio_account_sid" {
  description = "Twilio Account SID"
  type        = string
  sensitive   = true
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
}

variable "twilio_sms_number" {
  type      = string
  sensitive = true
}

variable "twilio_whatsapp_number" {
  type      = string
  sensitive = true
}

variable "twilio_voice_number" {
  type      = string
  sensitive = true
}

variable "google_maps_api_key" {
  type      = string
  sensitive = true
}


# ─────────────────────────────────────────
#  Enable Required APIs
# ─────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "maps-backend.googleapis.com",
    "geolocation.googleapis.com",
    "firebase.googleapis.com",
    "fcm.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])
  project = var.project_id
  service = each.value
  disable_on_destroy = false
}


# ─────────────────────────────────────────
#  Service Account
# ─────────────────────────────────────────
resource "google_service_account" "safevoice_agent" {
  account_id   = "safevoice-agent"
  display_name = "SafeVoice Agent Service Account"
}

resource "google_project_iam_member" "roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
    "roles/run.invoker",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.safevoice_agent.email}"
}


# ─────────────────────────────────────────
#  Secret Manager — All sensitive values
# ─────────────────────────────────────────
resource "google_secret_manager_secret" "twilio_sid" {
  secret_id = "twilio-account-sid"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "twilio_sid_val" {
  secret      = google_secret_manager_secret.twilio_sid.id
  secret_data = var.twilio_account_sid
}

resource "google_secret_manager_secret" "twilio_token" {
  secret_id = "twilio-auth-token"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "twilio_token_val" {
  secret      = google_secret_manager_secret.twilio_token.id
  secret_data = var.twilio_auth_token
}

resource "google_secret_manager_secret" "twilio_sms" {
  secret_id = "twilio-sms-number"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "twilio_sms_val" {
  secret      = google_secret_manager_secret.twilio_sms.id
  secret_data = var.twilio_sms_number
}

resource "google_secret_manager_secret" "maps_key" {
  secret_id = "google-maps-api-key"
  replication { auto {} }
}
resource "google_secret_manager_secret_version" "maps_key_val" {
  secret      = google_secret_manager_secret.maps_key.id
  secret_data = var.google_maps_api_key
}


# ─────────────────────────────────────────
#  Firestore Database
# ─────────────────────────────────────────
resource "google_firestore_database" "safevoice" {
  project     = var.project_id
  name        = "safevoice-db"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

resource "google_firestore_index" "incidents_by_user" {
  project    = var.project_id
  database   = google_firestore_database.safevoice.name
  collection = "incidents"

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "triggered_at"
    order      = "DESCENDING"
  }
}


# ─────────────────────────────────────────
#  Cloud Storage — Voice Recordings
# ─────────────────────────────────────────
resource "google_storage_bucket" "recordings" {
  name                        = "safevoice-recordings-${var.project_id}"
  location                    = var.region
  uniform_bucket_level_access = true

  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 365 }   # Auto-delete recordings after 1 year
  }

  versioning { enabled = false }
}


# ─────────────────────────────────────────
#  Artifact Registry — Docker images
# ─────────────────────────────────────────
resource "google_artifact_registry_repository" "safevoice" {
  repository_id = "safevoice"
  format        = "DOCKER"
  location      = var.region
  description   = "SafeVoice AI Docker images"

  depends_on = [google_project_service.apis]
}


# ─────────────────────────────────────────
#  Cloud Run — Backend Service
# ─────────────────────────────────────────
resource "google_cloud_run_v2_service" "safevoice_backend" {
  name     = "safevoice-backend"
  location = var.region

  template {
    service_account = google_service_account.safevoice_agent.email

    scaling {
      min_instance_count = 1   # Always warm — no cold starts for emergencies
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/safevoice/backend:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      # Environment variables from Secret Manager
      env {
        name = "TWILIO_ACCOUNT_SID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.twilio_sid.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TWILIO_AUTH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.twilio_token.id
            version = "latest"
          }
        }
      }
      env {
        name = "TWILIO_SMS_NUMBER"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.twilio_sms.id
            version = "latest"
          }
        }
      }
      env {
        name = "GOOGLE_MAPS_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.maps_key.id
            version = "latest"
          }
        }
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIRESTORE_DB"
        value = "safevoice-db"
      }

      ports {
        container_port = 8080
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.safevoice,
    google_secret_manager_secret_version.twilio_sid_val,
  ]
}

# Make Cloud Run publicly accessible (WebSocket connections from mobile)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.safevoice_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ─────────────────────────────────────────
#  Cloud Build Trigger — CI/CD
# ─────────────────────────────────────────
resource "google_cloudbuild_trigger" "safevoice" {
  name        = "safevoice-deploy"
  description = "Auto-deploy on push to main"

  github {
    owner = "your-github-username"
    name  = "safevoice-ai"
    push { branch = "^main$" }
  }

  build {
    step {
      name = "gcr.io/cloud-builders/docker"
      args = [
        "build",
        "-t", "${var.region}-docker.pkg.dev/${var.project_id}/safevoice/backend:$COMMIT_SHA",
        "-t", "${var.region}-docker.pkg.dev/${var.project_id}/safevoice/backend:latest",
        "./backend",
      ]
    }
    step {
      name = "gcr.io/cloud-builders/docker"
      args = [
        "push",
        "${var.region}-docker.pkg.dev/${var.project_id}/safevoice/backend:latest",
      ]
    }
    step {
      name       = "gcr.io/cloud-builders/gcloud"
      entrypoint = "bash"
      args = [
        "-c",
        "cd backend && pip install pytest && pytest tests/ -v"
      ]
    }
    step {
      name = "gcr.io/cloud-builders/gcloud"
      args = [
        "run", "deploy", "safevoice-backend",
        "--image", "${var.region}-docker.pkg.dev/${var.project_id}/safevoice/backend:latest",
        "--region", var.region,
        "--platform", "managed",
      ]
    }
  }
}


# ─────────────────────────────────────────
#  Outputs
# ─────────────────────────────────────────
output "backend_url" {
  value       = google_cloud_run_v2_service.safevoice_backend.uri
  description = "Cloud Run backend URL — use this as WS_URL in mobile app"
}

output "firestore_db" {
  value       = google_firestore_database.safevoice.name
  description = "Firestore database name"
}

output "recordings_bucket" {
  value       = google_storage_bucket.recordings.name
  description = "Cloud Storage bucket for voice recordings"
}
