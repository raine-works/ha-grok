# Text to speech

The *Text to speech* entity speaks through xAI at `wss://api.x.ai/v1/tts`. In a conversation, tokens are forwarded to xAI as the model generates them, and audio plays as it comes back. The connection is opened when the conversation turn starts, so the handshake overlaps with the model's thinking time.

## Options

Set these under Configure.

| Option | Default | Notes |
| :--- | :--- | :--- |
| Voice | `eve` | The default voice. The list comes from your account, and custom voice IDs are accepted. |
| Speech speed | 1.0 | 0.7 to 1.5. |
| Speech latency optimization | Balanced | Off (best quality), Balanced or Fastest. Higher starts speaking sooner, at some cost in audio quality where chunks join. |

A voice assistant can pick another voice than the default. The `voice` option also works in `tts.speak` calls.

## Languages

Every voice speaks every language. These are listed: English, Arabic (Egypt, Saudi Arabia, UAE), Bengali, Chinese, French, German, Hindi, Indonesian, Italian, Japanese, Korean, Portuguese (Brazil, Portugal), Russian, Spanish (Mexico, Spain), Turkish and Vietnamese. Others work with varying accuracy.

## Behavior

- Markdown characters (`*`, `#`, backticks) are removed before speaking.
- Home Assistant starts speaking mid-response only once the response passes 60 characters. Shorter ones are synthesized when the text is complete.
- The first voice request after a restart opens its connection on demand. Later ones find it already open.
