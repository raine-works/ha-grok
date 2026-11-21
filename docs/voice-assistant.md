# A fast voice assistant

Every stage streams, so a voice assistant built from the three entities starts answering quickly.

## Create the assistant

1. Go to Settings → Voice assistants and add an assistant, or edit one.
2. Set **Conversation agent** to *Grok*.
3. Set **Speech-to-text** to *Grok Speech to text*.
4. Set **Text-to-speech** to *Grok Text to speech*, and pick a voice if you don't want the default.

## Settings that help speed

- **Model:** keep the default non-reasoning model. It starts answering soonest.
- **Reasoning effort:** keep Low if you pick a model that reasons.
- **Web search and X search:** leave them off unless you need them. Searching makes answers slower.
- **Speech latency optimization:** Balanced or Fastest.
- **Instructions:** ask for short spoken answers and no Markdown. The prompt is cached by xAI, so a long stable prompt costs little.
- **Prefer handling commands locally:** in the assistant's settings, turn it on if you want Home Assistant's own intents to answer simple commands before Grok.

See [Conversation agent](conversation.md) and [Text to speech](text-to-speech.md) for each option.
