"""
SafeVoice AI — Service Layer
Twilio, Google Maps Platform, Firestore
"""

import os
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

# ─────────────────────────────────────────
#  Twilio Service
# ─────────────────────────────────────────
from twilio.rest import Client as TwilioClient

logger = logging.getLogger(__name__)


class TwilioService:
    """SMS, Voice Calls, and WhatsApp via Twilio."""

    def __init__(self):
        self.client   = TwilioClient(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        self.from_sms      = os.environ["TWILIO_SMS_NUMBER"]       # e.g. +15005550006
        self.from_whatsapp = os.environ["TWILIO_WHATSAPP_NUMBER"]  # e.g. whatsapp:+14155238886
        self.from_voice    = os.environ["TWILIO_VOICE_NUMBER"]

    async def send_sms(self, to: str, body: str) -> str:
        """Send SMS — returns message SID."""
        loop = asyncio.get_event_loop()
        message = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                body=body,
                from_=self.from_sms,
                to=to,
            )
        )
        logger.info(f"SMS sent to {to}: {message.sid}")
        return message.sid

    async def send_whatsapp(self, to: str, body: str) -> str:
        """Send WhatsApp message — returns message SID."""
        loop = asyncio.get_event_loop()
        to_wa = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
        message = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                body=body,
                from_=self.from_whatsapp,
                to=to_wa,
            )
        )
        logger.info(f"WhatsApp sent to {to}: {message.sid}")
        return message.sid

    async def make_call(
        self,
        to: str,
        twiml: str,
        machine_detection: str = "Enable",
        machine_detection_timeout: int = 8,
    ) -> str:
        """
        Place a voice call — returns call SID.
        machine_detection='Enable' detects voicemail vs human answer.
        """
        loop = asyncio.get_event_loop()
        call = await loop.run_in_executor(
            None,
            lambda: self.client.calls.create(
                twiml=twiml,
                from_=self.from_voice,
                to=to,
                machine_detection=machine_detection,
                machine_detection_timeout=machine_detection_timeout,
            )
        )
        logger.info(f"Call placed to {to}: {call.sid}")
        return call.sid


# ─────────────────────────────────────────
#  Google Maps Service
# ─────────────────────────────────────────
import httpx


class MapsService:
    """Google Maps Platform — GPS, Geocoding, Geolocation fallback."""

    GEOCODING_URL   = "https://maps.googleapis.com/maps/api/geocode/json"
    GEOLOCATION_URL = "https://www.googleapis.com/geolocation/v1/geolocate"

    def __init__(self):
        self.api_key = os.environ["GOOGLE_MAPS_API_KEY"]

    async def get_location(self, user_id: str) -> dict:
        """
        Get user's current location.
        Primary: GPS coordinates pushed from mobile app (stored in Firestore).
        Fallback: Google Geolocation API (cell tower / WiFi).
        """
        # Try GPS coordinates from mobile app first
        fs = FirestoreService()
        gps = await fs.get_latest_gps(user_id)

        if gps and gps.get("accuracy_meters", 999) < 50:
            # Accurate GPS available — reverse geocode for human address
            address = await self._reverse_geocode(gps["lat"], gps["lng"])
            return {**gps, "address": address}

        # Fallback: Geolocation API (cell towers + WiFi)
        logger.warning(f"[{user_id}] GPS inaccurate, using Geolocation API")
        return await self._geolocate_fallback()

    async def _reverse_geocode(self, lat: float, lng: float) -> str:
        """Convert GPS coordinates to human-readable address."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.GEOCODING_URL,
                params={
                    "latlng": f"{lat},{lng}",
                    "key": self.api_key,
                    "result_type": "street_address|sublocality",
                }
            )
            data = resp.json()
            if data.get("results"):
                return data["results"][0]["formatted_address"]
            return f"{lat:.5f}, {lng:.5f}"

    async def _geolocate_fallback(self) -> dict:
        """Use Google Geolocation API when GPS is unavailable."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.GEOLOCATION_URL}?key={self.api_key}",
                json={"considerIp": True},
            )
            data = resp.json()
            loc  = data.get("location", {})
            lat  = loc.get("lat", 0.0)
            lng  = loc.get("lng", 0.0)
            accuracy = data.get("accuracy", 999)
            address  = await self._reverse_geocode(lat, lng)
            return {
                "lat": lat,
                "lng": lng,
                "accuracy_meters": accuracy,
                "address": address,
                "source": "geolocation_api",
                "fallback": True,
            }


# ─────────────────────────────────────────
#  Firestore Service
# ─────────────────────────────────────────
from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient


class FirestoreService:
    """All Firestore operations for SafeVoice AI."""

    def __init__(self):
        self.db = firestore.AsyncClient(project=os.environ["GCP_PROJECT_ID"])

    # ── Users ──────────────────────────────
    async def create_user(self, user_data: dict):
        await self.db.collection("users").document(user_data["user_id"]).set(user_data)

    async def get_user(self, user_id: str) -> Optional[dict]:
        doc = await self.db.collection("users").document(user_id).get()
        return doc.to_dict() if doc.exists else None

    async def update_user(self, user_id: str, updates: dict):
        await self.db.collection("users").document(user_id).update(updates)

    # ── Contacts ──────────────────────────
    async def verify_contact(self, phone: str):
        """Mark a contact as verified after they reply YES."""
        users = await self.db.collection("users").get()
        for user_doc in users:
            user = user_doc.to_dict()
            contacts = user.get("emergency_contacts", [])
            updated  = False
            for contact in contacts:
                if contact["phone"] == phone and not contact.get("verified"):
                    contact["verified"] = True
                    updated = True
            if updated:
                await self.db.collection("users").document(user["user_id"]).update(
                    {"emergency_contacts": contacts}
                )
                break

    # ── Voice Baseline ─────────────────────
    async def save_voice_baseline(self, user_id: str, data: dict):
        await self.db.collection("voice_baselines").document(user_id).set(data)
        await self.update_user(user_id, {"voice_baseline_set": True})

    async def get_user_voice_baseline(self, user_id: str) -> Optional[dict]:
        doc = await self.db.collection("voice_baselines").document(user_id).get()
        return doc.to_dict() if doc.exists else None

    # ── GPS ───────────────────────────────
    async def save_gps(self, user_id: str, gps_data: dict):
        gps_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        await self.db.collection("gps_updates").add({**gps_data, "user_id": user_id})
        await self.db.collection("users").document(user_id).update(
            {"last_gps": gps_data}
        )

    async def get_latest_gps(self, user_id: str) -> Optional[dict]:
        user = await self.get_user(user_id)
        return user.get("last_gps") if user else None

    async def get_last_known_location(self, user_id: str) -> dict:
        gps = await self.get_latest_gps(user_id)
        if gps:
            return {**gps, "stale": True}
        return {"lat": 0.0, "lng": 0.0, "address": "Location unavailable", "stale": True}

    # ── Incidents ─────────────────────────
    async def create_incident(self, incident: dict) -> str:
        ref = self.db.collection("incidents").document(incident["incident_id"])
        await ref.set(incident)
        return f"incidents/{incident['incident_id']}"

    async def get_incidents(self, user_id: str) -> list:
        query = (
            self.db.collection("incidents")
            .where("user_id", "==", user_id)
            .order_by("triggered_at", direction=firestore.Query.DESCENDING)
            .limit(20)
        )
        docs = await query.get()
        return [doc.to_dict() for doc in docs]

    async def resolve_incident(self, incident_id: str):
        await self.db.collection("incidents").document(incident_id).update({
            "status":      "RESOLVED",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
