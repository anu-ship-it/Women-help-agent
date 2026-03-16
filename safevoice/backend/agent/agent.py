"""
SafeVoice AI — ADK Bidi-Streaming Agent
Core state machine + tool orchestrator
Runs on Google Cloud Run
"""

import asyncio
import logging
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import (
    LiveConnectConfig,
    SpeechConfig,
    VoiceActivityDetection,

)

from .tools import (
    get_gps_location,
    send_emergency_sms,
    call_helpline,
    notify_emergency_contacts,
    log_incident_to_firestore,
)
from .voice_verify import VoiceVerifier

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  Agent State Machine
# ─────────────────────────────────────────
class AgentState(str, Enum):
    IDLE      = "IDLE"       # Standby — keyword spotter running on-device
    TRIGGERED = "TRIGGERED"  # "Help Me" confirmed — 3s cancel window open
    ACTIVE    = "ACTIVE"     # Emergency response in progress
    RESOLVED  = "RESOLVED"   # User confirmed safe / escalated to police


# ─────────────────────────────────────────
#  SafeVoice Agent Definition
# ─────────────────────────────────────────
SYSTEM_PROMPT = """
You are SafeVoice, an emergency response AI agent for women's safety.

Your ONLY job is to protect the user when they are in danger.

When triggered (state = TRIGGERED):
1. Immediately call get_gps_location to capture current position
2. Call all 4 response tools in parallel using your tool execution
3. Track the state and report back to the mobile app

You are NOT a chatbot. You do not hold conversations.
You execute emergency protocols silently and efficiently.
Never ask the user clarifying questions during an active emergency.
"""

safevoice_agent = Agent(
    name="safevoice_emergency_agent",
    model="gemini-2.0-flash-live-001",
    description="Women's emergency safety agent — voice-triggered parallel response",
    instruction=SYSTEM_PROMPT,
    tools=[
        get_gps_location,
        send_emergency_sms,
        call_helpline,
        notify_emergency_contacts,
        log_incident_to_firestore,
    ],
)

# ADK session service (in-memory per Cloud Run instance)
session_service = InMemorySessionService()

# ADK runner
runner = Runner(
    agent=safevoice_agent,
    app_name="safevoice",
    session_service=session_service,
)


# ─────────────────────────────────────────
#  Live Session Manager
# ─────────────────────────────────────────
class SafeVoiceLiveSession:
    """
    Manages a single user's Gemini Live API session.
    One instance per connected mobile client.
    """

    def __init__(self, user_id: str, user_data: dict):
        self.user_id    = user_id
        self.user_data  = user_data  # contacts, name, recorded_voice_url
        self.state      = AgentState.IDLE
        self.incident_id: Optional[str] = None
        self.session    = None
        self.verifier   = VoiceVerifier(user_id)
        self._cancel_event = asyncio.Event()
        self._response_task: Optional[asyncio.Task] = None

    async def start(self, websocket):
        """Entry point — called when mobile app connects via WebSocket."""
        client = genai.Client()

        config = LiveConnectConfig(
            response_modalities=["TEXT"],
            speech_config=SpeechConfig(
                voice_activity_detection=VoiceActivityDetection(
                    start_of_speech_sensitivity="HIGH",
                    end_of_speech_sensitivity="HIGH",
                )
            ),
            system_instruction=SYSTEM_PROMPT,
        )

        logger.info(f"[{self.user_id}] Live session started — state: IDLE")

        async with client.aio.live.connect(
            model="gemini-2.0-flash-live-001",
            config=config,
        ) as gemini_session:
            self.session = gemini_session
            await self._listen_loop(websocket, gemini_session)

    async def _listen_loop(self, websocket, gemini_session):
        """
        Main loop — receives audio chunks from mobile app,
        streams them to Gemini Live API, handles responses.
        """
        async for message in websocket.iter_bytes():
            if self.state == AgentState.IDLE:
                # Forward raw PCM audio to Gemini Live API
                await gemini_session.send(
                    input={"mime_type": "audio/pcm", "data": message},
                    end_of_turn=False,
                )

            # Read any responses from Gemini
            async for response in gemini_session.receive():
                await self._handle_gemini_response(response, websocket)

    async def _handle_gemini_response(self, response, websocket):
        """Process responses from Gemini Live API."""

        # Keyword detected by Gemini
        if hasattr(response, "text") and response.text:
            text = response.text.lower()
            if "help me" in text and self.state == AgentState.IDLE:
                await self._on_keyword_detected(websocket)

        # Tool calls from ADK agent
        if hasattr(response, "tool_call") and response.tool_call:
            logger.info(f"[{self.user_id}] Tool call: {response.tool_call.name}")

    async def _on_keyword_detected(self, websocket):
        """
        Called the moment 'Help Me' is detected.
        Opens a 3-second cancel window via Gemini Live API barge-in.
        """
        logger.info(f"[{self.user_id}] Keyword detected — opening cancel window")

        # Notify mobile app to show cancel UI
        await websocket.send_json({
            "event": "KEYWORD_DETECTED",
            "cancel_window_seconds": 3,
        })

        self.state = AgentState.TRIGGERED
        self._cancel_event.clear()

        # Wait 3 seconds — Gemini's barge-in handles the "Cancel" word natively
        try:
            await asyncio.wait_for(
                self._cancel_event.wait(),
                timeout=3.0,
            )
            # Cancel was called — return to IDLE
            self.state = AgentState.IDLE
            await websocket.send_json({"event": "CANCELLED"})
            logger.info(f"[{self.user_id}] Trigger cancelled by user")

        except asyncio.TimeoutError:
            # 3 seconds passed, no cancel — FIRE
            await self._fire_emergency_response(websocket)

    async def cancel_trigger(self):
        """Called when user says 'Cancel' or presses cancel button."""
        if self.state == AgentState.TRIGGERED:
            self._cancel_event.set()

    async def _fire_emergency_response(self, websocket):
        """
        Core emergency response — all 5 tools run in PARALLEL.
        This is the heart of SafeVoice AI.
        """
        self.state = AgentState.ACTIVE
        self.incident_id = f"INC-{self.user_id}-{int(datetime.now().timestamp())}"

        logger.info(f"[{self.user_id}] EMERGENCY TRIGGERED — incident: {self.incident_id}")

        await websocket.send_json({
            "event": "EMERGENCY_ACTIVE",
            "incident_id": self.incident_id,
        })

        # Step 1: Get GPS immediately (needed by all other tools)
        gps_data = await get_gps_location(user_id=self.user_id)
        logger.info(f"[{self.user_id}] GPS captured: {gps_data}")

        # Step 2: Fire ALL response tools in PARALLEL — asyncio.gather is the key
        results = await asyncio.gather(
            send_emergency_sms(
                user_id=self.user_id,
                user_data=self.user_data,
                gps_data=gps_data,
                incident_id=self.incident_id,
            ),
            call_helpline(
                user_id=self.user_id,
                user_data=self.user_data,
                gps_data=gps_data,
                incident_id=self.incident_id,
            ),
            notify_emergency_contacts(
                user_id=self.user_id,
                user_data=self.user_data,
                gps_data=gps_data,
                incident_id=self.incident_id,
            ),
            log_incident_to_firestore(
                user_id=self.user_id,
                user_data=self.user_data,
                gps_data=gps_data,
                incident_id=self.incident_id,
            ),
            return_exceptions=True,  # Don't let one failure block others
        )

        # Log any individual tool failures — agent keeps running
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{self.user_id}] Tool {i} failed: {result}")

        await websocket.send_json({
            "event": "RESPONSE_DISPATCHED",
            "incident_id": self.incident_id,
            "gps": gps_data,
        })

        # Start safety check-in timer (30 minutes)
        self._response_task = asyncio.create_task(
            self._safety_checkin_loop(websocket)
        )

    async def _safety_checkin_loop(self, websocket):
        """
        After 30 minutes, ask user if they are safe.
        If no response in 5 minutes, escalate to police (112).
        """
        # Send live GPS updates every 60 seconds
        for _ in range(30):
            await asyncio.sleep(60)
            if self.state != AgentState.ACTIVE:
                return
            gps_data = await get_gps_location(user_id=self.user_id)
            await websocket.send_json({"event": "GPS_UPDATE", "gps": gps_data})
            # Push updated location to contacts
            await notify_emergency_contacts(
                user_id=self.user_id,
                user_data=self.user_data,
                gps_data=gps_data,
                incident_id=self.incident_id,
                update_only=True,
            )

        # 30 minutes passed — send safety check-in
        await websocket.send_json({"event": "SAFETY_CHECKIN"})
        logger.info(f"[{self.user_id}] Safety check-in sent")

        # Wait 5 minutes for user to confirm safety
        try:
            await asyncio.wait_for(
                self._wait_for_safe_confirmation(),
                timeout=300.0,  # 5 minutes
            )
        except asyncio.TimeoutError:
            # No response — escalate to police
            logger.warning(f"[{self.user_id}] No safety confirmation — escalating to 112")
            await self._escalate_to_police(websocket)

    async def _wait_for_safe_confirmation(self):
        """Blocks until confirm_safe() is called by the API."""
        while self.state == AgentState.ACTIVE:
            await asyncio.sleep(1)

    async def confirm_safe(self, websocket):
        """Called when user confirms they are safe."""
        self.state = AgentState.RESOLVED
        logger.info(f"[{self.user_id}] User confirmed safe — incident resolved")

        # Notify all contacts that user is safe
        await notify_emergency_contacts(
            user_id=self.user_id,
            user_data=self.user_data,
            gps_data=None,
            incident_id=self.incident_id,
            all_clear=True,
        )

        await websocket.send_json({"event": "RESOLVED", "incident_id": self.incident_id})

    async def _escalate_to_police(self, websocket):
        """Last resort — call emergency services (112)."""
        gps_data = await get_gps_location(user_id=self.user_id)

        await call_helpline(
            user_id=self.user_id,
            user_data=self.user_data,
            gps_data=gps_data,
            incident_id=self.incident_id,
            emergency_number="112",
        )

        await websocket.send_json({
            "event": "POLICE_CONTACTED",
            "incident_id": self.incident_id,
        })
