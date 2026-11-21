# Speech to text

The *Speech to text* entity streams audio to xAI at `wss://api.x.ai/v1/stt` while you are still speaking, so the transcript is ready almost as soon as you stop.

## Use it

In Settings → Voice assistants, pick **Grok Speech to text** as the speech-to-text engine of an assistant. See [A fast voice assistant](voice-assistant.md).

## Languages

The entity lists the languages xAI documents, including Arabic (and its UAE and Saudi variants), Chinese, Dutch, English, French, German, Hindi, Italian, Japanese, Korean, Portuguese, Russian and Spanish, among others. For some languages (Arabic, Chinese, English, French, German, Japanese, Portuguese, Russian, Spanish, Swedish and Vietnamese), xAI writes numbers, currency and units as digits.

## Cost

Streaming speech to text is billed by xAI at a higher rate than batch ($0.20 against $0.10 per hour of audio at the time of writing). Your API key needs Voice access.
