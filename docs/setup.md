# Setup

## Add the integration

1. Create an API key at [console.x.ai](https://console.x.ai). The key needs Voice access for speech to text and text to speech.
2. Go to Settings → Devices & services → **Add integration** → **xAI Grok**, or use this button:

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=xai_grok)
3. Enter the API key. Home Assistant checks it by listing the models on your account.

The same key can't be added twice. If xAI rejects the key later, Home Assistant asks you to re-authenticate with a new one.

There are no subentries: one entry holds one key and all the options below.

## What it creates

| Entity | Used for |
| :--- | :--- |
| Grok (conversation agent) | [Conversation agent](conversation.md) |
| Speech to text | [Speech to text](speech-to-text.md) |
| Text to speech | [Text to speech](text-to-speech.md) |
| AI Task | [AI Task](ai-task.md) |

## Options

Open the integration and choose **Configure**. Defaults are in the second column.

| Option | Default | Notes |
| :--- | :--- | :--- |
| Instructions | Home Assistant's default instructions | The system prompt. Templates are allowed. |
| Control Home Assistant | Assist | Which LLM APIs Grok may use. |
| Model | `grok-4.20-0309-non-reasoning` | Loaded from your account. Other model names can be typed in. |
| Reasoning effort | Low | Low, Medium or High. |
| Web search | Off | Lets Grok search the web. |
| X search | Off | Lets Grok search posts on X. |
| Voice | `eve` | Default voice. Custom voice IDs are accepted. |
| Speech speed | 1.0 | 0.7 to 1.5, in steps of 0.05. |
| Speech latency optimization | Balanced | Off (best quality), Balanced or Fastest. |

Each option is described on its own page: the first six in [Conversation agent](conversation.md), the last three in [Text to speech](text-to-speech.md).
