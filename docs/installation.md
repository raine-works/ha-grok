# Installation

You need Home Assistant 2026.10 or later.

## Home Assistant Marketplace (recommended)

[![Open your Home Assistant instance and open this repository in the Home Assistant Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=raine-works&repository=ha-grok&category=integration)

1. Open the Home Assistant Marketplace with the button above, or go to Settings → Marketplace.
2. If **xAI Grok** isn't listed, add `https://github.com/raine-works/ha-grok` as a custom repository of type **Integration**.
3. Download **xAI Grok**.
4. Restart Home Assistant.

Then continue with [Setup](setup.md).

## Manual

Copy `custom_components/xai_grok` from this repository into your Home Assistant `config/custom_components/` folder and restart.

The integration has no Python dependencies beyond Home Assistant. It can be installed next to `grok_conversation`, because the domains differ.
