# Agent guidance for ha-grok

## Raineworks base rules

This repository follows Raineworks' base rules, in [`.raineworks/base.md`](.raineworks/base.md): read them before
changing anything. They're a copy of `base.md` in `raine-works/agents`, kept current by its sync: change them there,
not here. Where this file is more specific, it wins.

@.raineworks/base.md

## This repository

An unofficial Home Assistant custom integration (`xai_grok`, "xAI Grok") for xAI's Grok: a conversation agent, speech
to text, text to speech and an AI Task entity, all streaming. It has no Python dependencies beyond Home Assistant
(`requirements` is empty) and needs Home Assistant 2026.10 or newer (`hacs.json`). Docs are in [docs/](docs/README.md).

### Layout

- `custom_components/xai_grok/`: `client.py` (the xAI REST, SSE and WebSocket client, on Home Assistant's aiohttp
  session), `config_flow.py` (API key, reauth, options), `entity.py` (shared chat-log handling), and one module per
  platform: `conversation.py`, `stt.py`, `tts.py`, `ai_task.py`. `translations/en.json` holds the UI strings.
- `tests/`: `conftest.py` runs the integration inside Home Assistant against a local stand-in for the xAI API;
  `test_xai_grok.py` are the tests; `test_live.py` hits the real API and skips itself without `XAI_API_KEY`.

### Checks and releases

- Set up and run (see [docs/development.md](docs/development.md)): `uv venv --python 3.14 && uv pip install -r
  requirements-test.txt`, then `ruff check .`, `ruff format --check .` and `python -m pytest`. CI (`test.yaml`, the
  workflow named `Test`) runs the same; `validate.yaml` runs hassfest and HACS validation.
- Ruff config is in `pyproject.toml` (line length 88, `E W F I B UP SIM C4`, imports sorted within sections).
- **A release is merging the release pull request:** `release-pr.yml` (Raineworks' shared Release pull request) keeps one pull request, `Release v<version>`, open on `master` with the next version: major for a breaking change (`type!:`), minor for a `feat`, patch for anything else that ships (a change to `custom_components/`). Merging it
  bumps `version` in `custom_components/xai_grok/manifest.json`, and `release.yaml` creates `v<version>` once `Test`
  passes. Never bump the version by hand.
- `requirements-test.txt` pins the test packages to what the pinned Home Assistant asks for, and `ruff` to the version CI
  installs.

### Rules the code follows

- All I/O is async through `XaiClient`; blocking work (audio encoding) goes through `hass.async_add_executor_job`.
- Setup raises `ConfigEntryAuthFailed` for a rejected key and `ConfigEntryNotReady` for other API errors; options
  changes reload the entry. xAI answers a wrong key with 400 as well as 401, which `client.py` treats as an auth error.
- The API key is only ever sent in the `Authorization` header; error bodies from xAI are truncated to 500 characters.
- Live tests in `tests/test_live.py` cost real money: never make them required.
