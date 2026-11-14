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
import time

from aiohttp.resolver import ThreadedResolver
import probatio as vol
import pytest
import pytest_socket
from pytest_homeassistant_custom_component import plugins as ha_plugins
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xai_grok.config_flow import DEFAULT_OPTIONS
from custom_components.xai_grok.const import CONF_CHAT_MODEL, DOMAIN
from homeassistant.components import conversation, stt
from homeassistant.components.tts import TTSAudioRequest
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er, llm


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
    assert "kitchen" in result.text.lower()
