#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  SafeVoice AI — One-Command Deploy Script
#  Usage: ./scripts/deploy.sh
#
#  What this does:
#  1. Initializes Terraform state bucket
#  2. Applies all GCP infrastructure
#  3. Builds and pushes Docker image
#  4. Deploys to Cloud Run
#  5. Prints the live backend URL
# ─────────────────────────────────────────────────────────────

set -e  # Exit on any error

# ── Config ────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-safevoice-ai}"
REGION="asia-south1"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/safevoice/backend:latest"

echo ""
echo "🛡️  SafeVoice AI — Deployment Starting"
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"
echo ""

# ── Step 1: Auth ──────────────────────────
echo "▶ Step 1/6: Authenticating with GCP..."
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet
gcloud config set project $PROJECT_ID

# ── Step 2: Terraform state bucket ────────
echo "▶ Step 2/6: Initializing Terraform state..."
gsutil mb -p $PROJECT_ID -l $REGION gs://safevoice-terraform-state 2>/dev/null || true

cd infrastructure
terraform init -backend-config="bucket=safevoice-terraform-state"

# ── Step 3: Terraform apply ────────────────
echo "▶ Step 3/6: Applying infrastructure..."
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="region=$REGION" \
  -var="twilio_account_sid=$TWILIO_ACCOUNT_SID" \
  -var="twilio_auth_token=$TWILIO_AUTH_TOKEN" \
  -var="twilio_sms_number=$TWILIO_SMS_NUMBER" \
  -var="twilio_whatsapp_number=$TWILIO_WHATSAPP_NUMBER" \
  -var="twilio_voice_number=$TWILIO_VOICE_NUMBER" \
  -var="google_maps_api_key=$GOOGLE_MAPS_API_KEY" \
  -auto-approve

cd ..

# ── Step 4: Run tests ─────────────────────
echo "▶ Step 4/6: Running tests..."
cd backend
pip install pytest pytest-asyncio --quiet
python -m pytest tests/ -v --tb=short
cd ..

# ── Step 5: Build and push Docker image ───
echo "▶ Step 5/6: Building Docker image..."
docker build -t $IMAGE ./backend
docker push $IMAGE

# ── Step 6: Deploy to Cloud Run ──────────
echo "▶ Step 6/6: Deploying to Cloud Run..."
gcloud run deploy safevoice-backend \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --min-instances 1 \
  --max-instances 10 \
  --memory 2Gi \
  --cpu 2 \
  --port 8080 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID,FIRESTORE_DB=safevoice-db"

# ── Print URL ─────────────────────────────
BACKEND_URL=$(gcloud run services describe safevoice-backend \
  --region $REGION \
  --format 'value(status.url)')

echo ""
echo "✅ Deployment complete!"
echo ""
echo "   Backend URL:  $BACKEND_URL"
echo "   WebSocket:    ${BACKEND_URL/https/wss}/ws/stream/{user_id}"
echo ""
echo "   Copy the WebSocket URL into your mobile app:"
echo "   EXPO_PUBLIC_BACKEND_WS_URL=${BACKEND_URL/https/wss}"
echo ""
echo "   Next steps:"
echo "   1. Take a screen recording of Cloud Run console for submission proof"
echo "   2. Run the mobile app: cd mobile && npx expo start"
echo "   3. Test with: say 'Help Me' on the registered device"
echo ""
