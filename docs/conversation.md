# Conversation agent

The Grok conversation agent answers through xAI's Responses API over server-sent events. Text reaches Home Assistant token by token, and tools run as soon as the model asks for them. A stable prompt cache key (the config entry's ID) keeps the system prompt and tool list in xAI's prompt cache across conversations.

It supports every language Home Assistant sends it.

## Options

Set these under Configure. See [Setup](setup.md#options) for the defaults.

### Instructions

The system prompt. It can be a template. It's passed through Home Assistant's LLM helper together with any extra prompt the pipeline adds.

### Control Home Assistant

Which Home Assistant LLM APIs Grok may use, such as Assist. With at least one selected, the agent can control your devices, and Home Assistant marks it as supporting control. Only the entities you expose to Assist are available. With none selected, it only chats.

### Model

The list comes from your account. The default, `grok-4.20-0309-non-reasoning`, starts answering soonest, which matters most for voice. `grok-4.7` is more capable but always reasons before it answers. You can type any other model name.

### Reasoning effort

Low, Medium or High. It is sent only to models that accept it (grok-4.5 and newer, not the non-reasoning ones). Lower is faster.

### Web search and X search

Each adds a search tool that runs on xAI's side, so Grok can look things up on the web or in posts on X. Answers that search take longer. Home Assistant's own tools are still run by Home Assistant.

## Images

Images attached in a conversation aren't sent to the model. Use the [AI Task](ai-task.md) entity for images.
