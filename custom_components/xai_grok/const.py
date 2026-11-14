"""Constants for the xAI Grok integration."""

import logging

DOMAIN = "xai_grok"
LOGGER = logging.getLogger(__package__)

API_BASE = "https://api.x.ai/v1"
WS_BASE = "wss://api.x.ai/v1"

CONF_CHAT_MODEL = "chat_model"
CONF_REASONING_EFFORT = "reasoning_effort"
CONF_WEB_SEARCH = "web_search"
CONF_X_SEARCH = "x_search"
CONF_VOICE = "voice"
CONF_TTS_SPEED = "tts_speed"
CONF_TTS_LATENCY = "tts_latency"

# Non-reasoning models start answering soonest, which matters most for voice.
DEFAULT_CHAT_MODEL = "grok-4.20-0309-non-reasoning"
DEFAULT_REASONING_EFFORT = "low"
IMAGE_MODEL = "grok-imagine-image-2.0"
DEFAULT_VOICE = "eve"
DEFAULT_TTS_SPEED = 1.0
DEFAULT_TTS_LATENCY = "1"

FALLBACK_CHAT_MODELS = [DEFAULT_CHAT_MODEL, "grok-4.7", "grok-4.3"]
FALLBACK_VOICES = [{"voice_id": DEFAULT_VOICE, "name": "Eve"}]
