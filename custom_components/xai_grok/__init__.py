"""The xAI Grok integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import XaiAuthError, XaiClient, XaiError
from .const import FALLBACK_VOICES, LOGGER

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION, Platform.STT, Platform.TTS)

type XaiConfigEntry = ConfigEntry[XaiClient]


async def async_setup_entry(hass: HomeAssistant, entry: XaiConfigEntry) -> bool:
    """Set up xAI Grok from a config entry."""
    client = XaiClient(hass, async_get_clientsession(hass), entry.data[CONF_API_KEY])

    try:
        client.models = await client.async_list_models()
    except XaiAuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except XaiError as err:
        raise ConfigEntryNotReady(err) from err

    # Voices are only listed for keys with Voice access; chat still works without
    try:
        client.voices = await client.async_list_voices()
    except XaiError as err:
        LOGGER.warning("Could not load the xAI voice list: %s", err)
    if not client.voices:
        client.voices = FALLBACK_VOICES

    entry.runtime_data = client
    entry.async_on_unload(client.async_close)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: XaiConfigEntry) -> bool:
    """Unload xAI Grok."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: XaiConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
