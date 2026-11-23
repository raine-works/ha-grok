"""Constants for the xAI Grok integration."""

import logging

#: The integration's domain, as in `manifest.json`.
DOMAIN = "xai_grok"
#: The integration's logger.
LOGGER = logging.getLogger(__package__)

#: Base URL of xAI's REST API (models, voices, chat responses, text to speech and
#: images).
API_BASE = "https://api.x.ai/v1"
#: Base URL of xAI's WebSocket API, used for streaming speech to text and text to
#: speech.
WS_BASE = "wss://api.x.ai/v1"

#: Option key: the chat model used by the conversation agent and AI Task.
CONF_CHAT_MODEL = "chat_model"
#: Option key: reasoning effort ("low", "medium" or "high"), sent only to models
#: that support it.
CONF_REASONING_EFFORT = "reasoning_effort"
#: Option key: whether Grok may search the web while answering.
CONF_WEB_SEARCH = "web_search"
#: Option key: whether Grok may search X while answering.
CONF_X_SEARCH = "x_search"
#: Option key: the text to speech voice's `voice_id`.
CONF_VOICE = "voice"
#: Option key: the text to speech speed, a multiplier of normal speed.
CONF_TTS_SPEED = "tts_speed"
#: Option key: xAI's `optimize_streaming_latency` level for streaming speech, as a
#: string: "0" is off (best quality), "1" balanced and "2" fastest.
CONF_TTS_LATENCY = "tts_latency"

#: The chat model used until another is chosen in the options. Non-reasoning
#: models start answering soonest, which matters most for voice.
DEFAULT_CHAT_MODEL = "grok-4.20-0309-non-reasoning"
#: Reasoning effort used until another is chosen in the options.
DEFAULT_REASONING_EFFORT = "low"
#: The model AI Task uses to generate images.
IMAGE_MODEL = "grok-imagine-image-2.0"
#: The text to speech voice used until another is chosen.
DEFAULT_VOICE = "eve"
#: Normal speaking speed (1.0 times).
DEFAULT_TTS_SPEED = 1.0
#: The default streaming latency level, "1": balanced (see `CONF_TTS_LATENCY`).
DEFAULT_TTS_LATENCY = "1"

#: Chat models offered in the options when xAI's model list isn't available (the
#: entry isn't loaded, for example with a revoked key, or the list came back
#: empty).
FALLBACK_CHAT_MODELS = [DEFAULT_CHAT_MODEL, "grok-4.7", "grok-4.3"]
#: Voices used when xAI's voice list can't be fetched or is empty (keys without
#: Voice access get none), so text to speech still has a voice to offer.
FALLBACK_VOICES = [{"voice_id": DEFAULT_VOICE, "name": "Eve"}]
