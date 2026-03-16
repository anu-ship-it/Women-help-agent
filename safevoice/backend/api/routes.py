"""
SafeVoice AI — WebSocket Handler + FastAPI Routes
The bridge between mobile app and Gemini Live API.
Deployed on Google Cloud Run.
"""

import asyncio
import logging
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent.agent import SafeVoiceLiveSession
from .services.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

app = FastAPI(title="SafeVoice AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

firestore_svc = FirestoreService()

# Active sessions: user_id -> SafeVoiceLiveSession
active_sessions: Dict[str, SafeVoiceLiveSession] = {}


# ─────────────────────────────────────────
#  WebSocket — Main Audio Stream
# ─────────────────────────────────────────
@app.websocket("/ws/stream/{user_id}")
async def audio_stream(websocket: WebSocket, user_id: str):
    """
    Main WebSocket endpoint.
    Mobile app connects here and streams raw PCM audio continuously.

    Protocol:
        Client → Server: raw bytes (PCM 16kHz audio)
        Client → Server: JSON {"action": "cancel"}
        Client → Server: JSON {"action": "safe_confirmed"}
        Server → Client: JSON {"event": "KEYWORD_DETECTED", ...}
        Server → Client: JSON {"event": "EMERGENCY_ACTIVE", ...}
        Server → Client: JSON {"event": "GPS_UPDATE", ...}
        Server → Client: JSON {"event": "RESOLVED", ...}
    """
    await websocket.accept()
    logger.info(f"[{user_id}] WebSocket connected")

    # Load user data from Firestore
    user_data = await firestore_svc.get_user(user_id)
    if not user_data:
        await websocket.send_json({"event": "ERROR", "message": "User not found"})
        await websocket.close()
        return

    # Create a new live session for this user
    session = SafeVoiceLiveSession(user_id=user_id, user_data=user_data)
    active_sessions[user_id] = session

    try:
        # Start Gemini Live API session and audio loop
        await asyncio.gather(
            session.start(websocket),
            _handle_control_messages(websocket, session, user_id),
        )
    except WebSocketDisconnect:
        logger.info(f"[{user_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{user_id}] Session error: {e}", exc_info=True)
    finally:
        active_sessions.pop(user_id, None)
        logger.info(f"[{user_id}] Session cleaned up")


async def _handle_control_messages(
    websocket: WebSocket,
    session: SafeVoiceLiveSession,
    user_id: str,
):
    """
    Listen for JSON control messages from mobile app alongside audio.
    Runs concurrently with the audio stream.
    """
    async for message in websocket.iter_json():
        action = message.get("action")

        if action == "cancel":
            await session.cancel_trigger()

        elif action == "safe_confirmed":
            await session.confirm_safe(websocket)

        elif action == "silent_trigger":
            # User triggered via gesture or button press
            logger.info(f"[{user_id}] Silent trigger received")
            await session._on_keyword_detected(websocket)

        elif action == "ping":
            await websocket.send_json({"event": "pong"})


# ─────────────────────────────────────────
#  REST API — Onboarding
# ─────────────────────────────────────────
class OnboardingRequest(BaseModel):
    user_id:   str
    name:      str
    phone:     str
    contacts:  list   # [{name, phone}]


@app.post("/api/onboard")
async def onboard_user(req: OnboardingRequest):
    """
    Register a new user — stores profile in Firestore.
    Called once during app setup.
    """
    user_data = {
        "user_id": req.user_id,
        "name":    req.name,
        "phone":   req.phone,
        "emergency_contacts": [
            {**c, "verified": False}
            for c in req.contacts
        ],
        "voice_baseline_set": False,
        "onboarding_complete": False,
    }

    await firestore_svc.create_user(user_data)

    # Send verification SMS to each contact
    from .services.twilio_service import TwilioService
    twilio = TwilioService()
    verification_tasks = []

    for contact in req.contacts:
        msg = (
            f"Hi {contact['name']}, {req.name} has added you as an emergency contact "
            f"on SafeVoice AI. Reply YES to confirm, or STOP to decline."
        )
        verification_tasks.append(twilio.send_sms(contact["phone"], msg))

    await asyncio.gather(*verification_tasks, return_exceptions=True)

    return {"status": "onboarded", "verification_sent": len(req.contacts)}


@app.post("/api/onboard/voice-baseline/{user_id}")
async def save_voice_baseline(user_id: str, audio_data: bytes):
    """
    Save user's voice biometric baseline.
    Called after recording "Help Me" 5 times during onboarding.
    """
    from .agent.voice_verify import VoiceVerifier
    verifier = VoiceVerifier(user_id)
    features = verifier._extract_mfcc(audio_data)

    await firestore_svc.save_voice_baseline(user_id, {"embedding": features})

    return {"status": "baseline_saved"}


@app.post("/api/onboard/emergency-recording/{user_id}")
async def save_emergency_recording(user_id: str, audio_data: bytes):
    """
    Save user's emergency voice recording (played to helpline).
    Uploaded to Cloud Storage, URL saved in Firestore.
    """
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket("safevoice-recordings")
    blob   = bucket.blob(f"recordings/{user_id}/emergency.wav")
    blob.upload_from_string(audio_data, content_type="audio/wav")
    blob.make_public()

    url = blob.public_url
    await firestore_svc.update_user(user_id, {"emergency_recording_url": url})

    return {"status": "recording_saved", "url": url}


@app.post("/api/contacts/verify")
async def verify_contact(payload: dict):
    """
    Called by Twilio webhook when a contact replies YES.
    Marks contact as verified in Firestore.
    """
    phone   = payload.get("From", "").replace("whatsapp:", "")
    body    = payload.get("Body", "").strip().upper()

    if body == "YES":
        await firestore_svc.verify_contact(phone)
        return {"status": "verified", "phone": phone}

    return {"status": "ignored"}


# ─────────────────────────────────────────
#  REST API — Incident Management
# ─────────────────────────────────────────
@app.get("/api/incidents/{user_id}")
async def get_incidents(user_id: str):
    """Returns the user's incident history."""
    incidents = await firestore_svc.get_incidents(user_id)
    return {"incidents": incidents}


@app.get("/api/health")
async def health_check():
    """Health check for Cloud Run."""
    return {"status": "ok", "service": "safevoice-backend"}
