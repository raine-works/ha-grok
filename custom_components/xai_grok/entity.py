"""Base entities for xAI Grok."""

from collections.abc import AsyncGenerator, AsyncIterable, Callable, Iterable
import json
import re
from typing import TYPE_CHECKING, Any

from homeassistant.components import conversation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.json import json_dumps

from .const import (
    CONF_CHAT_MODEL,
    CONF_REASONING_EFFORT,
    CONF_WEB_SEARCH,
    CONF_X_SEARCH,
    DEFAULT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    DOMAIN,
    LOGGER,
)

if TYPE_CHECKING:
    from . import XaiConfigEntry

# Home Assistant moved its schema library from voluptuous to probatio
try:
    from probatio import to_openapi

    def _convert_schema(
        schema: Any, custom_serializer: Callable[[Any], Any] | None
    ) -> dict[str, Any]:
        return to_openapi(
            schema, custom_serializer=custom_serializer, openapi_version="3.1.0"
        )

except ImportError:
    from voluptuous_openapi import convert

    def _convert_schema(
        schema: Any, custom_serializer: Callable[[Any], Any] | None
    ) -> dict[str, Any]:
        return convert(schema, custom_serializer=custom_serializer)


# Max number of back and forth with the LLM to generate a response
MAX_TOOL_ITERATIONS = 10

NO_CITATIONS_PROMPT = (
    "When you search, do not include citations, links or URLs in your answer."
)


def _supports_reasoning_effort(model: str) -> bool:
    """Return if the model accepts reasoning.effort (grok-4.5 and newer)."""
    if "non-reasoning" in model or not (
        match := re.match(r"grok-(\d+)(?:\.(\d+))?", model)
    ):
        return False
    major, minor = int(match[1]), match[2] or "0"
    # 4.20 and 4.3 predate the parameter; 4.5 to 4.9 are single-digit minors
    return major > 4 or (major == 4 and len(minor) == 1 and int(minor) >= 5)


def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> dict[str, Any]:
    """Format tool specification."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "parameters": _convert_schema(tool.parameters, custom_serializer),
    }


def _convert_content(
    chat_content: Iterable[conversation.Content],
) -> list[dict[str, Any]]:
    """Convert chat log content to Responses API input items."""
    items: list[dict[str, Any]] = []

    for content in chat_content:
        if isinstance(content, conversation.ToolResultContent):
            # Before 2026.x the result was a plain dict in `tool_result`
            if (result := getattr(content, "result", None)) is not None:
                output = {"data": result.data, "error": result.error}
            else:
                output = content.tool_result
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": content.tool_call_id,
                    "output": json_dumps(output),
                }
            )
            continue

        if isinstance(content, conversation.AssistantContent):
            # Encrypted reasoning goes back unchanged, ahead of what it produced
            if isinstance(content.native, dict):
                items.append(content.native)
            if content.content:
                items.append({"role": "assistant", "content": content.content})
            items.extend(
                {
                    "type": "function_call",
                    "call_id": tool_call.id,
                    "name": tool_call.tool_name,
                    "arguments": json_dumps(tool_call.tool_args),
                }
                for tool_call in content.tool_calls or ()
                if not tool_call.external
            )
        elif content.content:
            items.append({"role": content.role, "content": content.content})

    return items


async def _transform_stream(
    chat_log: conversation.ChatLog,
    events: AsyncIterable[dict[str, Any]],
) -> AsyncGenerator[
    conversation.AssistantContentDeltaDict | conversation.ToolResultContentDeltaDict
]:
    """Transform Responses API stream events into HA format."""
    tool_names = (
        {tool.name for tool in chat_log.llm_api.tools} if chat_log.llm_api else set()
    )
    has_native = False

    yield {"role": "assistant"}

    async for event in events:
        event_type = event.get("type")

        if event_type == "response.output_text.delta":
            if delta := event.get("delta"):
                yield {"content": delta}
        elif event_type == "response.output_item.done":
            item = event.get("item") or {}
            # Search tools run on xAI's side; only our own tools are executed
            if item.get("type") == "function_call" and item.get("name") in tool_names:
                try:
                    tool_args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError as err:
                    raise HomeAssistantError(
                        f"Grok sent invalid arguments for {item['name']}"
                    ) from err
                yield {
                    "tool_calls": [
                        llm.ToolInput(
                            id=item["call_id"],
                            tool_name=item["name"],
                            tool_args=tool_args,
                        )
                    ]
                }
            elif item.get("type") == "reasoning" and item.get("encrypted_content"):
                # A message holds one native item, so a second one starts a new one
                if has_native:
                    yield {"role": "assistant"}
                yield {"native": item}
                has_native = True
        elif event_type == "response.completed":
            if usage := (event.get("response") or {}).get("usage"):
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": usage.get("input_tokens"),
                            "cached_tokens": (
                                usage.get("input_tokens_details") or {}
                            ).get("cached_tokens"),
                            "output_tokens": usage.get("output_tokens"),
                        }
                    }
                )
        elif event_type == "response.incomplete":
            details = (event.get("response") or {}).get("incomplete_details") or {}
            raise HomeAssistantError(
                f"Grok response incomplete: {details.get('reason', 'unknown reason')}"
            )
        elif event_type == "response.failed":
            error = (event.get("response") or {}).get("error") or {}
            raise HomeAssistantError(
                f"Grok response failed: {error.get('message', 'unknown reason')}"
            )
        elif event_type == "error":
            raise HomeAssistantError(
                f"Grok response error: {event.get('message', event)}"
            )


class XaiBaseEntity(Entity):
    """Base entity for xAI Grok."""

    _attr_has_entity_name = True

    def __init__(self, entry: "XaiConfigEntry") -> None:
        """Initialize the entity."""
        self.entry = entry
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="xAI",
            model=entry.options.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL),
            entry_type=dr.DeviceEntryType.SERVICE,
        )


class XaiLLMEntity(XaiBaseEntity):
    """Entity that generates responses with a Grok chat model."""

    async def _async_handle_chat_log(self, chat_log: conversation.ChatLog) -> None:
        """Generate an answer for the chat log."""
        options = self.entry.options
        model = options.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL)

        messages = _convert_content(chat_log.content)

        payload: dict[str, Any] = {
            "model": model,
            "input": messages,
            "stream": True,
            # The chat log is the source of truth, so nothing is kept at xAI
            "store": False,
            # Routes every request to the server that cached the shared prefix
            # (system prompt and tools), across conversations
            "prompt_cache_key": self.entry.entry_id,
        }

        if _supports_reasoning_effort(model):
            payload["reasoning"] = {
                "effort": options.get(CONF_REASONING_EFFORT, DEFAULT_REASONING_EFFORT)
            }

        tools: list[dict[str, Any]] = []
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]
        if options.get(CONF_WEB_SEARCH):
            tools.append({"type": "web_search"})
        if options.get(CONF_X_SEARCH):
            tools.append({"type": "x_search"})
        if tools:
            payload["tools"] = tools

        if (
            (options.get(CONF_WEB_SEARCH) or options.get(CONF_X_SEARCH))
            and messages
            and messages[0].get("role") == "system"
        ):
            messages[0]["content"] += f"\n{NO_CITATIONS_PROMPT}"

        client = self.entry.runtime_data

        # To prevent infinite loops, we limit the number of iterations
        for _iteration in range(MAX_TOOL_ITERATIONS):
            LOGGER.debug("Requesting response from %s", model)
            content_stream = chat_log.async_add_delta_content_stream(
                self.entity_id,
                _transform_stream(chat_log, client.async_stream_response(payload)),
            )
            messages.extend(
                _convert_content([content async for content in content_stream])
            )

            if not chat_log.unresponded_tool_results:
                break
