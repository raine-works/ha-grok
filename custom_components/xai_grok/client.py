"""Thin async client for the xAI API, built on Home Assistant's aiohttp session."""

import asyncio
from collections.abc import AsyncGenerator
import json
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import API_BASE, LOGGER, WS_BASE

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# Reasoning models can stay silent for a while before the first event
STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=300)
WS_CONNECT_TIMEOUT = 10
# How long a pre-opened TTS connection is kept waiting for the pipeline
TTS_WARM_TTL = 20


class XaiError(HomeAssistantError):
    """Error talking to the xAI API."""


class XaiAuthError(XaiError):
    """The API key was rejected."""


class XaiClient:
    """Client for the xAI REST, SSE and WebSocket APIs."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        api_key: str,
    ) -> None:
        """Initialize the client."""
        self._hass = hass
        self._session = session
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.models: list[str] = []
        self.voices: list[dict[str, str]] = []
        self._tts_last_params: dict[str, str] | None = None
        self._tts_warm: (
            tuple[dict[str, str], asyncio.Task[aiohttp.ClientWebSocketResponse]] | None
        ) = None
        self._tts_warm_expire: asyncio.TimerHandle | None = None

    async def _raise_for_status(self, resp: aiohttp.ClientResponse) -> None:
        """Raise a descriptive error for a failed response."""
        if resp.status < 400:
            return
        body = (await resp.text())[:500]
        # xAI answers a wrong key with 400 rather than 401
        if resp.status in (401, 403) or "Incorrect API key" in body:
            raise XaiAuthError(f"xAI rejected the API key ({resp.status}): {body}")
        raise XaiError(f"xAI API error {resp.status}: {body}")

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{API_BASE}{path}",
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                await self._raise_for_status(resp)
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise XaiError(f"Cannot reach xAI: {err}") from err

    async def async_list_models(self) -> list[str]:
        """Return the chat model IDs available to this API key."""
        data = await self._get_json("/models")
        return sorted(
            model["id"]
            for model in data.get("data", [])
            if model["id"].startswith("grok-")
            and not any(part in model["id"] for part in ("imagine", "voice"))
        )

    async def async_list_voices(self) -> list[dict[str, str]]:
        """Return the built-in TTS voices."""
        data = await self._get_json("/tts/voices")
        return [
            {
                "voice_id": voice["voice_id"],
                "name": voice.get("name", voice["voice_id"]),
            }
            for voice in data.get("voices", [])
        ]

    async def async_stream_response(
        self, payload: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any]]:
        """Create a streaming response and yield its server-sent events."""
        try:
            async with self._session.post(
                f"{API_BASE}/responses",
                json=payload,
                headers=self._headers,
                timeout=STREAM_TIMEOUT,
            ) as resp:
                await self._raise_for_status(resp)
                # Split lines ourselves: the final event carries the whole
                # response and can exceed aiohttp's readline limit.
                buffer = b""
                async for chunk in resp.content.iter_any():
                    buffer += chunk
                    while (end := buffer.find(b"\n")) >= 0:
                        line, buffer = buffer[:end].strip(), buffer[end + 1 :]
                        if not line.startswith(b"data:"):
                            continue
                        data = line[5:].strip()
                        if data == b"[DONE]":
                            return
                        yield json.loads(data)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise XaiError(f"Error talking to xAI: {err}") from err

    async def async_tts(self, body: dict[str, Any]) -> bytes:
        """Synthesize a complete message with the REST endpoint."""
        try:
            async with self._session.post(
                f"{API_BASE}/tts",
                json=body,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                await self._raise_for_status(resp)
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise XaiError(f"Error talking to xAI: {err}") from err

    async def async_generate_image(self, body: dict[str, Any]) -> dict[str, Any]:
        """Generate an image and return the first result."""
        try:
            async with self._session.post(
                f"{API_BASE}/images/generations",
                json=body,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                await self._raise_for_status(resp)
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise XaiError(f"Error talking to xAI: {err}") from err
        if not data.get("data"):
            raise XaiError("xAI returned no image")
        return data["data"][0]

    async def _ws_connect(
        self, path: str, params: dict[str, str]
    ) -> aiohttp.ClientWebSocketResponse:
        try:
            async with asyncio.timeout(WS_CONNECT_TIMEOUT):
                return await self._session.ws_connect(
                    f"{WS_BASE}{path}", params=params, headers=self._headers
                )
        except aiohttp.WSServerHandshakeError as err:
            if err.status in (401, 403):
                raise XaiAuthError(f"xAI rejected the API key ({err.status})") from err
            # The handshake error has no body, and a wrong key is reported as
            # 400 like any bad parameter; setup has already verified the key.
            raise XaiError(
                f"xAI refused the {path} connection ({err.status}): {err.message}"
            ) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise XaiError(f"Cannot reach xAI: {err}") from err

    async def async_stt_connect(
        self, params: dict[str, str]
    ) -> aiohttp.ClientWebSocketResponse:
        """Open a streaming speech-to-text connection."""
        return await self._ws_connect("/stt", params)

    async def async_tts_connect(
        self, params: dict[str, str]
    ) -> aiohttp.ClientWebSocketResponse:
        """Return a streaming text-to-speech connection, pre-opened if possible."""
        self._tts_last_params = params
        warm = self._take_warm()
        if warm is not None:
            warm_params, task = warm
            if warm_params == params:
                try:
                    ws = await task
                except XaiError as err:
                    LOGGER.debug("Pre-opened TTS connection failed: %s", err)
                else:
                    if not ws.closed:
                        return ws
            else:
                self._discard(task)
        return await self._ws_connect("/tts", params)

    @callback
    def async_prewarm_tts(self) -> None:
        """Open a TTS connection ahead of the audio request.

        Called when a conversation turn starts, so the WebSocket handshake
        overlaps with the model's time to first token. It reuses the settings
        of the previous TTS request, so it only helps from the second turn on.
        """
        if self._tts_last_params is None or self._tts_warm is not None:
            return
        params = self._tts_last_params
        task = self._hass.async_create_background_task(
            self._ws_connect("/tts", params), name="xai_grok_tts_prewarm"
        )
        self._tts_warm = (params, task)
        self._tts_warm_expire = self._hass.loop.call_later(
            TTS_WARM_TTL, self._expire_warm
        )

    def _take_warm(
        self,
    ) -> tuple[dict[str, str], asyncio.Task[aiohttp.ClientWebSocketResponse]] | None:
        warm, self._tts_warm = self._tts_warm, None
        if self._tts_warm_expire is not None:
            self._tts_warm_expire.cancel()
            self._tts_warm_expire = None
        return warm

    @callback
    def _expire_warm(self) -> None:
        self._tts_warm_expire = None
        if (warm := self._take_warm()) is not None:
            self._discard(warm[1])

    def _discard(self, task: asyncio.Task[aiohttp.ClientWebSocketResponse]) -> None:
        """Close an unused pre-opened connection."""

        async def _close() -> None:
            try:
                ws = await task
            except XaiError:
                return
            await ws.close()

        self._hass.async_create_background_task(
            _close(), name="xai_grok_tts_prewarm_close"
        )

    @callback
    def async_close(self) -> None:
        """Release any pre-opened connection."""
        self._expire_warm()
