# xAI Grok for Home Assistant

A Home Assistant integration for xAI's Grok, built for a fast voice assistant.
It provides a conversation agent, speech to text and text to speech, and every
stage streams.

| Stage | How it is fast |
| --- | --- |
| Speech to text | Audio is streamed to `wss://api.x.ai/v1/stt` while you are still speaking, so the transcript is ready almost as soon as you stop. |
| Conversation | Responses API over server-sent events. Text reaches Home Assistant token by token, and tools run as soon as the model asks for them. A stable `prompt_cache_key` keeps the system prompt and tool list in xAI's prompt cache. |
| Text to speech | Tokens are forwarded to `wss://api.x.ai/v1/tts` as they are generated and audio is played as it comes back. The WebSocket is opened when the conversation turn starts, so the handshake overlaps with the model's thinking time. |

It has no Python dependencies beyond Home Assistant itself.

## Install

1. In HACS, add this repository as a custom repository of type *Integration*
   and install **xAI Grok**. Or copy `custom_components/xai_grok` into the
   `custom_components` folder of your configuration.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**, pick **xAI Grok**
   and enter an API key from [console.x.ai](https://console.x.ai). The key needs
   Voice access for speech to text and text to speech.
4. Go to **Settings > Voice assistants**, and in your assistant select *Grok* as
   the conversation agent, *Grok Speech to text* and *Grok Text to speech*.

It can be installed next to `grok_conversation`; the domains differ.

## Options

Open the integration and choose **Configure**.

| Option | Notes |
| --- | --- |
| Instructions | The system prompt. Templates are allowed. |
| Control Home Assistant | Which LLM APIs (such as Assist) Grok may use. |
| Model | Loaded from your account. The default, `grok-4.20-0309-non-reasoning`, starts answering soonest. `grok-4.7` is more capable but always reasons before it answers. |
| Reasoning effort | Sent to models that accept it (grok-4.5 and newer). Lower is faster. |
| Web search / X search | Lets Grok look things up on xAI's side. Answers that search take longer. |
| Voice | Default voice. A voice assistant can pick another. Custom voice IDs work. |
| Speech speed | 0.7 to 1.5. |
| Speech latency optimization | Higher starts speaking sooner, at some cost in audio quality where chunks join. |

## Notes

- Home Assistant only starts speaking mid-response once the response passes
  60 characters; shorter ones are synthesized when the text is complete.
- The first voice request after a restart opens its text to speech connection
  on demand. Later ones find it already open.
- Streaming speech to text is billed by xAI at a higher rate than batch
  ($0.20 against $0.10 per hour of audio at the time of writing).
- Images and other attachments are not sent to the model, and there is no
  AI Task entity.

## Development

```sh
uv venv --python 3.14 && uv pip install pytest-homeassistant-custom-component \
  hassil home-assistant-intents mutagen ha-ffmpeg pymicro-vad pyspeex-noise gazetteer-matcher
.venv/bin/python -m pytest
```

The tests run the integration inside Home Assistant against a local stand-in
for the xAI API (`tests/conftest.py`).
