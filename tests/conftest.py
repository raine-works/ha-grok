"""Fixtures for the xAI Grok tests: a local stand-in for the xAI API."""

import base64
import json
from typing import Any

from aiohttp import WSMsgType, web
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xai_grok import client as client_module
from custom_components.xai_grok.config_flow import DEFAULT_OPTIONS
from custom_components.xai_grok.const import DOMAIN

API_KEY = "xai-test-key"


class FakeXai:
    """Records requests and plays back scripted responses."""

    def __init__(self) -> None:
        """Initialize the fake."""
        self.response_scripts: list[list[dict[str, Any]]] = []
        self.response_requests: list[dict[str, Any]] = []
        self.tts_requests: list[dict[str, Any]] = []
        self.tts_connections: list[dict[str, str]] = []
        self.tts_text: list[str] = []
        self.stt_connections: list[dict[str, str]] = []
        self.stt_audio = b""

    def app(self) -> web.Application:
        """Build the application."""
        app = web.Application()
        app.router.add_get("/v1/models", self._models)
        app.router.add_get("/v1/tts/voices", self._voices)
        app.router.add_post("/v1/responses", self._responses)
        app.router.add_post("/v1/tts", self._tts_rest)
        app.router.add_get("/v1/tts", self._tts_ws)
        app.router.add_get("/v1/stt", self._stt_ws)
        return app

    @staticmethod
    def _check_auth(request: web.Request) -> None:
        if request.headers.get("Authorization") != f"Bearer {API_KEY}":
            # The real API reports a wrong key as 400, not 401
            raise web.HTTPBadRequest(
                text=json.dumps(
                    {
                        "code": "invalid-argument",
                        "error": "Incorrect API key provided. You can obtain "
                        "an API key from https://console.x.ai.",
                    }
                ),
                content_type="application/json",
            )

    async def _models(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        return web.json_response(
            {
                "data": [
                    {"id": "grok-4.7"},
                    {"id": "grok-4.20-0309-non-reasoning"},
                    {"id": "grok-imagine-image"},
                ]
            }
        )

    async def _voices(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        return web.json_response(
            {
                "voices": [
                    {"voice_id": "eve", "name": "Eve"},
                    {"voice_id": "rex", "name": "Rex"},
                ]
            }
        )

    async def _responses(self, request: web.Request) -> web.StreamResponse:
        self._check_auth(request)
        self.response_requests.append(await request.json())
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for event in self.response_scripts.pop(0):
            await response.write(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
            )
        await response.write(b"data: [DONE]\n\n")
        return response

    async def _tts_rest(self, request: web.Request) -> web.Response:
        self._check_auth(request)
        self.tts_requests.append(await request.json())
        return web.Response(body=b"rest-audio", content_type="audio/mpeg")

    async def _tts_ws(self, request: web.Request) -> web.WebSocketResponse:
        self._check_auth(request)
        self.tts_connections.append(dict(request.query))
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is not WSMsgType.TEXT:
                continue
            event = json.loads(msg.data)
            if event["type"] == "text.delta":
                self.tts_text.append(event["delta"])
                audio = base64.b64encode(f"<{event['delta']}>".encode()).decode()
                await ws.send_json({"type": "audio.delta", "delta": audio})
            elif event["type"] == "text.done":
                await ws.send_json({"type": "audio.done", "trace_id": "trace"})
        return ws

    async def _stt_ws(self, request: web.Request) -> web.WebSocketResponse:
        self._check_auth(request)
        self.stt_connections.append(dict(request.query))
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "transcript.created"})
        async for msg in ws:
            if msg.type is WSMsgType.BINARY:
                self.stt_audio += msg.data
            elif json.loads(msg.data)["type"] == "audio.done":
                # As observed live: each utterance arrives as chunk-final
                # results, then once more whole, and the final event is empty
                for text, speech_final in (
                    ("Turn on the lights.", False),
                    ("Turn on the lights.", True),
                    ("Then lock", False),
                    ("the door.", False),
                    ("Then lock the door.", True),
                    ("Thanks.", False),
                ):
                    await ws.send_json(
                        {
                            "type": "transcript.partial",
                            "text": text,
                            "is_final": True,
                            "speech_final": speech_final,
                        }
                    )
                await ws.send_json(
                    {"type": "transcript.done", "text": "", "duration": 1.0}
                )
                break
        return ws


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Enable custom integrations and the core component conversation needs."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
async def fake_xai(
    socket_enabled: None,
    hass: HomeAssistant,
    aiohttp_server,
    monkeypatch: pytest.MonkeyPatch,
) -> FakeXai:
    """Serve the fake xAI API and point the client at it."""
    fake = FakeXai()
    server = await aiohttp_server(fake.app())
    monkeypatch.setattr(client_module, "API_BASE", f"http://127.0.0.1:{server.port}/v1")
    monkeypatch.setattr(client_module, "WS_BASE", f"ws://127.0.0.1:{server.port}/v1")
    return fake


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Grok",
        data={CONF_API_KEY: API_KEY},
        options=DEFAULT_OPTIONS,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, fake_xai: FakeXai, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
