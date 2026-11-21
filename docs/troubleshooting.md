# Troubleshooting

## Voice access

Speech to text and text to speech need an API key with Voice access. Create or edit the key at [console.x.ai](https://console.x.ai).

## Invalid API key

Home Assistant asks you to re-authenticate. Enter a new key.

## The model list is short

If the integration isn't loaded (for example after a revoked key), Configure shows a built-in list: `grok-4.20-0309-non-reasoning`, `grok-4.7` and `grok-4.3`. You can type other names.

## Slow answers

Web search, X search and reasoning models add time. See [A fast voice assistant](voice-assistant.md).

## Known behavior

- Home Assistant only starts speaking mid-response once the response passes 60 characters.
- The first voice request after a restart opens its text-to-speech connection on demand.
- Images attached in a conversation aren't sent to the model.

## Reporting an issue

Open an issue on [GitHub](https://github.com/raine-works/ha-grok/issues). Include your Home Assistant version, the model you selected and any relevant Home Assistant logs.
