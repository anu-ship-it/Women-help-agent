"""
SafeVoice AI — Emergency Tools
All 5 tools used by the ADK agent.
Each tool is a standalone async function registered with the agent.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from google.adk.tools import FunctionTool

from ..services.maps_service    import MapsService
from ..services.twilio_service  import TwilioService
from ..services.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

maps_svc     = MapsService()
twilio_svc   = TwilioService()
firestore_svc = FirestoreService()


# ─────────────────────────────────────────
#  Tool 1 — Get GPS Location
# ─────────────────────────────────────────
async def get_gps_location(user_id: str) -> dict:
    """
    Captures the user's current GPS location.
    Falls back to cell tower / WiFi triangulation if GPS signal is weak.

    Returns:
        dict with lat, lng, address, accuracy_meters, timestamp
    """
    try:
        location = await maps_svc.get_location(user_id)
        logger.info(f"[{user_id}] GPS: {location['lat']}, {location['lng']} "
                    f"(accuracy: {location['accuracy_meters']}m)")
        return location
    except Exception as e:
        logger.error(f"[{user_id}] GPS failed, using last known: {e}")
        # Fall back to last known location stored in Firestore
        last_known = await firestore_svc.get_last_known_location(user_id)
        last_known["fallback"] = True
        return last_known


# ─────────────────────────────────────────
#  Tool 2 — Send Emergency SMS
# ─────────────────────────────────────────
async def send_emergency_sms(
    user_id: str,
    user_data: dict,
    gps_data: dict,
    incident_id: str,
) -> dict:
    """
    Sends emergency SMS with live Google Maps link to all contacts.
    Uses Twilio — works on 2G with minimal data.

    Returns:
        dict with status, message_sids, failed_numbers
    """
    contacts = user_data.get("emergency_contacts", [])
    user_name = user_data.get("name", "User")
    maps_link = _build_maps_link(gps_data)
    address   = gps_data.get("address", "Location unavailable")

    message = (
        f"EMERGENCY ALERT: {user_name} needs help!\n"
        f"Location: {address}\n"
        f"Live GPS: {maps_link}\n"
        f"Incident: {incident_id}\n"
        f"This is an automated SafeVoice AI alert."
    )

    tasks = [
        twilio_svc.send_sms(contact["phone"], message)
        for contact in contacts
        if contact.get("verified", False)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = [r for r in results if not isinstance(r, Exception)]
    failed  = [str(r) for r in results if isinstance(r, Exception)]

    logger.info(f"[{user_id}] SMS sent to {len(success)}/{len(tasks)} contacts")
    if failed:
        logger.warning(f"[{user_id}] SMS failures: {failed}")

    return {"status": "sent", "success_count": len(success), "failed": failed}


# ─────────────────────────────────────────
#  Tool 3 — Call Helpline
# ─────────────────────────────────────────
async def call_helpline(
    user_id: str,
    user_data: dict,
    gps_data: dict,
    incident_id: str,
    emergency_number: str = "181",  # Women's helpline India
) -> dict:
    """
    Places an AI voice call to the women's helpline.
    Plays the user's pre-recorded voice message for authenticity.
    Uses Twilio Voice + TwiML for call orchestration.

    Returns:
        dict with call_sid, status
    """
    recorded_voice_url = user_data.get("emergency_recording_url")
    user_name = user_data.get("name", "User")
    address   = gps_data.get("address", "unknown location")

    # TwiML script — plays user's real voice, then AI continues
    twiml = f"""
    <Response>
        <Play>{recorded_voice_url}</Play>
        <Say voice="alice" language="en-IN">
            This is an automated emergency alert from SafeVoice AI.
            {user_name} is in danger at {address}.
            Incident reference: {incident_id}.
            Please send help immediately.
            The live GPS location is being updated every 60 seconds.
        </Say>
        <Pause length="3"/>
        <Say voice="alice" language="en-IN">
            If you need to speak with {user_name}, she may not be able to respond.
            Please dispatch emergency services to the GPS coordinates provided.
        </Say>
    </Response>
    """

    try:
        call_sid = await twilio_svc.make_call(
            to=emergency_number,
            twiml=twiml,
            machine_detection="Enable",      # Detects voicemail vs human
            machine_detection_timeout=8,
        )
        logger.info(f"[{user_id}] Helpline call placed: {call_sid}")
        return {"status": "calling", "call_sid": call_sid, "number": emergency_number}

    except Exception as e:
        logger.error(f"[{user_id}] Helpline call failed: {e}")
        return {"status": "failed", "error": str(e)}


# ─────────────────────────────────────────
#  Tool 4 — Notify Emergency Contacts
# ─────────────────────────────────────────
async def notify_emergency_contacts(
    user_id: str,
    user_data: dict,
    gps_data: Optional[dict],
    incident_id: str,
    update_only: bool = False,   # True = GPS update, not initial alert
    all_clear: bool = False,     # True = user confirmed safe
) -> dict:
    """
    Calls emergency contacts via Twilio Voice.
    Retries every 30 seconds if unanswered.
    Also sends WhatsApp message simultaneously.

    Returns:
        dict with call_results per contact
    """
    contacts = user_data.get("emergency_contacts", [])
    user_name = user_data.get("name", "User")

    if all_clear:
        # Send all-clear to all contacts
        message = f"SafeVoice AI: {user_name} is now SAFE. Incident {incident_id} resolved."
        tasks = [
            twilio_svc.send_whatsapp(contact["phone"], message)
            for contact in contacts if contact.get("verified")
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "all_clear_sent"}

    if update_only and gps_data:
        # Just push updated GPS link
        maps_link = _build_maps_link(gps_data)
        message = f"SafeVoice AI: {user_name} GPS update — {maps_link}"
        tasks = [
            twilio_svc.send_whatsapp(contact["phone"], message)
            for contact in contacts if contact.get("verified")
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        return {"status": "gps_updated"}

    # Initial alert — call each contact with retry logic
    maps_link = _build_maps_link(gps_data)
    address   = gps_data.get("address", "unknown location")

    call_tasks = []
    whatsapp_tasks = []

    for contact in contacts:
        if not contact.get("verified"):
            continue

        # Voice call TwiML
        twiml = f"""
        <Response>
            <Say voice="alice" language="en-IN">
                Emergency alert from SafeVoice AI.
                {user_name} is in danger and needs your help immediately.
                She is at {address}.
                Please go to her location or call emergency services.
                Press any key to acknowledge this alert.
            </Say>
            <Gather numDigits="1" timeout="10">
                <Say>Press any key to acknowledge.</Say>
            </Gather>
        </Response>
        """

        call_tasks.append(
            twilio_svc.make_call(
                to=contact["phone"],
                twiml=twiml,
                machine_detection="Enable",
            )
        )

        # WhatsApp simultaneously
        whatsapp_message = (
            f"🚨 EMERGENCY: {user_name} needs help!\n"
            f"📍 {address}\n"
            f"🗺️ Live location: {maps_link}\n"
            f"Please respond immediately or call 112."
        )
        whatsapp_tasks.append(
            twilio_svc.send_whatsapp(contact["phone"], whatsapp_message)
        )

    # Fire voice calls and WhatsApp in parallel
    call_results     = await asyncio.gather(*call_tasks, return_exceptions=True)
    whatsapp_results = await asyncio.gather(*whatsapp_tasks, return_exceptions=True)

    logger.info(f"[{user_id}] Contacts notified: {len(call_tasks)} calls, "
                f"{len(whatsapp_tasks)} WhatsApp messages")

    return {
        "status": "notified",
        "calls": len([r for r in call_results if not isinstance(r, Exception)]),
        "whatsapp": len([r for r in whatsapp_results if not isinstance(r, Exception)]),
    }


# ─────────────────────────────────────────
#  Tool 5 — Log Incident to Firestore
# ─────────────────────────────────────────
async def log_incident_to_firestore(
    user_id: str,
    user_data: dict,
    gps_data: dict,
    incident_id: str,
) -> dict:
    """
    Creates an incident record in Firestore.
    Used for audit trail, incident history, and follow-up.

    Returns:
        dict with incident_id, firestore_path
    """
    incident = {
        "incident_id":    incident_id,
        "user_id":        user_id,
        "user_name":      user_data.get("name"),
        "triggered_at":   datetime.now(timezone.utc).isoformat(),
        "status":         "ACTIVE",
        "gps_history":    [gps_data],
        "contacts_notified": [
            c["phone"] for c in user_data.get("emergency_contacts", [])
            if c.get("verified")
        ],
        "resolved_at":    None,
    }

    path = await firestore_svc.create_incident(incident)
    logger.info(f"[{user_id}] Incident logged: {path}")
    return {"incident_id": incident_id, "firestore_path": path}


# ─────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────
def _build_maps_link(gps_data: dict) -> str:
    """Build a Google Maps link from GPS coordinates."""
    lat = gps_data.get("lat", 0)
    lng = gps_data.get("lng", 0)
    return f"https://maps.google.com/?q={lat},{lng}&z=17"
