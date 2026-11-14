"""Config flow for the xAI Grok integration."""

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import XaiConfigEntry
from .client import XaiAuthError, XaiClient, XaiError
from .const import (
    CONF_CHAT_MODEL,
    CONF_REASONING_EFFORT,
    CONF_TTS_LATENCY,
    CONF_TTS_SPEED,
    CONF_VOICE,
    CONF_WEB_SEARCH,
    CONF_X_SEARCH,
    DEFAULT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TTS_LATENCY,
    DEFAULT_TTS_SPEED,
    DEFAULT_VOICE,
    DOMAIN,
    FALLBACK_CHAT_MODELS,
    LOGGER,
)

# Home Assistant moved its schema library from voluptuous to probatio
try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

DEFAULT_OPTIONS = {
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_CHAT_MODEL: DEFAULT_CHAT_MODEL,
    CONF_REASONING_EFFORT: DEFAULT_REASONING_EFFORT,
    CONF_WEB_SEARCH: False,
    CONF_X_SEARCH: False,
    CONF_VOICE: DEFAULT_VOICE,
    CONF_TTS_SPEED: DEFAULT_TTS_SPEED,
    CONF_TTS_LATENCY: DEFAULT_TTS_LATENCY,
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class XaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for xAI Grok."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(user_input)
            client = XaiClient(
                self.hass, async_get_clientsession(self.hass), user_input[CONF_API_KEY]
            )
            try:
                await client.async_list_models()
            except XaiAuthError:
                errors["base"] = "invalid_auth"
            except XaiError:
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=user_input
                    )
                return self.async_create_entry(
                    title="Grok", data=user_input, options=DEFAULT_OPTIONS
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: XaiConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return XaiOptionsFlow()


class XaiOptionsFlow(OptionsFlow):
    """xAI Grok options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = dict(self.config_entry.options)
        valid_apis = {api.id for api in llm.async_get_apis(self.hass)}
        options[CONF_LLM_HASS_API] = [
            api for api in options.get(CONF_LLM_HASS_API, []) if api in valid_apis
        ]

        # The entry may not be loaded, for example with a revoked API key
        client: XaiClient | None = getattr(self.config_entry, "runtime_data", None)
        models = (client.models if client else None) or FALLBACK_CHAT_MODELS
        voices = client.voices if client else []

        schema = vol.Schema(
            {
                vol.Optional(CONF_PROMPT): TemplateSelector(),
                vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(label=api.name, value=api.id)
                            for api in llm.async_get_apis(self.hass)
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_CHAT_MODEL): SelectSelector(
                    SelectSelectorConfig(
                        options=models,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_REASONING_EFFORT): SelectSelector(
                    SelectSelectorConfig(
                        options=["low", "medium", "high"],
                        translation_key=CONF_REASONING_EFFORT,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_WEB_SEARCH): BooleanSelector(),
                vol.Required(CONF_X_SEARCH): BooleanSelector(),
                vol.Required(CONF_VOICE): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                label=voice["name"], value=voice["voice_id"]
                            )
                            for voice in voices
                        ],
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_TTS_SPEED): NumberSelector(
                    NumberSelectorConfig(
                        min=0.7, max=1.5, step=0.05, mode=NumberSelectorMode.SLIDER
                    )
                ),
                vol.Required(CONF_TTS_LATENCY): SelectSelector(
                    SelectSelectorConfig(
                        options=["0", "1", "2"],
                        translation_key=CONF_TTS_LATENCY,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, DEFAULT_OPTIONS | options
            ),
        )
