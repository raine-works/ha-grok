"""AI Task support for xAI Grok."""

import base64
from json import JSONDecodeError

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.json import json_loads

from . import XaiConfigEntry
from .const import IMAGE_MODEL, LOGGER
from .entity import XaiLLMEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: XaiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    async_add_entities([XaiAITaskEntity(config_entry)])


class XaiAITaskEntity(ai_task.AITaskEntity, XaiLLMEntity):
    """xAI Grok AI Task entity."""

    _attr_name = "AI Task"
    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        | ai_task.AITaskEntityFeature.GENERATE_IMAGE
    )

    def __init__(self, entry: XaiConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_ai_task"

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        await self._async_handle_chat_log(chat_log, task.name, task.structure)

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            raise HomeAssistantError(
                "Last content in chat log is not an AssistantContent"
            )

        text = chat_log.content[-1].content or ""

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )
        try:
            data = json_loads(text)
        except JSONDecodeError as err:
            LOGGER.error("Failed to parse JSON response: %s. Response: %s", err, text)
            raise HomeAssistantError("Error with Grok structured response") from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task."""
        if task.attachments:
            raise HomeAssistantError(
                "Generating an image from attachments is not supported"
            )

        image = await self.entry.runtime_data.async_generate_image(
            {
                "model": IMAGE_MODEL,
                "prompt": task.instructions,
                "response_format": "b64_json",
            }
        )
        image_data = base64.b64decode(image["b64_json"])

        return ai_task.GenImageTaskResult(
            image_data=image_data,
            conversation_id=chat_log.conversation_id,
            mime_type=image.get("mime_type")
            or ("image/png" if image_data.startswith(b"\x89PNG") else "image/jpeg"),
            model=IMAGE_MODEL,
            revised_prompt=image.get("revised_prompt"),
        )
