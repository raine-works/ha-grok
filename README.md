# xAI Grok for Home Assistant

An **unofficial** [Home Assistant](https://www.home-assistant.io/) integration for
[xAI](https://x.ai)'s Grok, from [raine-works](https://github.com/raine-works),
built for a fast voice assistant. It provides a conversation agent, speech to
text and text to speech, and every stage streams. It also provides an AI Task
entity for automations.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg?style=for-the-badge)](LICENSE)

[![Test](https://github.com/raine-works/ha-grok/actions/workflows/test.yaml/badge.svg)](https://github.com/raine-works/ha-grok/actions/workflows/test.yaml)
[![Validate](https://github.com/raine-works/ha-grok/actions/workflows/validate.yaml/badge.svg)](https://github.com/raine-works/ha-grok/actions/workflows/validate.yaml)

<a href="https://buymeacoffee.com/raineworks"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" /></a>

> This project is not affiliated with, authorized, or endorsed by xAI. It uses
> xAI's public API with your own API key, and xAI bills you for that usage.

| Stage | How it is fast |
| --- | --- |
| Speech to text | Audio is streamed to `wss://api.x.ai/v1/stt` while you are still speaking, so the transcript is ready almost as soon as you stop. |
| Conversation | Responses API over server-sent events. Text reaches Home Assistant token by token, and tools run as soon as the model asks for them. A stable `prompt_cache_key` keeps the system prompt and tool list in xAI's prompt cache. |
| Text to speech | Tokens are forwarded to `wss://api.x.ai/v1/tts` as they are generated and audio is played as it comes back. The WebSocket is opened when the conversation turn starts, so the handshake overlaps with the model's thinking time. |

It has no Python dependencies beyond Home Assistant itself.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=raine-works&repository=ha-grok&category=integration)

1. Click the button above (or in HACS, **⋮ → Custom repositories**, add
   `https://github.com/raine-works/ha-grok` as category **Integration**).
2. Install **xAI Grok**, then restart Home Assistant.

### Manual

Copy `custom_components/xai_grok` into your Home Assistant
`config/custom_components/` directory and restart.

It can be installed next to `grok_conversation`; the domains differ.

## Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=xai_grok)

1. Click the button above (or go to **Settings → Devices & services → Add
   integration → xAI Grok**) and enter an API key from
   [console.x.ai](https://console.x.ai). The key needs Voice access for speech
   to text and text to speech.
2. Go to **Settings → Voice assistants**, and in your assistant select *Grok* as
   the conversation agent, *Grok Speech to text* and *Grok Text to speech*.

Requires Home Assistant 2026.10 or newer.

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

## AI Task

The *Grok AI Task* entity works with the `ai_task.generate_data` and
`ai_task.generate_image` actions, and can be chosen as the default under
**Settings → System → General → AI suggestions**.

- **Generate data** uses the model selected in the options. With a `structure`
  the answer comes back as data in that shape. Image attachments (camera
  snapshots, media) are sent along; other file types are rejected.
- **Generate image** uses `grok-imagine-image-2.0`, which xAI bills per image.
  Generating from attached images is not supported.


- Home Assistant only starts speaking mid-response once the response passes
  60 characters; shorter ones are synthesized when the text is complete.
- The first voice request after a restart opens its text to speech connection
  on demand. Later ones find it already open.
- Streaming speech to text is billed by xAI at a higher rate than batch
  ($0.20 against $0.10 per hour of audio at the time of writing).
- Images attached in a conversation are not sent to the model; use the AI Task
  entity for those.

## Development

```sh
uv venv --python 3.14 && uv pip install -r requirements-test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

The tests run the integration inside Home Assistant against a local stand-in
for the xAI API (`tests/conftest.py`).

`tests/test_live.py` runs the same entities against the real API and prints
latencies. It is skipped unless `XAI_API_KEY` is set in the environment or in
a `.env` file at the repository root, and costs a fraction of a cent per run:

```sh
.venv/bin/python -m pytest tests/test_live.py -s
```

## Contributing

Issues and PRs welcome. This is a community project maintained on a best-effort
basis. If something breaks, please include your Home Assistant version, the
model you selected and any relevant Home Assistant logs.

## ☕ Support

If you find this project helpful, consider buying me a coffee to support continued
maintenance and development:

<a href="https://buymeacoffee.com/raineworks"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" /></a>

## License

[MIT](LICENSE) © [Raine Petersen](https://github.com/raine-works)
