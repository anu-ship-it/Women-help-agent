/**
 * SafeVoice AI — React Native Background Service
 * Always-on keyword listener + WebSocket manager
 * Works on iOS (Background Audio) and Android (ForegroundService)
 */

import { Platform, AppState, NativeModules } from 'react-native';
import * as TaskManager from 'expo-task-manager';
import * as BackgroundFetch from 'expo-background-fetch';
import * as Notifications from 'expo-notifications';
import { Audio } from 'expo-av';
import AsyncStorage from '@react-native-async-storage/async-storage';

const BACKGROUND_TASK = 'SAFEVOICE_LISTENER';
const WS_URL          = process.env.EXPO_PUBLIC_BACKEND_WS_URL; // wss://safevoice-xxx.run.app

// ─────────────────────────────────────────
//  WebSocket Manager (singleton)
// ─────────────────────────────────────────
class WebSocketManager {
  constructor() {
    this.ws           = null;
    this.userId       = null;
    this.reconnectMs  = 1000;   // Exponential backoff start
    this.maxReconnect = 30000;  // Cap at 30s
    this.listeners    = {};
    this.isConnecting = false;
  }

  async connect(userId) {
    this.userId = userId;
    if (this.isConnecting || this.ws?.readyState === WebSocket.OPEN) return;

    this.isConnecting = true;
    console.log(`[SafeVoice] Connecting to ${WS_URL}/ws/stream/${userId}`);

    this.ws = new WebSocket(`${WS_URL}/ws/stream/${userId}`);

    this.ws.onopen = () => {
      console.log('[SafeVoice] WebSocket connected');
      this.reconnectMs = 1000; // Reset backoff on successful connect
      this.isConnecting = false;
      this._emit('connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log(`[SafeVoice] Event: ${data.event}`);
        this._emit(data.event, data);
        this._emit('message', data);
      } catch (e) {
        console.error('[SafeVoice] Message parse error:', e);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[SafeVoice] WebSocket error:', error.message);
      this.isConnecting = false;
    };

    this.ws.onclose = () => {
      console.log('[SafeVoice] WebSocket closed — reconnecting...');
      this.isConnecting = false;
      this._scheduleReconnect();
    };
  }

  sendAudio(pcmBytes) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(pcmBytes);
    }
  }

  sendAction(action, payload = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...payload }));
    }
  }

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
    return () => {  // Returns unsubscribe function
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    };
  }

  _emit(event, data) {
    (this.listeners[event] || []).forEach(cb => cb(data));
  }

  _scheduleReconnect() {
    setTimeout(() => {
      if (this.userId) this.connect(this.userId);
    }, this.reconnectMs);

    // Exponential backoff
    this.reconnectMs = Math.min(this.reconnectMs * 2, this.maxReconnect);
  }

  disconnect() {
    this.userId = null;
    this.ws?.close();
    this.ws = null;
  }
}

export const wsManager = new WebSocketManager();


// ─────────────────────────────────────────
//  Audio Recorder (streams PCM to WebSocket)
// ─────────────────────────────────────────
class AudioStreamService {
  constructor() {
    this.recording    = null;
    this.isStreaming  = false;
    this.chunkInterval = null;
  }

  async requestPermissions() {
    const { status } = await Audio.requestPermissionsAsync();
    if (status !== 'granted') {
      throw new Error('Microphone permission denied');
    }
  }

  async startStreaming() {
    if (this.isStreaming) return;

    await Audio.setAudioModeAsync({
      allowsRecordingIOS:               true,
      playsInSilentModeIOS:             true,
      // Critical for iOS background audio
      staysActiveInBackground:          true,
      interruptionModeIOS:              Audio.INTERRUPTION_MODE_IOS_DO_NOT_MIX,
      interruptionModeAndroid:          Audio.INTERRUPTION_MODE_ANDROID_DO_NOT_MIX,
    });

    // PCM 16kHz mono — what Gemini Live API expects
    this.recording = new Audio.Recording();
    await this.recording.prepareToRecordAsync({
      android: {
        extension:       '.pcm',
        outputFormat:    Audio.RECORDING_OPTION_ANDROID_OUTPUT_FORMAT_DEFAULT,
        audioEncoder:    Audio.RECORDING_OPTION_ANDROID_AUDIO_ENCODER_DEFAULT,
        sampleRate:      16000,
        numberOfChannels: 1,
        bitRate:         128000,
      },
      ios: {
        extension:       '.pcm',
        audioQuality:    Audio.RECORDING_OPTION_IOS_AUDIO_QUALITY_HIGH,
        sampleRate:      16000,
        numberOfChannels: 1,
        bitRate:         128000,
        linearPCMBitDepth: 16,
        linearPCMIsBigEndian: false,
        linearPCMIsFloat:    false,
      },
    });

    await this.recording.startAsync();
    this.isStreaming = true;

    // Stream audio chunks every 100ms
    this.chunkInterval = setInterval(() => this._sendChunk(), 100);
    console.log('[SafeVoice] Audio streaming started');
  }

  async _sendChunk() {
    try {
      if (!this.recording || !this.isStreaming) return;
      const status = await this.recording.getStatusAsync();
      if (!status.isRecording) return;

      // Get raw PCM data and send to WebSocket
      const uri  = this.recording.getURI();
      const data = await fetch(uri).then(r => r.arrayBuffer());
      wsManager.sendAudio(data);
    } catch (e) {
      // Silently ignore chunk errors — don't interrupt the stream
    }
  }

  async stopStreaming() {
    if (!this.isStreaming) return;
    clearInterval(this.chunkInterval);
    this.isStreaming = false;
    try {
      await this.recording?.stopAndUnloadAsync();
    } catch (e) { /* ignore */ }
    this.recording = null;
    console.log('[SafeVoice] Audio streaming stopped');
  }
}

export const audioService = new AudioStreamService();


// ─────────────────────────────────────────
//  Accelerometer — Panic Shake Detection
// ─────────────────────────────────────────
import { Accelerometer } from 'expo-sensors';

class ShakeDetector {
  constructor() {
    this.threshold    = 2.5;   // G-force threshold
    this.shakeCount   = 0;
    this.lastShakeAt  = 0;
    this.windowMs     = 1500;  // 1.5 seconds window for 3 shakes
    this.subscription = null;
    this.onShake      = null;
  }

  start(onShake) {
    this.onShake = onShake;
    Accelerometer.setUpdateInterval(100);  // 10Hz

    this.subscription = Accelerometer.addListener(({ x, y, z }) => {
      const acceleration = Math.sqrt(x * x + y * y + z * z);

      if (acceleration > this.threshold) {
        const now = Date.now();

        if (now - this.lastShakeAt > 300) {  // Debounce 300ms between shakes
          this.shakeCount++;
          this.lastShakeAt = now;

          if (this.shakeCount === 3) {
            this.shakeCount = 0;
            console.log('[SafeVoice] Panic shake detected!');
            this.onShake?.();
          }

          // Reset count if 3 shakes not completed in time window
          setTimeout(() => {
            if (Date.now() - this.lastShakeAt > this.windowMs) {
              this.shakeCount = 0;
            }
          }, this.windowMs);
        }
      }
    });
  }

  stop() {
    this.subscription?.remove();
    this.subscription = null;
  }
}

export const shakeDetector = new ShakeDetector();


// ─────────────────────────────────────────
//  Power Button Detector (Android only)
// ─────────────────────────────────────────
export function setupPowerButtonTrigger(onTriplePressAndroid) {
  if (Platform.OS !== 'android') return () => {};

  let pressCount = 0;
  let lastPressAt = 0;

  const subscription = AppState.addEventListener('change', (nextState) => {
    if (nextState === 'inactive' || nextState === 'background') {
      const now = Date.now();
      if (now - lastPressAt < 600) {
        pressCount++;
        if (pressCount >= 3) {
          pressCount = 0;
          console.log('[SafeVoice] Triple power button press detected!');
          onTriplePressAndroid();
        }
      } else {
        pressCount = 1;
      }
      lastPressAt = now;
    }
  });

  return () => subscription.remove();
}


// ─────────────────────────────────────────
//  Background Task (Expo TaskManager)
//  Keeps the listener alive when app is in background
// ─────────────────────────────────────────
TaskManager.defineTask(BACKGROUND_TASK, async () => {
  try {
    const userId = await AsyncStorage.getItem('safevoice_user_id');
    if (!userId) return BackgroundFetch.BackgroundFetchResult.NoData;

    // Reconnect WebSocket if needed
    if (!wsManager.ws || wsManager.ws.readyState !== WebSocket.OPEN) {
      await wsManager.connect(userId);
    }

    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch (e) {
    console.error('[SafeVoice] Background task error:', e);
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundTask() {
  try {
    await BackgroundFetch.registerTaskAsync(BACKGROUND_TASK, {
      minimumInterval: 15,          // Every 15 seconds minimum (iOS limit)
      stopOnTerminate:  false,       // Keep running when app is terminated
      startOnBoot:      true,        // Restart after device reboot
    });
    console.log('[SafeVoice] Background task registered');
  } catch (e) {
    console.error('[SafeVoice] Background task registration failed:', e);
  }
}


// ─────────────────────────────────────────
//  Emergency Notifications (shown while agent is active)
// ─────────────────────────────────────────
export async function showEmergencyNotification(incidentId) {
  await Notifications.scheduleNotificationAsync({
    content: {
      title:    '🛡️ SafeVoice Active',
      body:     'Emergency response in progress. Tap to view status.',
      data:     { incidentId },
      priority: Notifications.AndroidNotificationPriority.MAX,
      sticky:   true,      // Cannot be dismissed — stays visible
    },
    trigger: null,  // Show immediately
  });
}

export async function dismissEmergencyNotification() {
  await Notifications.dismissAllNotificationsAsync();
}


// ─────────────────────────────────────────
//  Main SafeVoice Service (coordinates everything)
// ─────────────────────────────────────────
class SafeVoiceService {
  constructor() {
    this.userId    = null;
    this.callbacks = {};
    this._cleanupFns = [];
  }

  async initialize(userId) {
    this.userId = userId;
    await AsyncStorage.setItem('safevoice_user_id', userId);

    // 1. Request permissions
    await audioService.requestPermissions();

    // 2. Connect WebSocket
    await wsManager.connect(userId);

    // 3. Start audio stream
    await audioService.startStreaming();

    // 4. Start shake detector
    shakeDetector.start(() => this._onSilentTrigger());

    // 5. Power button (Android)
    const cleanupPower = setupPowerButtonTrigger(() => this._onSilentTrigger());
    this._cleanupFns.push(cleanupPower);

    // 6. Register background task
    await registerBackgroundTask();

    // 7. Listen for agent events
    const cleanupWS = wsManager.on('message', (data) => this._onAgentEvent(data));
    this._cleanupFns.push(cleanupWS);

    console.log(`[SafeVoice] Service initialized for user: ${userId}`);
  }

  _onSilentTrigger() {
    wsManager.sendAction('silent_trigger');
  }

  cancelTrigger() {
    wsManager.sendAction('cancel');
  }

  confirmSafe() {
    wsManager.sendAction('safe_confirmed');
    dismissEmergencyNotification();
  }

  async _onAgentEvent(event) {
    switch (event.event) {
      case 'KEYWORD_DETECTED':
        this.callbacks.onKeywordDetected?.(event);
        break;

      case 'EMERGENCY_ACTIVE':
        await showEmergencyNotification(event.incident_id);
        this.callbacks.onEmergencyActive?.(event);
        break;

      case 'GPS_UPDATE':
        this.callbacks.onGpsUpdate?.(event);
        break;

      case 'SAFETY_CHECKIN':
        this.callbacks.onSafetyCheckin?.(event);
        break;

      case 'RESOLVED':
        await dismissEmergencyNotification();
        this.callbacks.onResolved?.(event);
        break;

      case 'POLICE_CONTACTED':
        this.callbacks.onPoliceContacted?.(event);
        break;
    }
  }

  on(event, callback) {
    this.callbacks[event] = callback;
  }

  async destroy() {
    await audioService.stopStreaming();
    shakeDetector.stop();
    wsManager.disconnect();
    this._cleanupFns.forEach(fn => fn());
    await AsyncStorage.removeItem('safevoice_user_id');
  }
}

export const safevoiceService = new SafeVoiceService();

