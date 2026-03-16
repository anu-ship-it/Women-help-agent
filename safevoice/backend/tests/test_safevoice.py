"""
SafeVoice AI — Test Suite
Run with: pytest tests/ -v
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────
#  Tool Tests
# ─────────────────────────────────────────
class TestGetGpsLocation:
    @pytest.mark.asyncio
    async def test_returns_location_with_address(self):
        with patch("backend.services.all_services.MapsService.get_location") as mock:
            mock.return_value = {
                "lat": 28.6139, "lng": 77.2090,
                "accuracy_meters": 15,
                "address": "Connaught Place, New Delhi"
            }
            from backend.agent.tools import get_gps_location
            result = await get_gps_location("user_123")
            assert result["lat"] == 28.6139
            assert "address" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_last_known_on_failure(self):
        with patch("backend.services.all_services.MapsService.get_location",
                   side_effect=Exception("GPS unavailable")):
            with patch("backend.services.all_services.FirestoreService.get_last_known_location") as mock_fs:
                mock_fs.return_value = {"lat": 28.6, "lng": 77.2, "address": "Last known"}
                from backend.agent.tools import get_gps_location
                result = await get_gps_location("user_123")
                assert result["fallback"] is True


class TestSendEmergencySms:
    @pytest.mark.asyncio
    async def test_sends_to_all_verified_contacts(self):
        user_data = {
            "name": "Priya",
            "emergency_contacts": [
                {"phone": "+919876543210", "verified": True},
                {"phone": "+919876543211", "verified": True},
                {"phone": "+919876543212", "verified": False},  # Not verified — should skip
            ]
        }
        gps_data = {"lat": 28.6, "lng": 77.2, "address": "New Delhi"}

        with patch("backend.services.all_services.TwilioService.send_sms") as mock_sms:
            mock_sms.return_value = "SM_test_sid"
            from backend.agent.tools import send_emergency_sms
            result = await send_emergency_sms("user_123", user_data, gps_data, "INC-001")
            assert result["success_count"] == 2  # Only 2 verified contacts
            assert mock_sms.call_count == 2

    @pytest.mark.asyncio
    async def test_partial_failure_still_sends_to_others(self):
        user_data = {
            "name": "Priya",
            "emergency_contacts": [
                {"phone": "+919876543210", "verified": True},
                {"phone": "+919876543211", "verified": True},
            ]
        }
        gps_data = {"lat": 28.6, "lng": 77.2, "address": "New Delhi"}

        with patch("backend.services.all_services.TwilioService.send_sms",
                   side_effect=[Exception("Network error"), "SM_success"]):
            from backend.agent.tools import send_emergency_sms
            result = await send_emergency_sms("user_123", user_data, gps_data, "INC-001")
            assert result["success_count"] == 1
            assert len(result["failed"]) == 1


class TestCallHelpline:
    @pytest.mark.asyncio
    async def test_calls_helpline_with_twiml(self):
        user_data = {
            "name": "Priya",
            "emergency_recording_url": "https://storage.googleapis.com/test.wav"
        }
        gps_data = {"lat": 28.6, "lng": 77.2, "address": "New Delhi"}

        with patch("backend.services.all_services.TwilioService.make_call") as mock_call:
            mock_call.return_value = "CA_test_sid"
            from backend.agent.tools import call_helpline
            result = await call_helpline("user_123", user_data, gps_data, "INC-001")
            assert result["status"] == "calling"
            assert result["call_sid"] == "CA_test_sid"
            assert result["number"] == "181"

    @pytest.mark.asyncio
    async def test_escalates_to_112(self):
        user_data = {"name": "Priya", "emergency_recording_url": "https://test.wav"}
        gps_data  = {"lat": 28.6, "lng": 77.2, "address": "New Delhi"}

        with patch("backend.services.all_services.TwilioService.make_call") as mock_call:
            mock_call.return_value = "CA_police_sid"
            from backend.agent.tools import call_helpline
            result = await call_helpline("user_123", user_data, gps_data, "INC-001",
                                         emergency_number="112")
            assert result["number"] == "112"


# ─────────────────────────────────────────
#  Voice Verifier Tests
# ─────────────────────────────────────────
class TestVoiceVerifier:
    @pytest.mark.asyncio
    async def test_rejects_when_no_baseline(self):
        with patch("backend.services.all_services.FirestoreService.get_user_voice_baseline",
                   return_value=None):
            from backend.agent.voice_verify import VoiceVerifier
            verifier = VoiceVerifier("user_123")
            result   = await verifier.verify(b"\x00" * 16000)
            assert result["verified"] is False
            assert result["biometric_score"] == 0.0

    def test_stress_detection_returns_float(self):
        import numpy as np
        from backend.agent.voice_verify import VoiceVerifier

        verifier = VoiceVerifier("user_123")
        # Simulate stressed audio (high amplitude variation)
        audio = np.random.uniform(-0.8, 0.8, 16000).astype(np.float32)
        pcm   = (audio * 32768).astype(np.int16).tobytes()

        loop   = asyncio.get_event_loop()
        score  = loop.run_until_complete(verifier._detect_stress(pcm))
        assert 0.0 <= score <= 1.0

    def test_mfcc_returns_correct_length(self):
        from backend.agent.voice_verify import VoiceVerifier
        verifier  = VoiceVerifier("user_123")
        audio_pcm = bytes(16000 * 2)  # 1 second of silence
        features  = verifier._extract_mfcc(audio_pcm)
        assert len(features) == 40


# ─────────────────────────────────────────
#  Agent State Machine Tests
# ─────────────────────────────────────────
class TestAgentStateMachine:
    @pytest.mark.asyncio
    async def test_cancel_within_window_returns_to_idle(self):
        from backend.agent.agent import SafeVoiceLiveSession, AgentState

        session = SafeVoiceLiveSession("user_123", {"name": "Priya", "emergency_contacts": []})
        mock_ws = AsyncMock()

        # Simulate cancel being called within 3 seconds
        async def cancel_after_1s():
            await asyncio.sleep(0.1)
            await session.cancel_trigger()

        with patch.object(session, "_fire_emergency_response") as mock_fire:
            await asyncio.gather(
                session._on_keyword_detected(mock_ws),
                cancel_after_1s(),
            )
            mock_fire.assert_not_called()

        assert session.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_no_cancel_fires_emergency(self):
        from backend.agent.agent import SafeVoiceLiveSession, AgentState

        session = SafeVoiceLiveSession("user_123", {"name": "Priya", "emergency_contacts": []})
        mock_ws = AsyncMock()

        with patch.object(session, "_fire_emergency_response") as mock_fire:
            mock_fire.return_value = None
            # Don't cancel — let the 3s window expire
            await session._on_keyword_detected(mock_ws)
            mock_fire.assert_called_once()


# ─────────────────────────────────────────
#  Integration Test — Full Flow
# ─────────────────────────────────────────
class TestFullEmergencyFlow:
    @pytest.mark.asyncio
    async def test_complete_trigger_to_response(self):
        """
        End-to-end test: keyword detected → parallel tools fire → all contacts notified.
        Uses mocked external services (Twilio, Maps, Firestore).
        """
        from backend.agent.agent import SafeVoiceLiveSession, AgentState

        user_data = {
            "name": "Priya",
            "emergency_recording_url": "https://test.wav",
            "emergency_contacts": [
                {"name": "Mom", "phone": "+919876543210", "verified": True},
                {"name": "Friend", "phone": "+919876543211", "verified": True},
            ]
        }

        session = SafeVoiceLiveSession("user_123", user_data)
        mock_ws = AsyncMock()

        with patch("backend.agent.tools.get_gps_location",
                   return_value={"lat": 28.6, "lng": 77.2, "address": "New Delhi", "accuracy_meters": 10}), \
             patch("backend.agent.tools.send_emergency_sms",
                   return_value={"success_count": 2}), \
             patch("backend.agent.tools.call_helpline",
                   return_value={"status": "calling"}), \
             patch("backend.agent.tools.notify_emergency_contacts",
                   return_value={"status": "notified"}), \
             patch("backend.agent.tools.log_incident_to_firestore",
                   return_value={"incident_id": "INC-001"}):

            await session._fire_emergency_response(mock_ws)

        assert session.state == AgentState.ACTIVE
        assert session.incident_id is not None

        # Verify correct WebSocket events were sent
        events_sent = [call.args[0]["event"] for call in mock_ws.send_json.call_args_list]
        assert "EMERGENCY_ACTIVE"    in events_sent
        assert "RESPONSE_DISPATCHED" in events_sent
