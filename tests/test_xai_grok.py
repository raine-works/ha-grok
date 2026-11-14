"""Tests for the xAI Grok integration against a local fake of the xAI API."""

import asyncio
from collections.abc import AsyncGenerator
import json

from homeassistant.components import conversation, stt
from homeassistant.components.tts import TTSAudioRequest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er, llm
import probatio as vol
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xai_grok.const import (
    CONF_CHAT_MODEL,
    CONF_REASONING_EFFORT,
    CONF_TTS_LATENCY,
    CONF_VOICE,
    CONF_WEB_SEARCH,
    DOMAIN,
)
from custom_components.xai_grok.entity import _supports_reasoning_effort

from .conftest import API_KEY, FakeXai


def _text_script(*deltas: str) -> list[dict]:
    return [
        {"type": "response.created", "response": {}},
        *({"type": "response.output_text.delta", "delta": delta} for delta in deltas),
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 8},
                }
            },
        },
    ]


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


class EchoTool(llm.Tool):
    """Tool that returns its input."""

    name = "echo"
    description = "Echo the text"
    parameters = vol.Schema({vol.Required("text"): str})

    async def async_call(self, hass, tool_input, llm_context):
        """Call the tool."""
        return llm.ToolResult(data={"echoed": tool_input.tool_args["text"]})


class EchoAPI(llm.API):
    """LLM API exposing the echo tool."""

    async def async_get_api_instance(self, llm_context):
        """Return the instance."""
        return llm.APIInstance(
            api=self,
            api_prompt="Use echo.",
            llm_context=llm_context,
            tools=[EchoTool()],
        )


async def test_config_flow(hass: HomeAssistant, fake_xai: FakeXai) -> None:
    """The user flow validates the key and the options flow renders and saves."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.runtime_data.models == ["grok-4.20-0309-non-reasoning", "grok-4.7"]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "grok-4.7",
            CONF_REASONING_EFFORT: "medium",
            CONF_WEB_SEARCH: True,
            "x_search": False,
            CONF_VOICE: "rex",
            "tts_speed": 1.2,
            CONF_TTS_LATENCY: "2",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_VOICE] == "rex"
    assert CONF_LLM_HASS_API not in entry.options
    await hass.async_block_till_done()


async def test_conversation_streams_text(
    hass: HomeAssistant, fake_xai: FakeXai, setup_entry: MockConfigEntry
) -> None:
    """Text deltas become the spoken response."""
    hass.config_entries.async_update_entry(
        setup_entry, options={**setup_entry.options, CONF_LLM_HASS_API: []}
    )
    await hass.async_block_till_done()

    fake_xai.response_scripts.append(_text_script("Hello", " there", "!"))
    result = await conversation.async_converse(
        hass,
        "hi",
        None,
        Context(),
        agent_id=_entity_id(hass, "conversation", setup_entry.entry_id),
    )

    assert result.response.speech["plain"]["speech"] == "Hello there!"
    request = fake_xai.response_requests[0]
    assert request["model"] == "grok-4.20-0309-non-reasoning"
    assert request["stream"] is True
    assert request["store"] is False
    assert request["prompt_cache_key"] == setup_entry.entry_id
    assert "reasoning" not in request
    assert "tools" not in request
    assert [item["role"] for item in request["input"]] == ["system", "user"]


async def test_conversation_tool_call_and_reasoning(
    hass: HomeAssistant, fake_xai: FakeXai, setup_entry: MockConfigEntry
) -> None:
    """Tools run, and results and encrypted reasoning go back on the next request."""
    llm.async_register_api(hass, EchoAPI(hass=hass, id="echo_api", name="Echo"))
    hass.config_entries.async_update_entry(
        setup_entry,
        options={
            **setup_entry.options,
            CONF_LLM_HASS_API: ["echo_api"],
            CONF_CHAT_MODEL: "grok-4.7",
            CONF_WEB_SEARCH: True,
        },
    )
    await hass.async_block_till_done()

    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "secret"}
    fake_xai.response_scripts.append(
        [
            {"type": "response.output_item.done", "item": reasoning},
            {
                "type": "response.output_item.done",
                "item": {"type": "web_search_call", "id": "ws_1"},
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "echo",
                    "arguments": json.dumps({"text": "ping"}),
                },
            },
            {"type": "response.completed", "response": {}},
        ]
    )
    fake_xai.response_scripts.append(_text_script("Echoed ping."))

    result = await conversation.async_converse(
        hass,
        "echo ping",
        None,
        Context(),
        agent_id=_entity_id(hass, "conversation", setup_entry.entry_id),
    )

    assert result.response.speech["plain"]["speech"] == "Echoed ping."
    first, second = fake_xai.response_requests
    assert first["reasoning"] == {"effort": "low"}
    assert first["tools"][0]["type"] == "function"
    assert first["tools"][0]["name"] == "echo"
    assert first["tools"][0]["parameters"]["properties"] == {"text": {"type": "string"}}
    assert first["tools"][-1] == {"type": "web_search"}
    assert first["include"] == ["no_inline_citations"]
    assert "without links" in first["input"][0]["content"]

    assert second["input"][-3:-1] == [
        reasoning,
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "echo",
            "arguments": '{"text":"ping"}',
        },
    ]
    output = second["input"][-1]
    assert output["type"] == "function_call_output"
    assert output["call_id"] == "call_1"
    assert json.loads(output["output"])["data"] == {"echoed": "ping"}


async def test_tts_streams_and_prewarms(
    hass: HomeAssistant, fake_xai: FakeXai, setup_entry: MockConfigEntry
) -> None:
    """Text is forwarded as it arrives, and the next turn reuses a warm socket."""
    entity = hass.data["tts"].get_entity(
        _entity_id(hass, "tts", f"{setup_entry.entry_id}_tts")
    )
    assert entity.async_supports_streaming_input()
    assert [v.voice_id for v in entity.async_get_supported_voices("en")] == [
        "eve",
        "rex",
    ]

    received: list[bytes] = []
    release = asyncio.Event()

    async def message_gen() -> AsyncGenerator[str]:
        yield "Hello **there**. "
        # Audio for the first chunk must arrive before the text is complete
        await release.wait()
        yield "Second sentence."

    response = await entity.async_stream_tts_audio(
        TTSAudioRequest("en", {"voice": "rex"}, message_gen())
    )
    assert response.extension == "mp3"
    async for chunk in response.data_gen:
        received.append(chunk)
        release.set()

    assert received == [b"<Hello there. >", b"<Second sentence.>"]
    assert fake_xai.tts_connections == [
        {
            "language": "en",
            "voice": "rex",
            "codec": "mp3",
            "speed": "1.0",
            "optimize_streaming_latency": "1",
        }
    ]

    # A conversation turn opens the next connection ahead of time
    client = setup_entry.runtime_data
    client.async_prewarm_tts()
    client.async_prewarm_tts()
    await client._tts_warm[1]
    assert len(fake_xai.tts_connections) == 2

    async def one_chunk() -> AsyncGenerator[str]:
        yield "Again."

    response = await entity.async_stream_tts_audio(
        TTSAudioRequest("en", {"voice": "rex"}, one_chunk())
    )
    assert [chunk async for chunk in response.data_gen] == [b"<Again.>"]
    assert len(fake_xai.tts_connections) == 2

    # Different settings do not reuse a warm connection, and empty text ends cleanly
    client.async_prewarm_tts()

    async def nothing() -> AsyncGenerator[str]:
        yield "  "

    response = await entity.async_stream_tts_audio(TTSAudioRequest("de", {}, nothing()))
    assert [chunk async for chunk in response.data_gen] == []
    assert fake_xai.tts_connections[-1]["language"] == "de"
    assert fake_xai.tts_connections[-1]["voice"] == "eve"


async def test_tts_rest(
    hass: HomeAssistant, fake_xai: FakeXai, setup_entry: MockConfigEntry
) -> None:
    """A complete message uses the REST endpoint."""
    entity = hass.data["tts"].get_entity(
        _entity_id(hass, "tts", f"{setup_entry.entry_id}_tts")
    )
    assert await entity.async_get_tts_audio("Hi *you*", "en", {}) == (
        "mp3",
        b"rest-audio",
    )
    assert fake_xai.tts_requests == [
        {"text": "Hi you", "language": "en", "voice_id": "eve", "speed": 1.0}
    ]


async def test_stt_streams(
    hass: HomeAssistant, fake_xai: FakeXai, setup_entry: MockConfigEntry
) -> None:
    """Audio is forwarded chunk by chunk and the final transcript returned."""
    entity = hass.data["stt"].get_entity(
        _entity_id(hass, "stt", f"{setup_entry.entry_id}_stt")
    )

    async def audio() -> AsyncGenerator[bytes]:
        yield b"\x01\x02"
        yield b""
        yield b"\x03\x04"

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

    assert result.result == stt.SpeechResultState.SUCCESS
    assert result.text == "Turn on the lights. Then lock the door. Thanks."
    assert fake_xai.stt_audio == b"\x01\x02\x03\x04"
    assert fake_xai.stt_connections == [
        {"sample_rate": "16000", "encoding": "pcm", "language": "en", "format": "true"}
    ]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("grok-4.7", True),
        ("grok-4.5", True),
        ("grok-5", True),
        ("grok-4.3", False),
        ("grok-4.20-0309-reasoning", False),
        ("grok-4.20-0309-non-reasoning", False),
        ("grok-build-0.1", False),
    ],
)
def test_supports_reasoning_effort(model: str, expected: bool) -> None:
    """Only grok-4.5 and newer take reasoning.effort."""
    assert _supports_reasoning_effort(model) is expected
