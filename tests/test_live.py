"""Live checks against the real xAI API.

Skipped unless XAI_API_KEY is set in the environment or in the .env file at
the repository root. Run with:

    python -m pytest tests/test_live.py -s

Each run costs a fraction of a cent.
"""

import asyncio
from collections.abc import AsyncGenerator
import os
from pathlib import Path
import socket
import struct
import time
from unittest.mock import patch
import zlib

from aiohttp.resolver import ThreadedResolver
from homeassistant.components import ai_task, conversation, media_source, stt
from homeassistant.components.tts import TTSAudioRequest
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import chat_session, entity_registry as er, llm
import probatio as vol
import pytest
from pytest_homeassistant_custom_component import plugins as ha_plugins
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest_socket

from custom_components.xai_grok.config_flow import DEFAULT_OPTIONS
from custom_components.xai_grok.const import CONF_CHAT_MODEL, CONF_WEB_SEARCH, DOMAIN


def _api_key() -> str | None:
    if key := os.environ.get("XAI_API_KEY"):
        return key
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "XAI_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    return None


API_KEY = _api_key()

pytestmark = pytest.mark.skipif(API_KEY is None, reason="XAI_API_KEY is not set")

MODELS = [DEFAULT_OPTIONS[CONF_CHAT_MODEL], "grok-4.7"]


class EchoTool(llm.Tool):
    """Tool that records and returns its input."""

    name = "echo"
    description = "Echo the given text back. Use it whenever asked to echo."
    parameters = vol.Schema({vol.Required("text"): str})
    calls: list[str] = []

    async def async_call(self, hass, tool_input, llm_context):
        """Call the tool."""
        self.calls.append(tool_input.tool_args["text"])
        return llm.ToolResult(data={"echoed": tool_input.tool_args["text"]})


class EchoAPI(llm.API):
    """LLM API exposing the echo tool."""

    async def async_get_api_instance(self, llm_context):
        """Return the instance."""
        return llm.APIInstance(
            api=self, api_prompt="", llm_context=llm_context, tools=[EchoTool()]
        )


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Real TLS connections leave shutdown timers behind when a test ends."""
    return True


def _make_resolver(*args) -> ThreadedResolver:
    """Return a resolver that does real DNS, which the test plugin disables."""
    resolver = ThreadedResolver()
    resolver.real_close = resolver.close
    return resolver


@pytest.fixture
async def live_entry(
    hass: HomeAssistant, socket_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> MockConfigEntry:
    """Set up the integration against the real API."""
    # The Home Assistant test plugin only allows connections to localhost
    monkeypatch.setattr(socket.socket, "connect", pytest_socket._true_connect)
    monkeypatch.setattr(socket, "getaddrinfo", ha_plugins._real_getaddrinfo)
    monkeypatch.setattr(
        "homeassistant.helpers.aiohttp_client._async_make_resolver", _make_resolver
    )
    llm.async_register_api(hass, EchoAPI(hass=hass, id="echo_api", name="Echo"))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Grok",
        data={CONF_API_KEY: API_KEY},
        options={**DEFAULT_OPTIONS, CONF_LLM_HASS_API: ["echo_api"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, platform: str, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return hass.data[platform].get_entity(entity_id)


async def test_models_and_voices(hass: HomeAssistant, live_entry) -> None:
    """The account lists the models and voices the integration relies on."""
    client = live_entry.runtime_data
    print(f"\nmodels: {client.models}")
    print(f"voices: {[voice['voice_id'] for voice in client.voices]}")
    for model in MODELS:
        assert model in client.models
    assert "eve" in [voice["voice_id"] for voice in client.voices]


@pytest.mark.parametrize("model", MODELS)
async def test_conversation(hass: HomeAssistant, live_entry, model: str) -> None:
    """A turn with a tool call, then a follow-up that replays the history."""
    hass.config_entries.async_update_entry(
        live_entry, options={**live_entry.options, CONF_CHAT_MODEL: model}
    )
    await hass.async_block_till_done()
    agent_id = er.async_get(hass).async_get_entity_id(
        "conversation", DOMAIN, live_entry.entry_id
    )
    EchoTool.calls.clear()

    start = time.monotonic()
    result = await conversation.async_converse(
        hass,
        "Call the echo tool with the text 'ping', then tell me what it returned.",
        None,
        Context(),
        agent_id=agent_id,
    )
    speech = result.response.speech["plain"]["speech"]
    print(f"\n[{model}] tool turn {time.monotonic() - start:.2f}s: {speech!r}")
    assert EchoTool.calls == ["ping"]
    assert "ping" in speech.lower()

    start = time.monotonic()
    result = await conversation.async_converse(
        hass,
        "What text did you echo? Answer with that one word.",
        result.conversation_id,
        Context(),
        agent_id=agent_id,
    )
    speech = result.response.speech["plain"]["speech"]
    print(f"[{model}] follow-up {time.monotonic() - start:.2f}s: {speech!r}")
    assert "ping" in speech.lower()


async def test_first_token_latency(hass: HomeAssistant, live_entry) -> None:
    """Report time to first text for each model."""
    client = live_entry.runtime_data
    for model in MODELS:
        payload = {
            "model": model,
            "input": [{"role": "user", "content": "Say hello in five words."}],
            "stream": True,
            "store": False,
        }
        if model == "grok-4.7":
            payload["reasoning"] = {"effort": "low"}
        start = time.monotonic()
        first = None
        types: set[str] = set()
        async for event in client.async_stream_response(payload):
            types.add(event["type"])
            if first is None and event["type"] == "response.output_text.delta":
                first = time.monotonic() - start
        print(
            f"\n[{model}] first text {first:.2f}s, done {time.monotonic() - start:.2f}s"
        )
        print(f"  event types: {sorted(types)}")
        assert first is not None
        assert "response.completed" in types


async def test_tts_stream(hass: HomeAssistant, live_entry) -> None:
    """Audio starts arriving before the text is complete."""
    entity = _entity(hass, "tts", f"{live_entry.entry_id}_tts")

    for attempt in ("cold", "prewarmed"):
        if attempt == "prewarmed":
            live_entry.runtime_data.async_prewarm_tts()
            await asyncio.sleep(0.5)
        text_done_at = None

        async def message_gen() -> AsyncGenerator[str]:
            nonlocal text_done_at
            for chunk in (
                "The kitchen ",
                "lights are on. ",
                "The living room is at twenty one degrees, ",
                "and the front door is locked. ",
                "Is there anything else you need?",
            ):
                yield chunk
                await asyncio.sleep(0.4)
            text_done_at = time.monotonic()

        start = time.monotonic()
        response = await entity.async_stream_tts_audio(
            TTSAudioRequest("en", {}, message_gen())
        )
        first_audio_at = None
        audio = b""
        async for chunk in response.data_gen:
            if first_audio_at is None:
                first_audio_at = time.monotonic()
            audio += chunk

        print(
            f"\n[{attempt}] first audio {first_audio_at - start:.2f}s, "
            f"text complete {text_done_at - start:.2f}s, "
            f"all audio {time.monotonic() - start:.2f}s, {len(audio):,} bytes"
        )
        assert response.extension == "mp3"
        assert audio[:3] == b"ID3" or audio[0] == 0xFF
        assert len(audio) > 20_000
        assert first_audio_at < text_done_at


async def test_tts_rest(hass: HomeAssistant, live_entry) -> None:
    """A complete message is synthesized in one request."""
    entity = _entity(hass, "tts", f"{live_entry.entry_id}_tts")
    extension, audio = await entity.async_get_tts_audio("Hello there.", "en", {})
    assert extension == "mp3"
    assert audio[:3] == b"ID3" or audio[0] == 0xFF


async def test_stt_stream(hass: HomeAssistant, live_entry) -> None:
    """Speech synthesized by xAI is transcribed back while streaming."""
    pcm = await live_entry.runtime_data.async_tts(
        {
            "text": "Turn on the kitchen lights.",
            "language": "en",
            "voice_id": "eve",
            "output_format": {"codec": "pcm", "sample_rate": 16000},
        }
    )
    entity = _entity(hass, "stt", f"{live_entry.entry_id}_stt")
    audio_done_at = None

    async def audio() -> AsyncGenerator[bytes]:
        nonlocal audio_done_at
        # 100 ms chunks at four times real time
        for offset in range(0, len(pcm), 3200):
            yield pcm[offset : offset + 3200]
            await asyncio.sleep(0.025)
        audio_done_at = time.monotonic()

    result = await entity.async_process_audio_stream(
        stt.SpeechMetadata(
            language="en-US",
            format=stt.AudioFormats.WAV,
            codec=stt.AudioCodecs.PCM,
            bit_rate=stt.AudioBitRates.BITRATE_16,
            sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
            channel=stt.AudioChannels.CHANNEL_MONO,
        ),
        audio(),
    )
    print(
        f"\ntranscript {time.monotonic() - audio_done_at:.2f}s after "
        f"{len(pcm) / 32000:.1f}s of audio ended: {result.text!r}"
    )
    assert result.result == stt.SpeechResultState.SUCCESS
    assert result.text == "Turn on the kitchen lights."


@pytest.mark.parametrize("model", MODELS)
async def test_web_search_is_dynamic(
    hass: HomeAssistant, live_entry, model: str
) -> None:
    """With web search enabled, the model searches only when the question needs it.

    Costs more than the other checks: each search is billed by xAI.
    """
    hass.config_entries.async_update_entry(
        live_entry,
        options={**live_entry.options, CONF_CHAT_MODEL: model, CONF_WEB_SEARCH: True},
    )
    await hass.async_block_till_done()
    agent_id = er.async_get(hass).async_get_entity_id(
        "conversation", DOMAIN, live_entry.entry_id
    )
    client = live_entry.runtime_data
    stream_response = client.async_stream_response
    items: list[str] = []

    async def recording_stream(payload):
        async for event in stream_response(payload):
            if event["type"] == "response.output_item.done":
                items.append(event["item"]["type"])
            yield event

    client.async_stream_response = recording_stream

    async def ask(text: str) -> tuple[str, list[str], float]:
        items.clear()
        start = time.monotonic()
        result = await conversation.async_converse(
            hass, text, None, Context(), agent_id=agent_id
        )
        speech = result.response.speech["plain"]["speech"]
        elapsed = time.monotonic() - start
        print(f"\n[{model}] {text!r}\n  {elapsed:.2f}s {items}\n  {speech!r}")
        return speech, list(items), elapsed

    speech, seen, _ = await ask("What is seven times six? Answer with the number.")
    assert "42" in speech
    assert not [item for item in seen if "search" in item]

    EchoTool.calls.clear()
    speech, seen, _ = await ask("Call the echo tool with the text 'ping'.")
    assert EchoTool.calls == ["ping"]
    assert not [item for item in seen if "search" in item]

    speech, seen, _ = await ask(
        "What is the latest stable release of Home Assistant Core? Look it up."
    )
    assert [item for item in seen if "search" in item]
    assert "http" not in speech
    assert "2026" in speech


def _solid_png(red: int, green: int, blue: int, size: int = 64) -> bytes:
    """Return a single-colour PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes((red, green, blue)) * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("model", MODELS)
async def test_ai_task_data(
    hass: HomeAssistant, live_entry, tmp_path: Path, model: str
) -> None:
    """Structured output is honoured and an attached image is understood."""
    hass.config_entries.async_update_entry(
        live_entry, options={**live_entry.options, CONF_CHAT_MODEL: model}
    )
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "ai_task", DOMAIN, f"{live_entry.entry_id}_ai_task"
    )

    start = time.monotonic()
    result = await ai_task.async_generate_data(
        hass,
        task_name="Shopping list",
        entity_id=entity_id,
        instructions="We are out of milk and eggs, and have plenty of rice.",
        structure=vol.Schema(
            {
                vol.Required("to_buy"): [str],
                vol.Required("item_count"): int,
                vol.Optional("note"): str,
            }
        ),
    )
    print(f"\n[{model}] structured {time.monotonic() - start:.2f}s: {result.data}")
    assert sorted(item.lower() for item in result.data["to_buy"]) == ["eggs", "milk"]
    assert result.data["item_count"] == 2

    image = tmp_path / "colour.png"
    image.write_bytes(_solid_png(255, 0, 0))
    start = time.monotonic()
    with patch(
        "homeassistant.components.media_source.async_resolve_media",
        return_value=media_source.PlayMedia(
            url="http://example/colour.png", mime_type="image/png", path=image
        ),
    ):
        result = await ai_task.async_generate_data(
            hass,
            task_name="Colour",
            entity_id=entity_id,
            instructions="What single colour fills this image? Answer in one word.",
            attachments=[{"media_content_id": "media-source://media/colour.png"}],
        )
    print(f"[{model}] image {time.monotonic() - start:.2f}s: {result.data!r}")
    assert "red" in result.data.lower()


async def test_ai_task_image(hass: HomeAssistant, live_entry) -> None:
    """An image is generated. Costs a few cents per run."""
    entity = hass.data["ai_task"].get_entity(
        er.async_get(hass).async_get_entity_id(
            "ai_task", DOMAIN, f"{live_entry.entry_id}_ai_task"
        )
    )
    start = time.monotonic()
    with (
        chat_session.async_get_chat_session(hass) as session,
        conversation.async_get_chat_log(hass, session) as chat_log,
    ):
        result = await entity._async_generate_image(
            ai_task.GenImageTask(name="Icon", instructions="A red apple on white"),
            chat_log,
        )
    print(
        f"\nimage {time.monotonic() - start:.2f}s: {len(result.image_data):,} bytes, "
        f"{result.mime_type}, revised prompt {result.revised_prompt!r}"
    )
    assert result.mime_type in ("image/jpeg", "image/png")
    assert result.image_data[:2] == b"\xff\xd8" or result.image_data[:4] == b"\x89PNG"
    assert len(result.image_data) > 10_000
