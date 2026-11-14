"""Speech to text support for xAI Grok."""

from collections.abc import AsyncIterable
import json

import aiohttp

from homeassistant.components import stt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XaiConfigEntry
from .client import XaiError
from .const import LOGGER
from .entity import XaiBaseEntity

PARALLEL_UPDATES = 0

RECEIVE_TIMEOUT = 15

# Languages for which xAI can write numbers, currency and units as digits
FORMAT_LANGUAGES = {"ar", "zh", "en", "fr", "de", "ja", "pt", "ru", "es", "sv", "vi"}

# Regional codes xAI accepts as-is; everything else is sent as the base code
REGIONAL_LANGUAGES = {"es-ES", "pt-PT", "ar-AE", "ar-SA"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: XaiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up STT entities."""
    async_add_entities([XaiSTTEntity(config_entry)])


class XaiSTTEntity(stt.SpeechToTextEntity, XaiBaseEntity):
    """xAI Grok speech to text entity."""

    _attr_name = "Speech to text"

    def __init__(self, entry: XaiConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_stt"

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        # https://docs.x.ai/developers/model-capabilities/audio/speech-to-text
        return [
            "ar",
            "ar-AE",
            "ar-SA",
            "bs",
            "bg",
            "yue",
            "ca",
            "zh",
            "hr",
            "cs",
            "da",
            "nl",
            "en",
            "fil",
            "fi",
            "fr",
            "de",
            "el",
            "hi",
            "hu",
            "id",
            "it",
            "ja",
            "ko",
            "mk",
            "ms",
            "nb",
            "fa",
            "pl",
            "pt",
            "pt-PT",
            "ro",
            "ru",
            "sk",
            "es",
            "es-ES",
            "sv",
            "th",
            "tr",
            "uk",
            "ur",
            "vi",
        ]

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return a list of supported formats."""
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return a list of supported codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return a list of supported bit rates."""
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return a list of supported sample rates."""
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return a list of supported channels."""
        return [stt.AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Transcribe audio while it is still being recorded.

        Audio goes to xAI as it arrives, so the transcript is ready almost as
        soon as the speaker stops instead of after an upload.
        """
        language = metadata.language
        if language not in REGIONAL_LANGUAGES:
            language = language.split("-")[0]
        params = {
            "sample_rate": str(metadata.sample_rate.value),
            "encoding": "pcm",
            "language": language,
        }
        if language.split("-")[0] in FORMAT_LANGUAGES:
            params["format"] = "true"

        try:
            ws = await self.entry.runtime_data.async_stt_connect(params)
        except XaiError:
            LOGGER.exception("Error connecting to xAI STT")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        try:
            text = await self._async_transcribe(ws, stream)
        except (aiohttp.ClientError, TimeoutError, XaiError):
            LOGGER.exception("Error during STT")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        finally:
            await ws.close()

        return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)

    async def _async_transcribe(
        self, ws: aiohttp.ClientWebSocketResponse, stream: AsyncIterable[bytes]
    ) -> str:
        """Send the audio stream and return the final transcript."""
        finals: list[str] = []

        async def _next_event() -> dict:
            msg = await ws.receive(timeout=RECEIVE_TIMEOUT)
            if msg.type is not aiohttp.WSMsgType.TEXT:
                raise XaiError("xAI closed the STT connection unexpectedly")
            event = json.loads(msg.data)
            if event["type"] == "error":
                raise XaiError(f"xAI STT error: {event.get('message')}")
            return event

        # The server needs to be ready before it accepts audio
        while (await _next_event())["type"] != "transcript.created":
            pass

        async for chunk in stream:
            if chunk:
                await ws.send_bytes(chunk)
        await ws.send_json({"type": "audio.done"})

        while True:
            event = await _next_event()
            if event["type"] == "transcript.done":
                return (event.get("text") or " ".join(finals)).strip()
            if event["type"] == "transcript.partial" and event.get("is_final"):
                finals.append(event.get("text", ""))
