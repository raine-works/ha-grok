"""Text to speech support for xAI Grok."""

import asyncio
import base64
from collections.abc import AsyncGenerator, Mapping
import contextlib
import json
import re
from typing import Any

import aiohttp
from homeassistant.components.tts import (
    TextToSpeechEntity,
    TTSAudioRequest,
    TTSAudioResponse,
    TtsAudioType,
    Voice,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XaiConfigEntry
from .const import (
    CONF_TTS_LATENCY,
    CONF_TTS_SPEED,
    CONF_VOICE,
    DEFAULT_TTS_LATENCY,
    DEFAULT_TTS_SPEED,
    DEFAULT_VOICE,
    LOGGER,
)
from .entity import XaiBaseEntity

PARALLEL_UPDATES = 0

ATTR_VOICE = "voice"

# The model can stall on a slow tool call, during which no audio arrives
RECEIVE_TIMEOUT = 60

# Markdown the model may emit despite the prompt; it would be read out loud
_MARKUP = re.compile(r"[*#`]+")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: XaiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up TTS entities."""
    async_add_entities([XaiTTSEntity(config_entry)])


class XaiTTSEntity(TextToSpeechEntity, XaiBaseEntity):
    """xAI Grok TTS entity."""

    _attr_name = "Text to speech"
    _attr_supported_options = [ATTR_VOICE]
    # https://docs.x.ai/developers/model-capabilities/audio/text-to-speech
    # Every voice speaks every language; others work with varying accuracy
    _attr_supported_languages = [
        "en",
        "ar-EG",
        "ar-SA",
        "ar-AE",
        "bn",
        "zh",
        "fr",
        "de",
        "hi",
        "id",
        "it",
        "ja",
        "ko",
        "pt-BR",
        "pt-PT",
        "ru",
        "es-MX",
        "es-ES",
        "tr",
        "vi",
    ]
    _attr_default_language = "en"

    def __init__(self, entry: XaiConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_tts"
        self._attr_default_options = {
            ATTR_VOICE: entry.options.get(CONF_VOICE, DEFAULT_VOICE)
        }
        self._voices = [
            Voice(voice["voice_id"], voice["name"])
            for voice in entry.runtime_data.voices
        ]

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return a list of supported voices for a language."""
        return self._voices

    def _voice(self, options: Mapping[str, Any]) -> str:
        return options.get(ATTR_VOICE) or self.entry.options.get(
            CONF_VOICE, DEFAULT_VOICE
        )

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Load tts audio file from the engine."""
        data = await self.entry.runtime_data.async_tts(
            {
                "text": _MARKUP.sub("", message),
                "language": language,
                "voice_id": self._voice(options),
                "speed": self.entry.options.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED),
            }
        )
        return "mp3", data

    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Generate speech from an incoming message."""
        return TTSAudioResponse("mp3", self._async_stream_audio(request))

    async def _async_stream_audio(
        self, request: TTSAudioRequest
    ) -> AsyncGenerator[bytes]:
        """Forward text to xAI as it is generated and yield audio as it arrives.

        xAI decides where to cut the text for synthesis, so text is sent on
        as-is without waiting for sentence boundaries.
        """
        entry_options = self.entry.options
        ws = await self.entry.runtime_data.async_tts_connect(
            {
                "language": request.language,
                "voice": self._voice(request.options),
                "codec": "mp3",
                "speed": str(entry_options.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED)),
                "optimize_streaming_latency": str(
                    entry_options.get(CONF_TTS_LATENCY, DEFAULT_TTS_LATENCY)
                ),
            }
        )
        has_text = False
        nothing_to_say = False

        async def _send_text() -> None:
            nonlocal has_text, nothing_to_say
            async for chunk in request.message_gen:
                if not (text := _MARKUP.sub("", chunk)):
                    continue
                has_text = has_text or bool(text.strip())
                await ws.send_json({"type": "text.delta", "delta": text})
            if has_text:
                await ws.send_json({"type": "text.done"})
            else:
                # Nothing to say, so no audio.done will follow
                nothing_to_say = True
                await ws.close()

        send_task = self.hass.async_create_background_task(
            _send_text(), name="xai_grok_tts_send_text"
        )

        try:
            while True:
                try:
                    msg = await ws.receive(timeout=RECEIVE_TIMEOUT)
                except TimeoutError as err:
                    raise HomeAssistantError(
                        "Timed out waiting for audio from xAI"
                    ) from err

                if msg.type is aiohttp.WSMsgType.TEXT:
                    event = json.loads(msg.data)
                    if event["type"] == "audio.delta":
                        yield base64.b64decode(event["delta"])
                    elif event["type"] == "audio.done":
                        LOGGER.debug("Completed TTS stream: %s", event.get("trace_id"))
                        break
                    elif event["type"] == "error":
                        raise HomeAssistantError(
                            f"xAI TTS error: {event.get('message')}"
                        )
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    if nothing_to_say:
                        break
                    if (
                        send_task.done()
                        and not send_task.cancelled()
                        and (err := send_task.exception())
                    ):
                        raise HomeAssistantError(
                            f"Error sending text to xAI: {err}"
                        ) from err
                    raise HomeAssistantError(
                        "xAI closed the TTS connection before the audio was complete"
                    )
        finally:
            send_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await send_task
            await ws.close()
